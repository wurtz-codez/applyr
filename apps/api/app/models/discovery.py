from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.profile import json_type


def utcnow():
    return datetime.now(UTC)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats_provider", "board_token"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    ats_provider: Mapped[str] = mapped_column(String(30), default="greenhouse")
    board_token: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("company_id", "external_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    location_text: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(String(1000))
    description_text: Mapped[str] = mapped_column(Text)
    description_hash: Mapped[str] = mapped_column(String(64))
    description_truncated: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    missed_scans: Mapped[int] = mapped_column(default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", "cache_key"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    cache_key: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[int]
    job_hash: Mapped[str] = mapped_column(String(64))
    job_status: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(30))
    model_id: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(30))
    result_json: Mapped[dict] = mapped_column(json_type)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Shortlist(Base):
    __tablename__ = "shortlists"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    agent_type: Mapped[str] = mapped_column(String(30), default="discovery")
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    result_json: Mapped[dict] = mapped_column(json_type, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiscoveryLease(Base):
    __tablename__ = "discovery_leases"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "sha256", name="uq_resumes_user_hash"),
        UniqueConstraint("user_id", "version", name="uq_resumes_user_version"),
        Index(
            "uq_resumes_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    original_filename: Mapped[str] = mapped_column(String(200))
    file_key: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    version: Mapped[int]
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    resume_id: Mapped[UUID | None] = mapped_column(ForeignKey("resumes.id"))
    status: Mapped[str] = mapped_column(String(30), default="APPLIED")
    notes: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
