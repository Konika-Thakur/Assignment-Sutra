import json
import requests
from bs4 import BeautifulSoup
from string import Template
from urllib.parse import urljoin, urlparse
from llm.ollama_client import call
from utils.url_security import assert_safe_url


FUNCTIONAL_VALIDATION_PROMPT = Template("""You are validating a live prototype for an evaluation system.

Claimed features:
$claims

Observed live page evidence:
URL: $url
Status code: $status_code
Visible text:
$visible_text

Forms:
$forms

Buttons:
$buttons

Inputs:
$inputs

Links:
$links

Navigation probes:
$navigation_probes

Form/action probes:
$form_probes

Data-processing signals:
$data_signals

Browser flow validation:
$browser_validation

Assess only what can be supported by the observed page evidence. Do not assume backend behavior unless the page evidence suggests it.
Treat successful page loads and reachable same-origin links as stronger evidence than static tags. Treat POST forms, API paths, upload fields, save buttons, and dashboard/report pages as data-processing signals, but mark them partial unless there is direct page evidence that the flow completed.
When browser validation is enabled, use successful page load, real browser-rendered text, completed clicks, form submit outcomes, and observed network requests as the strongest evidence.

Return ONLY valid JSON with:
- "functional_summary": concise assessment of what appears to work
- "observed_features": list of features supported by page evidence
- "missing_or_unverified_claims": list of claimed features not visible or not verifiable
- "core_flows": list of objects with "flow", "status" one of [observed, partially_observed, not_observed], "evidence"
- "data_processing_signals": list of observed save/process/upload/API/form signals
- "confidence": float between 0.0 and 1.0

Return only valid JSON.""")


def _parse_json_object(response, fallback):
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        parsed = json.loads(response[start:end])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return fallback


def _claim_text(claims):
    if not claims:
        return "No structured claims were extracted."
    lines = []
    for item in claims[:20]:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim")
        if claim:
            source = item.get("source", "unknown")
            reference = item.get("reference", "")
            lines.append(f"- [{source}:{reference}] {claim}")
    return "\n".join(lines) if lines else "No structured claims were extracted."


