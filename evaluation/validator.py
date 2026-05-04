import json
import re
from string import Template
from retrieval.store import search
from llm.ollama_client import call


VALIDATE_PROMPT = Template("""You are an AI evaluator. Given a claim and retrieved evidence, decide if the claim is supported.

Claim: $claim

Evidence:
$evidence

Return ONLY valid JSON with:
- "status": one of [supported, partially_supported, not_supported]
- "reasoning": brief explanation
- "confidence": float between 0.0 and 1.0
- "citations": list of reference strings from evidence

Return only valid JSON.""")

CODE_CHECK_PROMPT = Template("""You are an AI evaluator. A submission made the following claim. Check if the code evidence below actually implements it.

Claim: $claim

Code Evidence:
$evidence

Return ONLY valid JSON with:
- "implemented": true or false
- "reasoning": brief explanation grounded in code evidence
- "citations": list of reference strings from evidence

Return only valid JSON.""")

PROTOTYPE_CHECK_PROMPT = Template("""You are an AI evaluator. A submission made the following claim. Check if the prototype or website evidence below shows it working.

Claim: $claim

Prototype Evidence:
$evidence

Return ONLY valid JSON with:
- "observed": true or false
- "reasoning": brief explanation grounded in prototype evidence
- "citations": list of reference strings from evidence

Return only valid JSON.""")

REPAIR_PROMPT = Template("""Convert the evaluator response below into ONLY one valid JSON object.

Evaluator response:
$response

Allowed citation references:
$allowed_references

Required schema:
$schema

Rules:
- Keep only citations that exactly match the allowed citation references.
- Return only valid JSON, no markdown.""")

SOURCES = ("deck", "video", "code", "website")
IMPLEMENTATION_CLAIM_TYPES = {"feature", "technical_approach", "implementation"}


def _parse_json_object(response, fallback):
    try:
        response = str(response or "")
        start = response.find("{")
        end = response.rfind("}") + 1
        parsed = json.loads(response[start:end])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return fallback


def _tokens(text):
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", text.lower())
        if len(token) > 3
    }


def _format_evidence(evidence):
    return "\n".join(f"[{e['reference']}] {e['text'][:300]}" for e in evidence)


def _references(evidence):
    return [e["reference"] for e in evidence]


def _repair_json_response(response, schema, allowed_references):
    response = str(response or "")
    repair_prompt = REPAIR_PROMPT.safe_substitute(
        response=response[:3000],
        allowed_references=", ".join(allowed_references),
        schema=schema
    )
    repair_response = call(repair_prompt)
    return _parse_json_object(repair_response, None)


def _sanitize_citations(citations, allowed_references):
    if not isinstance(citations, list):
        return []

    allowed = set(allowed_references)
    sanitized = []
    for citation in citations:
        citation = str(citation).strip().strip("[]")
        if citation in allowed and citation not in sanitized:
            sanitized.append(citation)
    return sanitized


def _valid_status(value):
    status = str(value).strip().lower()
    if status in {"supported", "partially_supported", "not_supported"}:
        return status
    return "not_supported"


def _valid_confidence(value):
    try:
        confidence = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, confidence))


def _valid_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _source_names(evidence_by_source):
    return [source for source, evidence in evidence_by_source.items() if evidence]


def _evidence_text(evidence):
    return " ".join(str(item.get("text", "")) for item in evidence)


def _token_overlap_count(claim_text, evidence):
    claim_tokens = _tokens(claim_text)
    evidence_tokens = _tokens(_evidence_text(evidence))
    return len(claim_tokens & evidence_tokens)


def _fallback_general_validation(claim_text, evidence_by_source, references):
    sources = _source_names(evidence_by_source)
    if not references:
        return {
            "status": "not_supported",
            "reasoning": "No retrieved evidence was available for this claim.",
            "confidence": 0.0,
            "citations": []
        }

    general_evidence = [
        evidence
        for source in SOURCES
        for evidence in evidence_by_source[source]
    ]
    overlap_count = _token_overlap_count(claim_text, general_evidence)

    if overlap_count >= 4 and len(sources) >= 2:
        status = "supported"
        confidence = 0.72
    elif overlap_count >= 2:
        status = "partially_supported"
        confidence = 0.55
    else:
        status = "not_supported"
        confidence = 0.30

    return {
        "status": status,
        "reasoning": (
            "The evaluator response could not be parsed, but retrieved evidence from "
            f"{', '.join(sources)} is available for this claim. "
            f"A conservative evidence-based fallback status is used after matching {overlap_count} claim terms."
        ),
        "confidence": confidence,
        "citations": references[:4] if status != "not_supported" else references[:2]
    }


def _fallback_code_validation(claim_text, code_evidence):
    if not code_evidence:
        return {"implemented": False, "reasoning": "No code evidence found.", "citations": []}

    overlap_count = _token_overlap_count(claim_text, code_evidence)
    implemented = overlap_count >= 2
    return {
        "implemented": implemented,
        "reasoning": (
            "The code-check response could not be parsed, but retrieved code evidence "
            f"contains {overlap_count} matching claim terms, so a conservative fallback was used."
            if implemented
            else "The code-check response could not be parsed and too little related implementation signal was found."
        ),
        "citations": _references(code_evidence)[:3] if implemented else []
    }


def _fallback_prototype_validation(prototype_evidence):
    if not prototype_evidence:
        return {"observed": False, "reasoning": "No prototype evidence found.", "citations": []}
    return {
        "observed": True,
        "reasoning": "Prototype-check response could not be parsed, but retrieved prototype evidence exists.",
        "citations": _references(prototype_evidence)[:3]
    }


