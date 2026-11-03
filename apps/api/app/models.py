from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now():
    return datetime.now(UTC)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "india_status IN ('CONFIRMED', 'NOT_ELIGIBLE', 'UNCERTAIN')",
            name="ck_jobs_india_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    india_status: Mapped[str] = mapped_column(
        String(20), default="UNCERTAIN", server_default="UNCERTAIN", index=True
    )
    eligibility_reason: Mapped[str | None] = mapped_column(String(200))
    eligibility_evidence: Mapped[dict | None] = mapped_column(JSON)
    eligibility_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligibility_method: Mapped[str | None] = mapped_column(String(80))
    eligibility_confidence: Mapped[float | None]
    normalization_version: Mapped[int] = mapped_column(default=0, server_default="0", index=True)
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
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    apply_url: Mapped[str | None] = mapped_column(String(2000), index=True)
    original_job_url: Mapped[str | None] = mapped_column(String(2000))
    normalized_json: Mapped[dict | None] = mapped_column(JSON)
    experience_min: Mapped[int | None] = mapped_column(index=True)
    experience_max: Mapped[int | None]
    india_eligible: Mapped[bool | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    valid_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ats_identity: Mapped[str | None] = mapped_column(String(500), unique=True)
    requisition_id: Mapped[str | None] = mapped_column(String(200), index=True)


class JobTag(Base):
    __tablename__ = "job_tags"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)


class JobSource(Base):
    __tablename__ = "job_source_occurrences"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("job_sources.id"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    ats_identity: Mapped[str | None] = mapped_column(String(500), index=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True)

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


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(300))
    website: Mapped[str | None] = mapped_column(String(2000), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IngestionSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("provider", "board_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(300))
    career_url: Mapped[str | None] = mapped_column(String(2000))
    provider: Mapped[str] = mapped_column(String(30), index=True)
    board_id: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(30), default="ats")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
    access_policy: Mapped[str] = mapped_column(String(30))
    permission_notes: Mapped[str | None] = mapped_column(Text)
    fetch_interval_seconds: Mapped[int] = mapped_column(default=21600)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_count: Mapped[int] = mapped_column(default=0)
    health: Mapped[str] = mapped_column(String(30), default="unverified")
    seed_defaults: Mapped[dict | None] = mapped_column(JSON)
    local_overrides: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    sync_state: Mapped[dict] = mapped_column(JSON, default=dict)
    active_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("job_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched: Mapped[int] = mapped_column(default=0)
    inserted: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    deduplicated: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)


class MatchingProfile(Base):
    __tablename__ = "matching_profiles"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_key: Mapped[str] = mapped_column(String(200), unique=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(default=True)
    needs_refresh: Mapped[bool] = mapped_column(default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobMatch(Base):
    __tablename__ = "job_matches"
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("matching_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(index=True)
    reasons: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MaintenanceState(Base):
    """Durable, shared leases for bounded global maintenance tasks."""

    __tablename__ = "ingestion_maintenance"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(default=0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