def _page_observations(soup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    visible_text = "\n".join(lines[:80])

    forms = []
    for form in soup.find_all("form")[:10]:
        inputs = [
            inp.get("name") or inp.get("type") or inp.get("placeholder") or "unnamed_input"
            for inp in form.find_all(["input", "textarea", "select"])
        ]
        forms.append({
            "action": form.get("action", ""),
            "method": form.get("method", "get"),
            "inputs": inputs
        })

    buttons = [
        button.get_text(" ", strip=True) or button.get("aria-label") or "unnamed_button"
        for button in soup.find_all(["button"])[:30]
    ]
    inputs = [
        {
            "type": inp.get("type", inp.name),
            "name": inp.get("name", ""),
            "placeholder": inp.get("placeholder", "")
        }
        for inp in soup.find_all(["input", "textarea", "select"])[:30]
    ]
    links = [
        {
            "text": a.get_text(" ", strip=True),
            "href": a.get("href", "")
        }
        for a in soup.find_all("a", href=True)[:30]
    ]

    return visible_text, forms, buttons, inputs, links


def _same_origin(base_url, target_url):
    base = urlparse(base_url)
    target = urlparse(target_url)
    return target.scheme in ("http", "https") and target.netloc == base.netloc


def _safe_get(session, target_url, allow_local=False):
    try:
        assert_safe_url(target_url, allow_local=allow_local)
        response = session.get(target_url, timeout=8, allow_redirects=False)
        return {
            "url": target_url,
            "final_url": response.url,
            "status_code": response.status_code,
            "loads_successfully": 200 <= response.status_code < 400
        }
    except requests.exceptions.Timeout:
        return {
            "url": target_url,
            "status_code": None,
            "loads_successfully": False,
            "error": "timeout"
        }
    except Exception as exc:
        return {
            "url": target_url,
            "status_code": None,
            "loads_successfully": False,
            "error": str(exc)
        }


def _probe_navigation(session, base_url, links, limit=8, allow_local=False):
    probes = []
    seen = set()
    for link in links:
        href = link.get("href")
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        target = urljoin(base_url, href)
        if target in seen or not _same_origin(base_url, target):
            continue

        seen.add(target)
        probe = _safe_get(session, target, allow_local=allow_local)
        probe["text"] = link.get("text", "")
        probes.append(probe)

        if len(probes) >= limit:
            break
    return probes


def _probe_form_actions(session, base_url, forms, limit=5, allow_local=False):
    probes = []
    for form in forms[:limit]:
        action = form.get("action") or base_url
        target = urljoin(base_url, action)
        method = form.get("method", "get").lower()

        probe = {
            "action": target,
            "method": method,
            "inputs": form.get("inputs", []),
            "submitted": False
        }

        # Only probe GET actions. POST/PUT/DELETE could mutate the app, so they are reported as unverified flows.
        if method == "get" and _same_origin(base_url, target):
            probe.update(_safe_get(session, target, allow_local=allow_local))
        else:
            probe["loads_successfully"] = None
            probe["note"] = "Not submitted to avoid side effects."

        probes.append(probe)
    return probes


def _data_processing_signals(forms, buttons, inputs, links):
    keywords = (
        "save", "submit", "upload", "process", "generate", "analyze",
        "report", "dashboard", "api", "webhook", "checkout", "payment"
    )
    signals = []

    for form in forms:
        method = form.get("method", "get").lower()
        if method != "get":
            signals.append(f"{method.upper()} form action: {form.get('action') or 'current page'}")
        if form.get("inputs"):
            signals.append(f"form inputs: {', '.join(form['inputs'])}")

    for button in buttons:
        if any(keyword in button.lower() for keyword in keywords):
            signals.append(f"button: {button}")

    for inp in inputs:
        input_text = " ".join(str(inp.get(key, "")) for key in ("type", "name", "placeholder"))
        if any(keyword in input_text.lower() for keyword in keywords) or inp.get("type") == "file":
            signals.append(f"input: {input_text.strip()}")

    for link in links:
        link_text = f"{link.get('text', '')} {link.get('href', '')}"
        if any(keyword in link_text.lower() for keyword in keywords):
            signals.append(f"link: {link_text.strip()}")

    return signals[:25]


def _dummy_value(input_type, name, placeholder):
    label = f"{name} {placeholder}".lower()
    if input_type == "email" or "email" in label:
        return "test@example.com"
    if input_type == "password" or "password" in label:
        return "TestPassword123!"
    if input_type == "number":
        return "1"
    if input_type in ("date",):
        return "2026-01-01"
    if "phone" in label:
        return "9999999999"
    return "test input"


def _browser_flow_validation(url, submit_forms=True, allow_local=False):
    try:
        assert_safe_url(url, allow_local=allow_local)
    except ValueError as exc:
        return {
            "enabled": False,
            "reason": f"Browser validation blocked unsafe URL: {exc}"
        }

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        return {
            "enabled": False,
            "reason": "Playwright is not installed. Install it with `pip install playwright` and `playwright install chromium`."
        }

    network_requests = []
    browser = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("requestfinished", lambda req: network_requests.append({
                "method": req.method,
                "url": req.url,
                "resource_type": req.resource_type
            }))

            response = page.goto(url, wait_until="networkidle", timeout=15000)
            rendered = page.evaluate("""() => ({
                title: document.title,
                text: document.body ? document.body.innerText.slice(0, 4000) : "",
                buttons: Array.from(document.querySelectorAll("button, input[type=submit]")).slice(0, 20).map((el) => ({
                    text: el.innerText || el.value || el.getAttribute("aria-label") || "",
                    type: el.getAttribute("type") || el.tagName.toLowerCase()
                })),
                forms: Array.from(document.querySelectorAll("form")).slice(0, 5).map((form, index) => ({
                    index,
                    action: form.getAttribute("action") || "",
                    method: form.getAttribute("method") || "get",
                    inputs: Array.from(form.querySelectorAll("input, textarea, select")).map((el) => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute("type") || el.tagName.toLowerCase(),
                        name: el.getAttribute("name") || "",
                        placeholder: el.getAttribute("placeholder") || ""
                    }))
                }))
            })""")

            form_results = []
            if submit_forms:
                for index, form_meta in enumerate(rendered.get("forms", [])[:2]):
                    method = form_meta.get("method", "get").lower()
                    form_result = {
                        "form_index": index,
                        "method": method,
                        "submitted": False,
                        "status": "not_observed",
                        "evidence": []
                    }

                    try:
                        form = page.locator("form").nth(index)
                        for input_index, input_meta in enumerate(form_meta.get("inputs", [])):
                            input_type = input_meta.get("type", "text")
                            if input_type in ("hidden", "submit", "button", "file", "checkbox", "radio"):
                                continue
                            field = form.locator("input, textarea").nth(input_index)
                            if field.count():
                                field.fill(_dummy_value(
                                    input_type,
                                    input_meta.get("name", ""),
                                    input_meta.get("placeholder", "")
                                ), timeout=3000)

                        before_url = page.url
                        submit = form.locator("button[type=submit], input[type=submit], button").first
                        if submit.count():
                            submit.click(timeout=5000)
                        else:
                            form.locator("input, textarea").first.press("Enter", timeout=5000)

                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except PlaywrightTimeoutError:
                            pass

                        after_text = page.locator("body").inner_text(timeout=5000)[:1000]
                        form_result.update({
                            "submitted": True,
                            "status": "partially_observed",
                            "before_url": before_url,
                            "after_url": page.url,
                            "evidence": [
                                "Form accepted dummy input and submit action completed in browser.",
                                after_text
                            ]
                        })
                    except Exception as exc:
                        form_result["error"] = str(exc)

                    form_results.append(form_result)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=8000)
                    except Exception:
                        break

            return {
                "enabled": True,
                "status_code": response.status if response else None,
                "final_url": page.url,
                "rendered_title": rendered.get("title", ""),
                "rendered_text": rendered.get("text", ""),
                "rendered_buttons": rendered.get("buttons", []),
                "rendered_forms": rendered.get("forms", []),
                "form_results": form_results,
                "network_requests": network_requests[:30]
            }
    except Exception as exc:
        return {
            "enabled": False,
            "reason": f"Browser validation failed: {str(exc)}"
        }
    finally:
        if browser is not None:
            browser.close()


