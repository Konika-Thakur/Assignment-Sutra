import whisper
import os
import shutil
from pathlib import Path


def _candidate_ffmpeg_paths():
    roots = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "Microsoft" / "WinGet" / "Packages")
    roots.extend([
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
    ])

    for root in roots:
        if not root.exists():
            continue
        try:
            yield from root.rglob("ffmpeg.exe")
        except OSError:
            continue


def _ensure_ffmpeg_on_path():
    existing = shutil.which("ffmpeg")
    if existing:
        return existing

    for candidate in _candidate_ffmpeg_paths():
        ffmpeg_dir = str(candidate.parent)
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        resolved = shutil.which("ffmpeg")
        if resolved:
            return resolved

    return None


def _require_ffmpeg():
    if _ensure_ffmpeg_on_path() is None:
        raise RuntimeError(
            "Video transcription requires ffmpeg, but it was not found on PATH. "
            "Install ffmpeg, restart the terminal, or pass a .txt/.srt transcript with --video instead."
        )


def ingest(path):
    _require_ffmpeg()
    model = whisper.load_model("base")
    result = model.transcribe(str(path))
    chunks = []
    for seg in result.get("segments", []):
        text = seg["text"].strip()
        if text:
            start = round(seg["start"], 2)
            end = round(seg["end"], 2)
            chunks.append({
                "text": text,
                "source": "video",
                "reference": f"video_{start}s-{end}s"
            })
    return chunks


def ingest_transcript(path):
    text = Path(path).read_text(encoding="utf-8")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    chunks = []
    for i, line in enumerate(lines):
        chunks.append({
            "text": line,
            "source": "video",
            "reference": f"transcript_line_{i + 1}"
        })
    return chunks
