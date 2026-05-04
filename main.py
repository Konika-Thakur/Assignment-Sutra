import json
import argparse
import sys
from pathlib import Path

from ingestion import deck, video, website, code
from utils.chunker import chunk
from retrieval.store import build_store
from evaluation.claim_extractor import extract
from evaluation.validator import validate
from evaluation.scorer import score
from evaluation.summarizer import build
from evaluation.prototype_validator import validate as validate_prototype


def load_chunks(args):
    all_chunks = []

    if args.deck:
        deck_paths = args.deck if isinstance(args.deck, list) else [args.deck]
        use_source_prefix = len(deck_paths) > 1
        for deck_path in deck_paths:
            deck_chunks = deck.ingest(deck_path)
            if use_source_prefix:
                path = Path(deck_path)
                prefix = f"{path.stem}_{path.suffix.lower().lstrip('.')}"
                for item in deck_chunks:
                    item["reference"] = f"{prefix}_{item['reference']}"
            all_chunks.extend(deck_chunks)

    if args.video:
        p = Path(args.video)
        if p.suffix in (".txt", ".srt"):
            all_chunks.extend(video.ingest_transcript(args.video))
        else:
            all_chunks.extend(video.ingest(args.video))

    if args.code:
        all_chunks.extend(code.ingest(args.code))

    if args.url:
        all_chunks.extend(website.ingest(args.url, allow_local=args.allow_local_url))

    return all_chunks


def run(args):
    raw_chunks = load_chunks(args)

    if not raw_chunks:
        print("No content ingested. Check your input paths.", file=sys.stderr)
        sys.exit(1)

    chunked = chunk(raw_chunks)
    store = build_store(chunked, collection_name=args.submission_id)

    claims = extract(store)

    claim_validation = validate(claims, store)
    scores = score(store, has_prototype=bool(args.url))
    summary = build(store)
    prototype = validate_prototype(
        args.url,
        claims,
        allow_local=args.allow_local_url,
        submit_forms=args.submit_prototype_forms
    )

    output = {
        "submission_id": args.submission_id,
        "summary": summary,
        "prototype_validation": prototype,
        "claim_validation": claim_validation,
        "scores": scores
    }

    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Output written to {args.output}")
    else:
        print(json.dumps(output, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description="AI-Assisted Submission Evaluator")
    parser.add_argument("--submission-id", required=True, help="Unique ID for this submission")
    parser.add_argument(
        "--deck",
        nargs="+",
        default=None,
        help="One or more deck files (PDF, PPTX, or TXT)"
    )
    parser.add_argument("--video", default=None, help="Path to video or transcript file")
    parser.add_argument("--code", default=None, help="Path to code repository directory")
    parser.add_argument("--url", default=None, help="Prototype or website URL")
    parser.add_argument(
        "--allow-local-url",
        action="store_true",
        help="Allow localhost/private URLs for local prototype demos. Keep disabled for untrusted submissions."
    )
    parser.add_argument(
        "--submit-prototype-forms",
        action="store_true",
        help="Allow Playwright prototype validation to submit simple forms with dummy data. Use only for safe demo apps."
    )
    parser.add_argument("--output", default=None, help="Path to write JSON output")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        run(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
