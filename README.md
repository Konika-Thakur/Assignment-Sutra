# Sutra.AI

This project evaluates a submission by reading multiple artefacts together: deck, video/transcript, code, and (optionally) a live prototype URL.

The goal is simple: generate one clean JSON report that explains what was built, validates claims with evidence, and gives rubric-based scoring.

## What this does

- Ingests deck files (`.pdf`, `.pptx`, `.txt`)
- Ingests video or transcript
- Reads a code folder/repository
- Optionally checks a prototype URL
- Produces one output JSON with summary, claim validation, and scores

## What you need

- Python 3.10+
- [Ollama](https://ollama.com/) running locally
- `llama3` model in Ollama
- `ffmpeg` (needed for MP4/audio)

Install dependencies:

```powershell
py -m pip install -r requirements.txt
ollama pull llama3
```

Windows ffmpeg install:

```powershell
winget install Gyan.FFmpeg
```

Optional (only if you want browser-based prototype validation):

```powershell
playwright install chromium
```

## Quick start

Run with sample artefacts:

```powershell
py main.py --submission-id sample1 --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --output samples/sample1/output.json
```

Run with a prototype URL:

```powershell
py main.py --submission-id sample1-url --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --url https://example.com --output samples/sample1/output_with_url.json
```

If your URL is local (`localhost` or private IP), add:

```powershell
--allow-local-url
```

## Recommended final run

For final Sutra.AI assessment output, use:

```powershell
py run_assessment_test.py --submission-id sutra-ai-assessment
```

With a prototype URL:

```powershell
py run_assessment_test.py --submission-id sutra-ai-assessment --url "https://your-sutra-ai-prototype.example"
```

## Common arguments

- `--submission-id`: unique run ID
- `--deck`: one or more deck files
- `--video`: video or transcript file
- `--code`: code directory
- `--url`: prototype URL
- `--allow-local-url`: allow localhost/private URL checks
- `--submit-prototype-forms`: submit dummy form data during browser checks
- `--output`: output JSON path

## Output format

Every run writes a JSON file containing:

- `submission_id`
- `summary`
- `prototype_validation`
- `claim_validation`
- `scores`

## Folder layout

```
Sutra.ai/
├── ingestion/
├── embedding/
├── retrieval/
├── llm/
├── evaluation/
├── utils/
├── samples/
├── main.py
└── run_assessment_test.py
```

## Notes

- Keep `--submit-prototype-forms` disabled for untrusted sites.
- Use public URLs in normal runs.
- See `DESIGN.md` for architecture and trade-offs.
