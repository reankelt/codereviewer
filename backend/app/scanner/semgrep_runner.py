"""Deterministic analysis via Semgrep (optional dependency)."""

import json
import shutil
import subprocess
from pathlib import Path

SEVERITY_MAP = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}


def semgrep_available() -> bool:
    return shutil.which("semgrep") is not None


def run_semgrep(repo_dir: Path) -> list[dict]:
    """Run `semgrep --config auto` and normalize results.

    Returns a list of finding dicts; empty list if semgrep is missing or fails
    (the scan still proceeds with LLM review only).
    """
    if not semgrep_available():
        return []
    try:
        proc = subprocess.run(
            ["semgrep", "--config", "auto", "--json", "--quiet", "--timeout", "120", str(repo_dir)],
            capture_output=True, text=True, timeout=900,
        )
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return []

    findings = []
    for r in data.get("results", []):
        path = r.get("path", "")
        rel = str(Path(path).resolve().relative_to(repo_dir.resolve())) if path else ""
        extra = r.get("extra", {})
        meta = extra.get("metadata", {})
        category = "security" if "security" in str(meta.get("category", "")).lower() else "best_practice"
        findings.append({
            "file_path": rel,
            "line_start": r.get("start", {}).get("line", 1),
            "line_end": r.get("end", {}).get("line", 1),
            "source": "semgrep",
            "rule_id": r.get("check_id"),
            "severity": SEVERITY_MAP.get(extra.get("severity", "INFO"), "low"),
            "category": category,
            "title": (extra.get("message") or r.get("check_id") or "Semgrep finding").split("\n")[0][:300],
            "explanation": extra.get("message", ""),
            "suggested_fix": extra.get("fix"),
            "confidence": None,
        })
    return findings
