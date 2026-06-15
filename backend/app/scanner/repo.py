"""Repo ingestion and shared scanning utilities."""

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "vendor", "__pycache__",
    ".venv", "venv", ".next", "target", ".idea", ".vscode", "coverage",
}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "go.sum", "composer.lock",
}

LANGUAGE_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".rb": "ruby", ".java": "java", ".kt": "kotlin", ".rs": "rust",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".cs": "csharp", ".php": "php", ".swift": "swift", ".scala": "scala",
    ".sh": "shell", ".bash": "shell", ".sql": "sql", ".tf": "terraform",
    ".yaml": "yaml", ".yml": "yaml",
}

MAX_FILE_BYTES = 300_000


def acquire_repo(repo_url: str) -> tuple[Path, str | None]:
    """Clone a git URL (shallow) or accept a local directory path.

    Returns (repo_dir, commit_sha).
    """
    local = Path(repo_url).expanduser()
    if local.is_dir():
        sha = _git_sha(local)
        return local, sha

    tmp = Path(tempfile.mkdtemp(prefix="scan_"))
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(tmp / "repo")],
        check=True, capture_output=True, timeout=300,
    )
    repo_dir = tmp / "repo"
    return repo_dir, _git_sha(repo_dir)


def _git_sha(repo_dir: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir,
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip()[:40] or None
    except Exception:
        return None


def iter_source_files(repo_dir: Path):
    """Yield (relative_path, language, content) for analyzable files."""
    for path in sorted(repo_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        lang = LANGUAGE_BY_EXT.get(path.suffix.lower())
        if lang is None:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        yield str(path.relative_to(repo_dir)), lang, content


def fingerprint(rule_or_category: str, file_path: str, snippet: str) -> str:
    """Stable identity for a finding across scans.

    Line numbers are deliberately excluded and whitespace is normalized so the
    same issue maps to the same fingerprint after unrelated edits shift lines.
    """
    normalized = re.sub(r"\s+", " ", snippet).strip()[:400]
    raw = f"{rule_or_category}|{file_path}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snippet_for(content: str, line_start: int, line_end: int) -> str:
    lines = content.splitlines()
    lo = max(0, line_start - 1)
    hi = min(len(lines), max(line_end, line_start))
    return "\n".join(lines[lo:hi])
