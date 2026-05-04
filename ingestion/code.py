from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".sh", ".yml", ".yaml", ".json",
    ".toml", ".md", ".txt", ".sql", ".html", ".css"
}

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv",
    "venv", "dist", "build", ".idea", ".vscode"
}


def ingest(repo_path):
    root = Path(repo_path)
    chunks = []

    for filepath in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in filepath.parts):
            continue
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            continue

        if not content:
            continue

        relative = str(filepath.relative_to(root))
        chunks.append({
            "text": content,
            "source": "code",
            "reference": relative
        })

    return chunks
