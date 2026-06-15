"""Scan pipeline: acquire repo -> semgrep -> LLM review -> dedupe -> persist."""

import os
import time
from datetime import datetime, timezone

from openai import OpenAI

from ..database import SessionLocal
from ..models import Finding, Scan
from .llm_reviewer import review_file
from .repo import acquire_repo, fingerprint, iter_source_files, snippet_for
from .semgrep_runner import run_semgrep, semgrep_available

LLM_MAX_FILES = int(os.getenv("LLM_MAX_FILES", "25"))

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def run_scan(scan_id: str, repo_url: str) -> None:
    db = SessionLocal()
    scan = db.get(Scan, scan_id)
    if scan is None:
        db.close()
        return

    t0 = time.time()
    try:
        scan.status = "cloning"
        db.commit()
        repo_dir, sha = acquire_repo(repo_url)
        scan.commit_sha = sha
        scan.status = "analyzing"
        db.commit()

        files = list(iter_source_files(repo_dir))
        contents = {path: content for path, _, content in files}

        # Initialize with progress tracking
        scan.stats = {
            "files_scanned": len(files),
            "llm_files_reviewed": 0,
            "llm_total_files": 0,
            "llm_progress_percent": 0,
            "estimated_remaining_seconds": 0,
            "current_file": "Running Semgrep analysis...",
        }
        db.commit()

        raw_findings = run_semgrep(repo_dir)

        api_key = os.getenv("OPENROUTER_API_KEY")
        llm_files_reviewed = 0
        if api_key:
            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            # Cost cap: largest files first — they tend to hold the most logic.
            ranked = sorted(files, key=lambda f: len(f[2]), reverse=True)[:LLM_MAX_FILES]
            total_files = len(ranked)
            
            llm_start_time = time.time()
            
            for idx, (path, lang, content) in enumerate(ranked):
                # Progress before file review
                elapsed = time.time() - llm_start_time
                if elapsed > 0 and idx > 0:
                    files_per_sec = idx / elapsed
                    remaining_files = total_files - idx
                    estimated_remaining = int(remaining_files / files_per_sec) if files_per_sec > 0 else 0
                else:
                    estimated_remaining = 0
                
                progress = int((idx / total_files) * 100) if total_files > 0 else 0
                
                # Update BEFORE processing file
                scan.stats = {
                    "files_scanned": len(files),
                    "llm_files_reviewed": idx,
                    "llm_total_files": total_files,
                    "llm_progress_percent": progress,
                    "estimated_remaining_seconds": estimated_remaining,
                    "current_file": path,
                }
                db.commit()
                
                raw_findings.extend(review_file(client, path, lang, content, raw_findings))
                llm_files_reviewed = idx + 1
                
                # Update AFTER processing file (progress moves forward)
                elapsed = time.time() - llm_start_time
                if elapsed > 0 and idx > 0:
                    files_per_sec = (idx + 1) / elapsed
                    remaining_files = total_files - idx - 1
                    estimated_remaining = int(remaining_files / files_per_sec) if files_per_sec > 0 else 0
                else:
                    estimated_remaining = 0
                
                progress = int(((idx + 1) / total_files) * 100) if total_files > 0 else 100
                
                scan.stats = {
                    "files_scanned": len(files),
                    "llm_files_reviewed": idx + 1,
                    "llm_total_files": total_files,
                    "llm_progress_percent": progress,
                    "estimated_remaining_seconds": estimated_remaining,
                    "current_file": path,
                }
                db.commit()

        # Fingerprint + dedupe (semgrep wins ties since it's deterministic).
        seen: dict[str, dict] = {}
        for f in raw_findings:
            snip = snippet_for(contents.get(f["file_path"], ""), f["line_start"], f["line_end"])
            fp = fingerprint(f.get("rule_id") or f["category"], f["file_path"], snip or f["title"])
            if fp in seen and f["source"] == "llm":
                continue
            f["fingerprint"] = fp
            seen[fp] = f

        # Carry forward dismissals from this project's previous scan.
        dismissed = _previously_dismissed(db, scan)
        for f in seen.values():
            status = "dismissed" if f["fingerprint"] in dismissed else "open"
            db.add(Finding(scan_id=scan.id, status=status, **f))

        by_severity: dict[str, int] = {}
        for f in seen.values():
            by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

        scan.stats = {
            "files_scanned": len(files),
            "llm_files_reviewed": llm_files_reviewed,
            "semgrep_used": semgrep_available(),
            "findings_total": len(seen),
            "by_severity": by_severity,
            "duration_seconds": round(time.time() - t0, 1),
        }
        scan.status = "completed"
    except Exception as exc:  # surface the failure to the dashboard
        scan.status = "failed"
        scan.error = str(exc)[:2000]
    finally:
        scan.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()


def _previously_dismissed(db, scan: Scan) -> set[str]:
    prev = (
        db.query(Scan)
        .filter(Scan.project_id == scan.project_id, Scan.id != scan.id, Scan.status == "completed")
        .order_by(Scan.started_at.desc())
        .first()
    )
    if prev is None:
        return set()
    rows = db.query(Finding.fingerprint).filter(
        Finding.scan_id == prev.id, Finding.status == "dismissed"
    ).all()
    return {r[0] for r in rows}
