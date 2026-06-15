# Reviewbench

A web app that scans a codebase, finds bugs and best-practice violations, and
suggests fixes. Two analysis engines run on every scan:

- **Semgrep** (deterministic) — multi-language static analysis with `--config auto`
- **Claude** (semantic) — logic bugs, edge cases, and design issues static
  analysis can't see, returned as structured findings with unified-diff fixes

Findings are fingerprinted (`rule + file + normalized snippet`, line numbers
excluded) so duplicates collapse, the same issue is recognized across scans,
and dismissals carry forward automatically.

## Quick start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install semgrep            # optional but recommended
cp .env.example .env           # add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload  # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173 (proxies /api to :8000)
```

Add a project with a git URL (`https://github.com/you/repo.git`) or a local
directory path (handy for testing), hit Scan, and watch findings stream in.

## How a scan works

1. API enqueues a scan; a background task shallow-clones the repo
2. Files are walked (skipping `node_modules`, lockfiles, binaries, >300 KB files)
3. Semgrep runs across the whole tree
4. The largest `LLM_MAX_FILES` files go to Claude, chunked at 250 lines with
   overlap, along with Semgrep's findings so the model doesn't repeat them
5. Everything is fingerprinted, deduped (deterministic findings win ties),
   filtered by `LLM_MIN_CONFIDENCE`, and persisted
6. The dashboard polls scan status and renders findings worst-first

## Cost controls

- `LLM_MAX_FILES` caps how many files reach the API per scan
- `LLM_MIN_CONFIDENCE` drops low-confidence LLM findings
- `REVIEW_MODEL` lets you trade cost for depth (see
  https://docs.claude.com/en/api/overview for current models and pricing)

## Production upgrade path

This starter favors zero-setup: SQLite + FastAPI BackgroundTasks. When you
outgrow it:

- **Database**: set `DATABASE_URL` to Postgres — the SQLAlchemy models and
  indexes are already written for it
- **Queue**: move `run_scan` into a Celery/RQ worker behind Redis so scans
  survive restarts and run in parallel
- **Realtime**: swap dashboard polling for WebSockets/SSE
- **Auth**: add user accounts before exposing this beyond localhost — the API
  currently trusts everyone, and scanning arbitrary git URLs server-side
  should be restricted to trusted users
