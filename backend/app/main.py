from datetime import datetime

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Finding, Project, Scan
from .scanner.pipeline import run_scan

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Code Reviewer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectIn(BaseModel):
    name: str
    repo_url: str


class FindingPatch(BaseModel):
    status: str  # open | dismissed | fixed


def _scan_out(s: Scan) -> dict:
    return {
        "id": s.id, "project_id": s.project_id, "commit_sha": s.commit_sha,
        "status": s.status, "error": s.error, "stats": s.stats or {},
        "started_at": _iso(s.started_at), "finished_at": _iso(s.finished_at),
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@app.post("/api/projects")
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    p = Project(name=body.name, repo_url=body.repo_url)
    db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name, "repo_url": p.repo_url}


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [
        {
            "id": p.id, "name": p.name, "repo_url": p.repo_url,
            "scans": [_scan_out(s) for s in sorted(p.scans, key=lambda s: s.started_at, reverse=True)],
        }
        for p in projects
    ]


@app.post("/api/projects/{project_id}/scans")
def start_scan(project_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    scan = Scan(project_id=project.id)
    db.add(scan)
    db.commit()
    background.add_task(run_scan, scan.id, project.repo_url)
    return _scan_out(scan)


@app.get("/api/scans/{scan_id}")
def get_scan(scan_id: str, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return _scan_out(scan)


@app.get("/api/scans/{scan_id}/findings")
def list_findings(
    scan_id: str,
    severity: str | None = None,
    source: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Finding).filter(Finding.scan_id == scan_id)
    if severity:
        q = q.filter(Finding.severity == severity)
    if source:
        q = q.filter(Finding.source == source)
    if status:
        q = q.filter(Finding.status == status)
    rows = q.all()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    rows.sort(key=lambda f: (order.get(f.severity, 5), f.file_path, f.line_start))
    return [
        {
            "id": f.id, "file_path": f.file_path, "language": f.language,
            "line_start": f.line_start, "line_end": f.line_end,
            "source": f.source, "rule_id": f.rule_id, "severity": f.severity,
            "category": f.category, "title": f.title, "explanation": f.explanation,
            "suggested_fix": f.suggested_fix, "confidence": f.confidence,
            "fingerprint": f.fingerprint, "status": f.status,
        }
        for f in rows
    ]


@app.patch("/api/findings/{finding_id}")
def patch_finding(finding_id: str, body: FindingPatch, db: Session = Depends(get_db)):
    if body.status not in {"open", "dismissed", "fixed"}:
        raise HTTPException(422, "status must be open, dismissed, or fixed")
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    f.status = body.status
    db.commit()
    return {"id": f.id, "status": f.status}


@app.delete("/api/scans/{scan_id}")
def delete_scan(scan_id: str, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    db.delete(scan)
    db.commit()
    return {"id": scan_id, "deleted": True}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    db.delete(project)
    db.commit()
    return {"id": project_id, "deleted": True}
