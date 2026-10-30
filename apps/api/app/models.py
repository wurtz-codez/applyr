from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now():
    return datetime.now(UTC)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    canonical_url: Mapped[str] = mapped_column(String(2000), unique=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    company: Mapped[str | None] = mapped_column(String(300), index=True)
    location: Mapped[str | None] = mapped_column(String(500), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    work_mode: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True)
    employment_type: Mapped[str | None] = mapped_column(String(80), index=True)
    experience_level: Mapped[str | None] = mapped_column(String(80))
    salary_min: Mapped[float | None]
    salary_max: Mapped[float | None]
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(20))
    salary_text: Mapped[str | None] = mapped_column(String(500))
    listing_type: Mapped[str] = mapped_column(String(30), default="JOB_POSTING", index=True)
    enrichment_status: Mapped[str] = mapped_column(String(50), default="NOT_NEEDED")
    primary_source: Mapped[str] = mapped_column(String(30))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    content_hash: Mapped[str] = mapped_column(String(64))


class JobTag(Base):
    __tablename__ = "job_tags"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)


class JobSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("job_id", "provider"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    source_url: Mapped[str] = mapped_column(String(2000))
    external_id: Mapped[str | None] = mapped_column(String(200))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    query: Mapped[str] = mapped_column(String(500), default="")
    providers_json: Mapped[list] = mapped_column(JSON)
    results_json: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))


class RunLock(Base):
    __tablename__ = "run_lock"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("discovery_runs.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceState(Base):
    __tablename__ = "source_states"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    next_allowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))


class SearchAttempt(Base):
    __tablename__ = "search_attempts"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
