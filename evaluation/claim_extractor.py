import json
from string import Template
from retrieval.store import search
from llm.ollama_client import call


CLAIM_PROMPT = Template("""You are an evaluation assistant. Extract structured claims from the following submission content.

Return ONLY a valid JSON array with no explanation. Each item must have:
- "claim": the specific claim made
- "type": one of [problem, feature, technical_approach, implementation]
- "source": one of [deck, video, code, website]
- "reference": where it came from

Content:
$content

Return only valid JSON array.""")

REPAIR_PROMPT = Template("""Convert the claim extraction response below into ONLY one valid JSON array.

Extractor response:
$response

Required item schema:
{
  "claim": "specific claim made by the submission",
  "type": "problem | feature | technical_approach | implementation",
  "source": "deck | video | code | website",
  "reference": "source reference"
}

Rules:
- Return a JSON array only.
- Drop vague or duplicate claims.
- Keep source and reference values when present.
- No markdown, no explanation.""")

SOURCE_CLAIM_QUERIES = {
    "deck": [
        "problem being solved",
        "features and capabilities",
        "technical approach and architecture",
        "solution proposed",
    ],
    "video": [
        "demo proof and walkthrough",
        "features shown in the demo",
        "user flows demonstrated",
        "implementation details mentioned",
    ],
    "code": [
        "implemented features and core functionality",
        "technical architecture and important modules",
        "data persistence API endpoints authentication integrations",
        "implementation quality and missing pieces",
    ],
    "website": [
        "working prototype features",
        "navigation forms buttons and user flows",
        "data processing or saved user input",
        "visible product functionality",
    ],
}

SOURCE_K = {
    "deck": 6,
    "video": 4,
    "code": 6,
    "website": 4,
}


VALID_TYPES = {"problem", "feature", "technical_approach", "implementation"}
VALID_SOURCES = set(SOURCE_CLAIM_QUERIES)


def _parse_json_array(response):
    try:
        response = str(response or "")
        start = response.find("[")
        end = response.rfind("]") + 1
        if start == -1 or end <= start:
            return None
        parsed = json.loads(response[start:end])
        return parsed if isinstance(parsed, list) else None
    except Exception:
        return None


def _sanitize_claims(claims):
    sanitized = []
    seen = set()
    for item in claims or []:
        if not isinstance(item, dict):
            continue

        claim_text = str(item.get("claim", "")).strip()
        if len(claim_text) < 12:
            continue

        claim_type = str(item.get("type", "feature")).strip()
        if claim_type not in VALID_TYPES:
            claim_type = "feature"

        source = str(item.get("source", "deck")).strip()
        if source not in VALID_SOURCES:
            source = "deck"

        normalized = claim_text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)

        sanitized.append({
            "claim": claim_text,
            "type": claim_type,
            "source": source,
            "reference": str(item.get("reference", "")).strip()
        })
    return sanitized


def _fallback_claims_from_chunks(chunks):
    claims = []
    for chunk in chunks[:10]:
        text = " ".join(str(chunk.get("text", "")).split())
        if len(text) < 40:
            continue
        sentence = text.split(". ")[0].strip()
        if len(sentence) > 220:
            sentence = sentence[:220].rsplit(" ", 1)[0]
        claims.append({
            "claim": sentence,
            "type": "implementation" if chunk.get("source") == "code" else "feature",
            "source": chunk.get("source", "deck"),
            "reference": chunk.get("reference", "")
        })
    return _sanitize_claims(claims)


def extract(store):
    seen_refs = set()
    chunks = []

    for source, queries in SOURCE_CLAIM_QUERIES.items():
        for query in queries:
            for r in search(store, query, k=SOURCE_K[source], source=source):
                key = (r["source"], r["reference"])
                if key not in seen_refs:
                    seen_refs.add(key)
                    chunks.append(r)

    content = "\n\n".join(
        f"[source={c['source']} reference={c['reference']}] {c['text']}"
        for c in chunks
    )
    prompt = CLAIM_PROMPT.safe_substitute(content=content)
    response = call(prompt)

    claims = _parse_json_array(response)
    if claims is None:
        repair_response = call(REPAIR_PROMPT.safe_substitute(response=str(response or "")[:3000]))
        claims = _parse_json_array(repair_response)

    return _sanitize_claims(claims) if claims is not None else _fallback_claims_from_chunks(chunks)
