# Design Note: AI Evidence Layer MVP

## Goal

The system creates an evidence-backed evaluation workflow for submissions that may include a presentation deck, demo video or transcript, repository content, and an optional working prototype URL. The central design choice is to build a retrieval-backed evidence layer first, then allow the LLM to summarize, validate, and score only against retrieved evidence.

## Architecture

1. Ingestion normalizes each artefact into source-tagged chunks:
   - Deck: PDF, PPT/PPTX, or text mapped to `slide_*` references.
   - Video: transcript lines or Whisper segments mapped to `transcript_line_*` or `video_*` references.
   - Code: supported repository files mapped to relative file paths and line-aware chunk references.
   - URL: crawled website text mapped to page URLs.

2. Chunking preserves traceability:
   - Text is split by sentence-like boundaries.
   - Code is split around class/function/logical boundaries where possible.
   - Every chunk keeps `source` and `reference` metadata.

3. Retrieval stores evidence in an in-memory Qdrant vector collection:
   - Each run uses the submission ID as the collection name.
   - Searches can be filtered by artefact source for cross-validation.

4. Claim extraction asks the LLM to produce structured claims:
   - `claim`
   - `type`
   - `source`
   - `reference`

5. Claim validation cross-checks each claim:
   - General support is judged from retrieved evidence across all sources.
   - Code validation checks whether implementation claims are present in code evidence.
   - Prototype validation checks whether working app evidence supports claimed features.
   - The output includes source coverage, missing evidence flags, and mismatch labels.

6. Prototype validation checks live signals:
   - HTTP accessibility and status.
   - Visible text, forms, inputs, buttons, links, tables, and navigation.
   - Same-origin navigation probes.
   - Non-mutating form probes.
   - Optional Playwright browser rendering and limited form submission.
   - Observed-vs-claimed mismatch summary.

7. Scoring is evidence-first:
   - Each rubric criterion performs retrieval before scoring.
   - The LLM receives allowed citation references and must cite only those references.
   - Invalid or unparsable LLM output falls back to conservative evidence-based scoring.
   - Citations are sanitized to avoid generic paper names or hallucinated references.

## Rubric

The MVP scores:

- Problem Understanding
- Technical Approach
- Implementation Quality
- Innovation / Originality
- Communication & Demo Clarity
- Claim vs Reality Alignment
- Prototype Functionality

The last two criteria make the assignment's additional considerations visible in the final JSON instead of leaving them implicit.

## Failure Handling

- Missing artefacts do not crash the pipeline; the relevant evidence is simply absent.
- Broken URLs return an explicit prototype validation failure.
- Localhost/private URLs are blocked by default. `--allow-local-url` exists only for local demo prototypes.
- If Ollama returns malformed JSON, scoring uses a conservative fallback rather than returning an unusable criterion.
- If Playwright is unavailable, static HTTP/HTML validation still runs and the browser validation field explains the limitation.

## Trade-Offs

- The vector store is in-memory to keep the MVP simple and easy to run. A production system would persist Qdrant collections and retain evaluation history.
- Prototype validation is intentionally cautious. It reports strong UI and browser signals, but does not claim full backend correctness unless observable flows complete.
- Code validation is retrieval and LLM based. It can identify likely support or gaps, but it is not a substitute for executing the submitted code or running its tests.
- The MVP favors traceability and practical robustness over perfect extraction accuracy.

## How To Demonstrate Assignment Coverage

Run a full multi-source evaluation:

```powershell
py main.py --submission-id sample1 --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --output samples/sample1/output.json
```

Run a prototype validation demo:

```powershell
cd samples/sample1/prototype
py -m http.server 8000
```

Then in another terminal:

```powershell
py main.py --submission-id sample1-url --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --url http://127.0.0.1:8000/index.html --allow-local-url --output samples/sample1/output_with_url.json
```
