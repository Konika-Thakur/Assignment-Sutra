import json
from string import Template
from retrieval.store import search
from llm.ollama_client import call


SUMMARY_PROMPT = Template("""You are an AI evaluator. Based on the following evidence from a submission, create a unified summary.

Evidence:
$evidence

Return ONLY valid JSON with:
- "problem": what problem the submission addresses
- "solution": what solution is proposed
- "features": list of features mentioned
- "implementation_depth": brief assessment of implementation quality
- "gaps": list of any observed gaps between claims and evidence

Return only valid JSON.""")


def build(store):
    queries = ["problem statement", "solution approach", "features implemented", "technical implementation"]
    all_evidence = []

    for q in queries:
        results = search(store, q, k=4)
        all_evidence.extend(results)

    seen = set()
    unique = []
    for e in all_evidence:
        if e["reference"] not in seen:
            seen.add(e["reference"])
            unique.append(e)

    evidence_text = "\n".join(
        f"[{e['reference']}] {e['text'][:300]}" for e in unique[:16]
    )

    prompt = SUMMARY_PROMPT.safe_substitute(evidence=evidence_text)
    response = call(prompt)

    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        return json.loads(response[start:end])
    except Exception:
        return {
            "problem": "Could not extract.",
            "solution": "Could not extract.",
            "features": [],
            "implementation_depth": "Unknown.",
            "gaps": []
        }
