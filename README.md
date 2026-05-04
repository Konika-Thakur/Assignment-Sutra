<<<<<<< HEAD
# AI-Assisted Evaluation MVP

Evaluates multi-artefact submissions by ingesting a deck, video or transcript, code repository, and optional prototype URL. It extracts evidence, validates claims across artefacts, checks live prototype signals, and produces rubric-based JSON scores grounded in retrieved source references.


## Requirements

- Python 3.10+
- Ollama installed and running locally with llama3 pulled
- ffmpeg installed and available on PATH for MP4/video transcription

```powershell
ollama pull llama3
```


Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

On Windows, install ffmpeg before using `--video` with MP4/audio files:

```powershell
winget install Gyan.FFmpeg
```

For browser-based prototype validation:

```powershell
playwright install chromium
```


## Project Structure

eval_system/
├── ingestion/
│   ├── deck.py          # Extracts text from PDF or PPTX
│   ├── video.py         # Transcribes video or reads transcript file
│   ├── website.py       # Crawls and extracts text from a URL
│   └── code.py          # Reads source files from a repository directory
├── embedding/
│   └── embed.py         # HuggingFace MiniLM embeddings via LangChain
├── retrieval/
│   └── store.py         # Qdrant in-memory vector store with search
├── llm/
│   └── ollama_client.py # LangChain Ollama LLM wrapper
├── evaluation/
│   ├── claim_extractor.py     # Extracts claims from all indexed sources
│   ├── validator.py           # Validates each claim against retrieved evidence
│   ├── scorer.py              # Scores submission on rubric criteria and extra alignment checks
│   ├── summarizer.py          # Builds unified submission summary
│   └── prototype_validator.py # Checks URL accessibility and detects UI features
├── utils/
│   └── chunker.py       # Splits large text chunks into smaller pieces
├── samples/
│   ├── sample1/         # MediTrack - health management app
│   └── sample2/         # EduBot - AI tutoring platform
├── main.py              # CLI entry point
└── requirements.txt


## Usage

Evaluate a full sample with deck, transcript, and code:

```powershell
py main.py --submission-id sample1 --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --output samples/sample1/output.json
```

Evaluate with a local prototype URL:

```powershell
cd samples/sample1/prototype
py -m http.server 8000
```

In another terminal:

```powershell
py main.py --submission-id sample1-url --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --url http://127.0.0.1:8000/index.html --allow-local-url --output samples/sample1/output_with_url.json
```

For untrusted or public submissions, do not pass `--allow-local-url`; the default URL guard blocks private and localhost addresses.

Run the final unified assessment with the provided Git repo, PDF deck, PPTX deck, and MP4 demo video:

```powershell
py run_assessment_test.py --submission-id sutra-ai-assessment
```

This is the recommended final output for assessment accuracy because it evaluates one submission by comparing PDF deck + PPTX deck + video + GitHub code in a single run and writes `test_outputs/sutra-ai-assessment.json`. Add `--url` only when the prototype URL belongs to the same Sutra.AI submission:

```powershell
py run_assessment_test.py --submission-id sutra-ai-assessment --url "https://your-sutra-ai-prototype.example"
```

Do not use the bundled MediTrack sample prototype as the Sutra.AI prototype; it is only for demonstrating URL validation.

To clone or refresh the GitHub repo before the final run:

```powershell
py run_assessment_test.py --refresh-clone
```

For a full pipeline demo that also exercises local URL validation:

```powershell
.\run_test.ps1
```

It runs:

```powershell
git clone --depth 1 https://github.com/Konika-Thakur/Sutra.AI.git "$env:TEMP\sutra-ai-assessment\submission_repo"

py "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\main.py" --submission-id TEST1 --deck "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\Sutra_AI_Overview.pdf" --video "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\audio_for_test 1.mp4" --code "$env:TEMP\sutra-ai-assessment\submission_repo" --url "http://127.0.0.1:8000/index.html" --allow-local-url --output "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\test_outputs\TEST1_output.json"
```

If no prototype URL is passed, `run_test.ps1` starts the bundled sample prototype on `http://127.0.0.1:8000/index.html` and validates it. This proves the URL validator works, but it should not be used as the final Sutra.AI accuracy run. To validate a different live prototype:

```powershell
.\run_test.ps1 -PrototypeUrl "https://your-prototype-url.example"
```

The script uses these defaults:

- Git repo: `https://github.com/Konika-Thakur/Sutra.AI.git`
- PDF deck: `C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\Sutra_AI_Overview.pdf`
- PPTX deck: `C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\Sutra_AI_Overview.pptx`
- DOCX overview: `C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\Sutra_AI_Overview.docx` checked for presence only
- Demo video: `C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\audio_for_test 1.mp4`
- Temporary cloned repo: `%TEMP%\sutra-ai-assessment\submission_repo`
- Output folder: `test_outputs/`

Use only one deck format if you need to isolate parser behavior:

```powershell
py run_assessment_test.py --deck-mode pdf
py run_assessment_test.py --deck-mode pptx
```

If the repository was already cloned by the script, refresh it before running:

```powershell
py run_assessment_test.py --refresh-clone
```

Generic command:

```powershell
py main.py --submission-id S1 --deck samples/sample1/deck.txt --video samples/sample1/transcript.txt --code samples/sample1/code --url https://example.com --output output.json
```

Unix/macOS style:

```bash
python main.py \
  --submission-id S1 \
  --deck samples/sample1/deck.txt \
  --video samples/sample1/transcript.txt \
  --code samples/sample1/code \
  --url https://example.com \
  --output samples/sample1/output.json
```


All arguments except `--submission-id` are optional. The system handles missing artefacts gracefully.


## Arguments

| Argument | Description |
|---|---|
| `--submission-id` | Unique identifier for the submission (required) |
| `--deck` | Path to deck file (PDF or PPTX or TXT) |
| `--video` | Path to video file or plain text transcript |
| `--code` | Path to code repository directory |
| `--url` | Prototype or website URL |
| `--allow-local-url` | Allows localhost/private URLs for local demos only |
| `--submit-prototype-forms` | Allows browser validation to submit simple forms with dummy data; use only for safe demo apps |
| `--output` | Path to write JSON output (prints to stdout if omitted) |



## Output Format

```json
{
  "submission_id": "S1",
  "summary": {
    "problem": "...",
    "solution": "...",
    "features": [],
    "implementation_depth": "...",
    "gaps": []
  },
  "prototype_validation": {
    "url": "...",
    "accessible": true,
    "status_code": 200,
    "features_detected": [],
    "summary": "...",
    "functional_validation": {
      "functional_summary": "...",
      "observed_features": [],
      "missing_or_unverified_claims": [],
      "core_flows": [],
      "data_processing_signals": [],
      "confidence": 0.7
    },
    "observed_vs_claimed_mismatch": {
      "claimed_features_count": 4,
      "observed_features": [],
      "missing_or_unverified_claims": [],
      "has_mismatch": false
    }
  },
  "claim_validation": [
    {
      "claim": "...",
      "type": "feature",
      "status": "supported",
      "reasoning": "...",
      "confidence": 0.87,
      "citations": ["slide_4", "code/main.py"]
    }
  ],
  "scores": [
    {
      "criterion": "Technical Approach",
      "score": 4,
      "reasoning": "...",
      "citations": ["slide_5", "code/risk.py"],
      "confidence": 0.85,
      "evidence_count": 6
    }
  ]
}
```

---

## Rubric Criteria

1. Problem Understanding
2. Technical Approach
3. Implementation Quality
4. Innovation / Originality
5. Communication & Demo Clarity
6. Claim vs Reality Alignment
7. Prototype Functionality

Scores range from 1 (very weak) to 5 (excellent). Every score includes reasoning, citations, and a confidence value.

---

## Design Notes

- All scoring is grounded in retrieved evidence from the vector store. No score is generated without a retrieval step.
- Claim validation uses LLM reasoning over source-separated retrieved chunks, not only similarity thresholds.
- Citations are sanitized so outputs refer only to retrieved evidence references such as `slide_3`, `transcript_line_2`, `detector.py`, or a URL.
- Missing artefacts are handled without errors. Broken URLs are reported in prototype validation and claim/prototype mismatch fields.
- Browser validation does not submit forms by default. Use `--submit-prototype-forms` only for safe demo apps where dummy submissions are acceptable.
- The vector store is in-memory (Qdrant). Each run creates a fresh collection keyed by submission ID.
- LLM calls use Ollama locally. No external API keys required.

See `DESIGN.md` for the full architecture note, limitations, and practical trade-offs.


py main.py --submission-id sutra-ai-final --deck "C:\Program Files(1)(x86)\Sutra_AI_Overview.pdf" --video "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\audio_for_test 1.mp4" --code "C:\Users\creno\AppData\Local\Temp\sutra-ai-assessment\submission_repo" --output "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI\test_outputs\sutra-ai-final.json"
=======
# Sutra.AI
>>>>>>> 026694d07db18375e4ebc1e5118eaaab34dccfcd
