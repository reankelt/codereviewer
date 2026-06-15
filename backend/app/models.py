import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    repo_url: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    scans: Mapped[list["Scan"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (Index("ix_scans_project_started", "project_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # queued | cloning | analyzing | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    project: Mapped[Project] = relationship(back_populates="scans")
    findings: Mapped[list["Finding"]] = relationship(back_populates="scan", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_scan_severity", "scan_id", "severity"),
        Index("ix_findings_fingerprint", "fingerprint"),
        Index("uq_findings_scan_fp", "scan_id", "fingerprint", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"))
    file_path: Mapped[str] = mapped_column(String(500))
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    line_start: Mapped[int] = mapped_column(Integer, default=1)
    line_end: Mapped[int] = mapped_column(Integer, default=1)
    # semgrep | llm
    source: Mapped[str] = mapped_column(String(20))
    rule_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # critical | high | medium | low | info
    severity: Mapped[str] = mapped_column(String(10), default="info")
    # bug | security | performance | style | best_practice
    category: Mapped[str] = mapped_column(String(20), default="best_practice")
    title: Mapped[str] = mapped_column(String(300))
    explanation: Mapped[str] = mapped_column(Text, default="")
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    # open | dismissed | fixed
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    scan: Mapped[Scan] = relationship(back_populates="findings")
