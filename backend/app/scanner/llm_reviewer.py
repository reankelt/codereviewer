"""Semantic review via OpenRouter (GPT-4o mini).

Each file (or chunk of a large file) is sent with any existing deterministic
findings so the model focuses on what static analysis can't see: logic bugs,
edge cases, and design problems. Output is strict JSON.
"""

import json
import os
import re

from openai import OpenAI

MODEL = os.getenv("REVIEW_MODEL", "openai/gpt-4o-mini")
MIN_CONFIDENCE = float(os.getenv("LLM_MIN_CONFIDENCE", "0.5"))
CHUNK_LINES = 250
CHUNK_OVERLAP = 25

SYSTEM_PROMPT = """You are a precise senior code reviewer. You will receive one source file \
(or a chunk of one, with its starting line number) and a list of issues already found by \
static analysis. Find REAL problems static analysis cannot: logic bugs, off-by-one errors, \
unhandled edge cases, race conditions, resource leaks, incorrect error handling, security \
flaws, and significant best-practice violations. Do NOT repeat the static analysis findings. \
Do NOT report stylistic nitpicks or speculative issues.

Respond with ONLY a JSON array (no markdown fences, no prose). Each element:
{
  "line_start": <int, absolute line number in the original file>,
  "line_end": <int>,
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "category": "bug" | "security" | "performance" | "style" | "best_practice",
  "title": "<one short sentence>",
  "explanation": "<why this is a problem, 1-3 sentences>",
  "suggested_fix": "<a unified diff for the fix, or null if not applicable>",
  "confidence": <float 0-1, how sure you are this is a real issue>
}
Return [] if the code is fine. Quality over quantity: 0-5 findings per file is typical."""


def _chunks(content: str) -> list[tuple[int, str]]:
    """Split big files into (start_line, text) windows with overlap."""
    lines = content.splitlines()
    if len(lines) <= CHUNK_LINES:
        return [(1, content)]
    out, i = [], 0
    while i < len(lines):
        window = lines[i:i + CHUNK_LINES]
        out.append((i + 1, "\n".join(window)))
        i += CHUNK_LINES - CHUNK_OVERLAP
    return out


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return []


def review_file(client: OpenAI, file_path: str, language: str,
                content: str, known_findings: list[dict]) -> list[dict]:
    known = [
        {"line": f["line_start"], "title": f["title"]}
        for f in known_findings if f["file_path"] == file_path
    ]
    findings: list[dict] = []

    for start_line, chunk in _chunks(content):
        numbered = "\n".join(
            f"{start_line + i:>5} | {line}"
            for i, line in enumerate(chunk.splitlines())
        )
        user_msg = (
            f"File: {file_path} (language: {language})\n"
            f"Chunk starts at line {start_line}.\n"
            f"Already found by static analysis (do not repeat): {json.dumps(known)}\n\n"
            f"{numbered}"
        )
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.choices[0].message.content
        except Exception:
            continue

        for item in _parse_json_array(raw):
            try:
                conf = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            if conf < MIN_CONFIDENCE:
                continue
            findings.append({
                "file_path": file_path,
                "line_start": int(item.get("line_start", start_line)),
                "line_end": int(item.get("line_end", item.get("line_start", start_line))),
                "source": "llm",
                "rule_id": None,
                "severity": item.get("severity", "info"),
                "category": item.get("category", "best_practice"),
                "title": str(item.get("title", "Review finding"))[:300],
                "explanation": str(item.get("explanation", "")),
                "suggested_fix": item.get("suggested_fix"),
                "confidence": conf,
            })
    return findings