def _claimed_features(claims):
    features = []
    for item in claims or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in ("feature", "technical_approach", "implementation"):
            claim = item.get("claim")
            if claim:
                features.append({
                    "claim": claim,
                    "source": item.get("source", "unknown"),
                    "reference": item.get("reference", "")
                })
    return features[:20]


def _observed_vs_claimed(claims, functional_validation):
    claimed = _claimed_features(claims)
    observed = functional_validation.get("observed_features", [])
    missing = functional_validation.get("missing_or_unverified_claims", [])
    return {
        "claimed_features_count": len(claimed),
        "observed_features": observed,
        "missing_or_unverified_claims": missing,
        "claimed_features_sample": claimed[:8],
        "has_mismatch": bool(missing)
    }


def validate(url, claims=None, submit_forms=False, allow_local=False):
    default_mismatch = {
        "claimed_features_count": len(_claimed_features(claims)),
        "observed_features": [],
        "missing_or_unverified_claims": [],
        "claimed_features_sample": _claimed_features(claims)[:8],
        "has_mismatch": False
    }

    if not url:
        return {
            "url": None,
            "accessible": False,
            "summary": "No URL provided.",
            "features_detected": [],
            "functional_validation": None,
            "observed_vs_claimed_mismatch": default_mismatch
        }

    result = {
        "url": url,
        "accessible": False,
        "status_code": None,
        "summary": "",
        "features_detected": [],
        "functional_validation": None,
        "browser_validation": None,
        "observed_vs_claimed_mismatch": default_mismatch,
        "issues": []
    }

    session = requests.Session()

    try:
        assert_safe_url(url, allow_local=allow_local)
        response = session.get(url, timeout=10, allow_redirects=False)
        result["status_code"] = response.status_code
        result["accessible"] = response.status_code == 200
    except requests.exceptions.ConnectionError:
        result["summary"] = "Connection failed. URL may be offline."
        result["issues"].append("connection_error")
        result["observed_vs_claimed_mismatch"] = {
            **default_mismatch,
            "missing_or_unverified_claims": [
                item["claim"] for item in _claimed_features(claims)
            ],
            "has_mismatch": bool(_claimed_features(claims))
        }
        return result
    except requests.exceptions.Timeout:
        result["summary"] = "Request timed out."
        result["issues"].append("timeout")
        result["observed_vs_claimed_mismatch"] = {
            **default_mismatch,
            "missing_or_unverified_claims": [
                item["claim"] for item in _claimed_features(claims)
            ],
            "has_mismatch": bool(_claimed_features(claims))
        }
        return result
    except Exception as e:
        result["summary"] = f"Unexpected error: {str(e)}"
        result["issues"].append("unknown_error")
        result["observed_vs_claimed_mismatch"] = {
            **default_mismatch,
            "missing_or_unverified_claims": [
                item["claim"] for item in _claimed_features(claims)
            ],
            "has_mismatch": bool(_claimed_features(claims))
        }
        return result

    if not result["accessible"]:
        result["summary"] = f"URL returned status {result['status_code']}."
        result["observed_vs_claimed_mismatch"] = {
            **default_mismatch,
            "missing_or_unverified_claims": [
                item["claim"] for item in _claimed_features(claims)
            ],
            "has_mismatch": bool(_claimed_features(claims))
        }
        return result

    soup = BeautifulSoup(response.text, "html.parser")
    visible_text, forms, buttons, inputs, links = _page_observations(soup)
    navigation_probes = _probe_navigation(session, url, links, allow_local=allow_local)
    form_probes = _probe_form_actions(session, url, forms, allow_local=allow_local)
    data_signals = _data_processing_signals(forms, buttons, inputs, links)
    browser_validation = _browser_flow_validation(
        url,
        submit_forms=submit_forms,
        allow_local=allow_local
    )
    result["browser_validation"] = browser_validation

    features = []

    if forms:
        features.append("form_present")
    if any(inp.get("type") == "email" or inp.get("name") == "email" for inp in inputs):
        features.append("email_input")
    if any(inp.get("type") == "password" for inp in inputs):
        features.append("login_form")
    if buttons:
        features.append("buttons_present")
    if soup.find("nav"):
        features.append("navigation_present")
    if soup.find("table"):
        features.append("data_table")
    if soup.find(id=True):
        features.append("structured_elements")

    result["features_detected"] = features
    result["summary"] = (
        f"URL is accessible. Detected {len(features)} UI feature(s): {', '.join(features) if features else 'none'}."
    )
    prompt = FUNCTIONAL_VALIDATION_PROMPT.safe_substitute(
        claims=_claim_text(claims),
        url=url,
        status_code=result["status_code"],
        visible_text=visible_text[:4000],
        forms=json.dumps(forms, indent=2),
        buttons=json.dumps(buttons, indent=2),
        inputs=json.dumps(inputs, indent=2),
        links=json.dumps(links, indent=2),
        navigation_probes=json.dumps(navigation_probes, indent=2),
        form_probes=json.dumps(form_probes, indent=2),
        data_signals=json.dumps(data_signals, indent=2),
        browser_validation=json.dumps(browser_validation, indent=2)
    )
    response = call(prompt)
    result["functional_validation"] = _parse_json_object(response, {
        "functional_summary": "Could not parse LLM prototype validation.",
        "observed_features": features,
        "missing_or_unverified_claims": [],
        "core_flows": [],
        "data_processing_signals": [],
        "confidence": 0.0
    })
    result["observed_vs_claimed_mismatch"] = _observed_vs_claimed(
        claims,
        result["functional_validation"]
    )
    result["summary"] = result["functional_validation"].get("functional_summary", result["summary"])

    return result
