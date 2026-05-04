import json
from string import Template
from retrieval.store import search
from llm.ollama_client import call


CRITERIA = [
    "Problem Understanding",
    "Technical Approach",
    "Implementation Quality",
    "Innovation / Originality",
    "Communication & Demo Clarity",
    "Claim vs Reality Alignment",
    "Prototype Functionality"
]

SCORE_PROMPT = Template("""You are an AI evaluator scoring a submission on a specific criterion.

Criterion: $criterion

Retrieved Evidence:
$evidence

Allowed citation references:
$allowed_references

Score from 1 to 5 where:
1 = very weak, 2 = weak, 3 = average, 4 = good, 5 = excellent

Rules:
- Use only the retrieved evidence above.
- Every citation must exactly match one of the allowed citation references.
- If evidence is missing or weak for this criterion, assign a low score and explain the gap.

Return ONLY valid JSON with:
- "score": integer 1-5
- "reasoning": brief explanation grounded in evidence
- "citations": list of reference strings
- "confidence": float 0.0-1.0

Return only valid JSON.""")

REPAIR_PROMPT = Template("""Convert the evaluator response below into ONLY one valid JSON object.

Evaluator response:
$response

Allowed citation references:
$allowed_references

Required schema:
{
  "score": 1,
  "reasoning": "brief evidence-grounded reason",
  "citations": [],
  "confidence": 0.0
}

Rules:
- Keep only citations that exactly match the allowed citation references.
- Score must be an integer from 1 to 5.
- Confidence must be a number from 0.0 to 1.0.
- Return only valid JSON, no markdown.""")


CRITERION_QUERIES = {
    "Problem Understanding": "problem pain point target user motivation",
    "Technical Approach": "technical approach architecture model stack system design",
    "Implementation Quality": "code implementation files modules persistence tests API quality",
    "Innovation / Originality": "innovation originality differentiation novel approach",
    "Communication & Demo Clarity": "demo walkthrough presentation clarity video explanation user flow",
    "Claim vs Reality Alignment": "claimed features evidence mismatch missing code prototype support",
    "Prototype Functionality": "working prototype URL app loads forms buttons navigation data processing",
}


def _parse_json_object(response):
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start == -1 or end <= start:
            return None
        parsed = json.loads(response[start:end])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _valid_score(value):
    try:
        score = int(value)
    except Exception:
        return 1
    return max(1, min(5, score))


def _valid_confidence(value):
    try:
        confidence = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, confidence))


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


def _fallback_score(criterion, retrieved, allowed_references):
    if not retrieved:
        return {
            "score": 1,
            "reasoning": f"No retrieved evidence was available for {criterion}, so the system cannot justify a stronger score.",
            "citations": [],
            "confidence": 0.0
        }

    return {
        "score": 3,
        "reasoning": (
            f"Retrieved evidence exists for {criterion}, but the evaluator response could not be parsed reliably. "
            "An average conservative score is used to preserve evidence-before-scoring behavior."
        ),
        "citations": allowed_references[:3],
        "confidence": 0.45
    }


def _prototype_not_provided_score():
    return {
        "criterion": "Prototype Functionality",
        "score": 1,
        "reasoning": "No prototype URL was provided, so app loading, navigation, core flows, and data-processing behavior could not be validated.",
        "citations": [],
        "confidence": 0.0,
        "evidence_count": 0
    }


def _call_score_prompt(prompt, allowed_references):
    response = call(prompt)
    parsed = _parse_json_object(response)
    if parsed is not None:
        return parsed

    repair_prompt = REPAIR_PROMPT.safe_substitute(
        response=response[:3000],
        allowed_references=", ".join(allowed_references)
    )
    repair_response = call(repair_prompt)
    return _parse_json_object(repair_response)


def score(store, has_prototype=False):
    results = []
    for criterion in CRITERIA:
        if criterion == "Prototype Functionality" and not has_prototype:
            results.append(_prototype_not_provided_score())
            continue

        retrieved = search(store, CRITERION_QUERIES[criterion], k=8)
        allowed_references = [e["reference"] for e in retrieved]
        evidence_text = "\n".join(
            f"[{e['reference']}] source={e['source']} {e['text'][:450]}" for e in retrieved
        )

        if not retrieved:
            parsed = _fallback_score(criterion, retrieved, allowed_references)
        else:
            prompt = SCORE_PROMPT.safe_substitute(
                criterion=criterion,
                evidence=evidence_text,
                allowed_references=", ".join(allowed_references)
            )
            parsed = _call_score_prompt(prompt, allowed_references) or _fallback_score(
                criterion,
                retrieved,
                allowed_references
            )

        citations = _sanitize_citations(parsed.get("citations", []), allowed_references)
        if retrieved and not citations:
            citations = allowed_references[:3]

        results.append({
            "criterion": criterion,
            "score": _valid_score(parsed.get("score", 1)),
            "reasoning": parsed.get("reasoning", ""),
            "citations": citations,
            "confidence": _valid_confidence(parsed.get("confidence", 0.0)),
            "evidence_count": len(retrieved)
        })

    return results