def _build_cross_artifact_flags(claim_source, claim_type, code_parsed, prototype_parsed, evidence_by_source):
    flags = []

    if claim_source in ("deck", "video") and claim_type in IMPLEMENTATION_CLAIM_TYPES:
        if not _valid_bool(code_parsed.get("implemented", False)):
            flags.append(f"{claim_source}_claim_missing_code_evidence")
        if evidence_by_source["website"] and not _valid_bool(prototype_parsed.get("observed", False)):
            flags.append(f"{claim_source}_claim_not_observed_in_prototype")

    if claim_source == "code" and not evidence_by_source["deck"] and not evidence_by_source["video"]:
        flags.append("code_exists_but_not_claimed_or_demonstrated")

    if claim_source == "website" and not evidence_by_source["code"]:
        flags.append("prototype_feature_missing_code_evidence")

    return flags


def validate(claims, store):
    results = []
    for item in claims:
        if not isinstance(item, dict):
            continue

        claim_text = item.get("claim", "")
        if not claim_text:
            continue
        claim_source = item.get("source", "unknown")
        claim_type = item.get("type", "unknown")

        evidence_by_source = {
            source: search(store, claim_text, k=5, source=source)
            for source in SOURCES
        }

        # General support is judged over source-separated evidence, not a single mixed RAG blob.
        general_evidence = [
            evidence
            for source in SOURCES
            for evidence in evidence_by_source[source]
        ]
        evidence_text = _format_evidence(general_evidence)
        general_references = _references(general_evidence)
        prompt = VALIDATE_PROMPT.safe_substitute(claim=claim_text, evidence=evidence_text)
        response = call(prompt)
        parsed = _parse_json_object(response, None)
        if parsed is None:
            parsed = _repair_json_response(
                response,
                '{"status": "supported", "reasoning": "brief evidence-grounded reason", "confidence": 0.0, "citations": []}',
                general_references
            )
        if parsed is None:
            parsed = _fallback_general_validation(claim_text, evidence_by_source, general_references)

        # Cross-artifact: verify claim exists in code
        code_evidence = evidence_by_source["code"]
        if code_evidence:
            code_text = _format_evidence(code_evidence)
            code_prompt = CODE_CHECK_PROMPT.safe_substitute(claim=claim_text, evidence=code_text)
            code_response = call(code_prompt)
            code_parsed = _parse_json_object(code_response, None)
            if code_parsed is None:
                code_parsed = _repair_json_response(
                    code_response,
                    '{"implemented": true, "reasoning": "brief code-grounded reason", "citations": []}',
                    _references(code_evidence)
                )
            if code_parsed is None:
                code_parsed = _fallback_code_validation(claim_text, code_evidence)
            code_parsed["citations"] = _sanitize_citations(
                code_parsed.get("citations", []),
                _references(code_evidence)
            )
        else:
            code_parsed = {"implemented": False, "reasoning": "No code evidence found.", "citations": []}

        # Cross-artifact: verify claim appears in the working prototype/URL crawl
        prototype_evidence = evidence_by_source["website"]
        if prototype_evidence:
            prototype_text = _format_evidence(prototype_evidence)
            prototype_prompt = PROTOTYPE_CHECK_PROMPT.safe_substitute(
                claim=claim_text,
                evidence=prototype_text
            )
            prototype_response = call(prototype_prompt)
            prototype_parsed = _parse_json_object(prototype_response, None)
            if prototype_parsed is None:
                prototype_parsed = _repair_json_response(
                    prototype_response,
                    '{"observed": true, "reasoning": "brief prototype-grounded reason", "citations": []}',
                    _references(prototype_evidence)
                )
            if prototype_parsed is None:
                prototype_parsed = _fallback_prototype_validation(prototype_evidence)
            prototype_parsed["citations"] = _sanitize_citations(
                prototype_parsed.get("citations", []),
                _references(prototype_evidence)
            )
        else:
            prototype_parsed = {"observed": False, "reasoning": "No prototype evidence found.", "citations": []}

        mismatch_flags = _build_cross_artifact_flags(
            claim_source,
            claim_type,
            code_parsed,
            prototype_parsed,
            evidence_by_source
        )
        has_prototype_evidence = bool(evidence_by_source["website"])

        results.append({
            "claim": claim_text,
            "type": claim_type,
            "source": claim_source,
            "reference": item.get("reference", ""),
            "status": _valid_status(parsed.get("status", "not_supported")),
            "reasoning": parsed.get("reasoning", ""),
            "confidence": _valid_confidence(parsed.get("confidence", 0.0)),
            "citations": _sanitize_citations(
                parsed.get("citations", []),
                general_references
            ) or general_references[:3],
            "source_coverage": {
                source: {
                    "has_evidence": bool(evidence_by_source[source]),
                    "citations": _references(evidence_by_source[source])
                }
                for source in SOURCES
            },
            "code_validation": {
                "implemented_in_code": _valid_bool(code_parsed.get("implemented", False)),
                "reasoning": code_parsed.get("reasoning", ""),
                "citations": code_parsed.get("citations", [])
            },
            "prototype_validation": {
                "observed_in_prototype": _valid_bool(prototype_parsed.get("observed", False)),
                "reasoning": prototype_parsed.get("reasoning", ""),
                "citations": prototype_parsed.get("citations", [])
            },
            "cross_artifact_flags": {
                "missing_code_evidence": not _valid_bool(code_parsed.get("implemented", False)),
                "missing_prototype_evidence": has_prototype_evidence and not _valid_bool(prototype_parsed.get("observed", False)),
                "mismatches": mismatch_flags
            }
        })

    return results
