import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent

DEFAULT_REPO_URL = "https://github.com/Konika-Thakur/Sutra.AI.git"
DEFAULT_DOCX = ROOT / "Sutra_AI_Overview.docx"
DEFAULT_PDF = ROOT / "Sutra_AI_Overview.pdf"
DEFAULT_PPTX = ROOT / "Sutra_AI_Overview.pptx"
DEFAULT_VIDEO = ROOT / "audio_for_test 1.mp4"
DEFAULT_CLONE_DIR = Path(tempfile.gettempdir()) / "sutra-ai-assessment" / "submission_repo"
DEFAULT_OUTPUT_DIR = ROOT / "test_outputs"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run an end-to-end assessment test with the provided Sutra.AI artefacts."
    )
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="Git repository URL to clone for code ingestion.")
    parser.add_argument("--code-dir", default=None, help="Use an existing local code directory instead of cloning.")
    parser.add_argument("--clone-dir", default=str(DEFAULT_CLONE_DIR), help="Where the Git repo should be cloned.")
    parser.add_argument("--refresh-clone", action="store_true", help="Run git pull --ff-only if the clone already exists.")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX), help="Overview DOCX path. Checked for presence only.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="PDF deck path.")
    parser.add_argument("--pptx", default=str(DEFAULT_PPTX), help="PPTX deck path.")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO), help="Demo video path.")
    parser.add_argument(
        "--deck-mode",
        choices=("pdf", "pptx", "both"),
        default="both",
        help="Which deck artefact(s) to include. Default 'both' evaluates PDF and PPTX together in one output.",
    )
    parser.add_argument("--submission-id", default="sutra-ai-assessment", help="Base submission ID for output JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated JSON outputs.")
    parser.add_argument("--url", default=None, help="Optional prototype URL to validate.")
    parser.add_argument("--allow-local-url", action="store_true", help="Allow localhost/private prototype URLs.")
    parser.add_argument(
        "--submit-prototype-forms",
        action="store_true",
        help="Allow browser validation to submit simple prototype forms with dummy data.",
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run main.py.")
    return parser.parse_args()


def run_command(command, cwd=ROOT):
    print(f"\n$ {' '.join(str(part) for part in command)}")
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def require_file(path, label):
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Missing {label}: {path}")
    return path


def prepare_code_dir(args):
    if args.code_dir:
        code_dir = Path(args.code_dir)
        if not code_dir.exists() or not code_dir.is_dir():
            raise SystemExit(f"Code directory does not exist: {code_dir}")
        return code_dir

    clone_dir = Path(args.clone_dir)
    git = shutil.which("git")
    if git is None:
        raise SystemExit("Git is required to clone the assessment repository, but it was not found on PATH.")

    if clone_dir.exists():
        if not (clone_dir / ".git").exists():
            raise SystemExit(f"Clone path exists but is not a Git repository: {clone_dir}")
        if args.refresh_clone:
            run_command([git, "-C", str(clone_dir), "pull", "--ff-only"])
        else:
            print(f"Using existing clone: {clone_dir}")
        return clone_dir

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    run_command([git, "clone", "--depth", "1", args.repo_url, str(clone_dir)])
    return clone_dir


def selected_decks(args):
    if args.deck_mode in ("pdf", "both"):
        yield Path(args.pdf)
    if args.deck_mode in ("pptx", "both"):
        yield Path(args.pptx)


def validate_output(path):
    required_keys = {"submission_id", "summary", "prototype_validation", "claim_validation", "scores"}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    missing = required_keys - set(payload)
    if missing:
        raise SystemExit(f"Output JSON is missing required keys {sorted(missing)}: {path}")
    if not isinstance(payload.get("scores"), list) or not payload["scores"]:
        raise SystemExit(f"Output JSON does not contain rubric scores: {path}")

    print(f"Validated output schema: {path}")


def run_evaluation(args, deck_paths, code_dir, video_path, output_dir):
    output_path = output_dir / f"{args.submission_id}.json"
    command = [
        args.python,
        str(ROOT / "main.py"),
        "--submission-id",
        args.submission_id,
        "--deck",
        *[str(path) for path in deck_paths],
        "--video",
        str(video_path),
        "--code",
        str(code_dir),
        "--output",
        str(output_path),
    ]

    if args.url:
        command.extend(["--url", args.url])
    if args.allow_local_url:
        command.append("--allow-local-url")
    if args.submit_prototype_forms:
        command.append("--submit-prototype-forms")

    run_command(command)
    validate_output(output_path)


def main():
    args = parse_args()

    docx_path = Path(args.docx)
    if docx_path.exists():
        print(f"DOCX found but not passed to main.py because deck ingestion supports PDF/PPTX/TXT: {docx_path}")
    else:
        print(f"DOCX not found, continuing with evaluator-supported artefacts: {docx_path}")

    video_path = require_file(Path(args.video), "video artefact")
    code_dir = prepare_code_dir(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    deck_paths = list(selected_decks(args))
    for deck_path in deck_paths:
        require_file(deck_path, f"{deck_path.suffix.upper().lstrip('.')} deck")
    run_evaluation(args, deck_paths, code_dir, video_path, output_dir)

    print("\nAssessment test completed successfully.")
    print(f"Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
