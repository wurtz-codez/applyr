import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Engine, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.integrations.ats.greenhouse import SourceError, fetch_jobs
from app.models.discovery import AgentRun, Company, DiscoveryLease, Job
from app.models.profile import LOCAL_USER_ID, Profile
from app.services.matching import evaluate

logger = logging.getLogger(__name__)


def create_run(session: Session, use_ai: bool = True) -> AgentRun:
    profile = session.scalar(select(Profile).where(Profile.user_id == LOCAL_USER_ID))
    if profile is None or not profile.facts_json:
        raise HTTPException(409, "Create a verified profile with at least one fact first")
    sources = session.scalars(select(Company).where(Company.enabled.is_(True))).all()
    if not sources:
        raise HTTPException(409, "Add and enable at least one Greenhouse company board in Settings")
    now = datetime.now(UTC)
    previous = session.get(DiscoveryLease, 1)
    previous_id = previous.run_id if previous else None
    run = AgentRun(
        result_json={"source_ids": [str(s.id) for s in sources], "use_ai": use_ai, "sources": []}
    )
    session.add(run)
    session.flush()
    acquired = session.execute(
        update(DiscoveryLease)
        .where(
            DiscoveryLease.id == 1,
            or_(DiscoveryLease.run_id.is_(None), DiscoveryLease.expires_at < now),
        )
        .values(run_id=run.id, expires_at=now + timedelta(minutes=20))
        .execution_options(synchronize_session=False)
    )
    if acquired.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Discovery is already running. Check Runs for progress.")
    if previous_id:
        session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == previous_id,
                AgentRun.status.in_(["QUEUED", "RUNNING"]),
            )
            .values(status="INTERRUPTED", error_code="RUN_LEASE_EXPIRED", finished_at=now)
        )
    session.commit()
    session.refresh(run)
    return run


def finish_run(session: Session, run_id: UUID, status: str, error: str | None = None):
    run = session.get(AgentRun, run_id)
    if run:
        run.status, run.error_code, run.finished_at = status, error, datetime.now(UTC)
    session.execute(
        update(DiscoveryLease)
        .where(
            DiscoveryLease.id == 1,
            DiscoveryLease.run_id == run_id,
        )
        .values(run_id=None, expires_at=None)
    )
    session.commit()


def ingest_source(session: Session, source: Company, normalized, invalid: int) -> dict:
    now = datetime.now(UTC)
    known = {
        row.external_id: row
        for row in session.scalars(select(Job).where(Job.company_id == source.id))
    }
    counts = {
        "fetched": len(normalized),
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "closed": 0,
        "invalid": invalid,
    }
    seen = set()
    for item in normalized:
        seen.add(item.external_id)
        row = known.get(item.external_id)
        if row is None:
            row = Job(company_id=source.id, external_id=item.external_id, first_seen_at=now)
            session.add(row)
            counts["new"] += 1
        elif row.description_hash != item.description_hash or row.status != "OPEN":
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
        row.title, row.location_text, row.source_url = (
            item.title,
            item.location_text,
            item.source_url,
        )
        row.description_text, row.description_hash = item.description_text, item.description_hash
        row.description_truncated = item.description_truncated
        row.status, row.last_seen_at, row.missed_scans = "OPEN", now, 0
    # Partial/corrupt snapshots must never be interpreted as closure evidence.
    if invalid == 0:
        for key, row in known.items():
            if key not in seen and row.status == "OPEN":
                row.missed_scans += 1
                if row.missed_scans >= 3:
                    row.status = "CLOSED"
                    counts["closed"] += 1
    session.commit()
    return counts


def execute_run(run_id: UUID | str, engine: Engine | None = None):
    run_id = UUID(str(run_id))
    with Session(engine or get_engine()) as session:
        claimed = session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status == "QUEUED",
            )
            .values(status="RUNNING")
        )
        if claimed.rowcount != 1:
            session.rollback()
            return
        session.commit()
        run = session.get(AgentRun, run_id)
        metadata = dict(run.result_json)
        progress, ai_requests, failures = [], 0, 0
        try:
            for source_id in metadata["source_ids"]:
                lease = session.get(DiscoveryLease, 1, populate_existing=True)
                if lease.run_id != run_id or lease.expires_at.replace(tzinfo=UTC) < datetime.now(
                    UTC
                ):
                    finish_run(session, run_id, "INTERRUPTED", "RUN_LEASE_EXPIRED")
                    return
                source = session.get(Company, UUID(source_id))
                if source is None or not source.enabled:
                    continue
                item = {"company": source.name, "source_id": source_id}
                try:
                    jobs, invalid = fetch_jobs(source.board_token)
                    item.update(ingest_source(session, source, jobs, invalid))
                    item["status"] = "PARTIAL" if invalid else "SUCCEEDED"
                    failures += bool(invalid)
                    # Cache avoids rescoring unchanged source jobs, including closed listings.
                    source_jobs = session.scalars(
                        select(Job).where(Job.company_id == source.id)
                    ).all()
                    for job in source_jobs:
                        profile = session.scalar(
                            select(Profile).where(Profile.user_id == LOCAL_USER_ID)
                        )
                        if profile is None:
                            raise SourceError("PROFILE_UNAVAILABLE")
                        _, requested = evaluate(
                            session,
                            job,
                            profile,
                            use_ai=bool(metadata["use_ai"])
                            and ai_requests < get_settings().ai_max_jobs_per_run,
                        )
                        ai_requests += requested
                        session.commit()
                except SourceError as error:
                    session.rollback()
                    failures += 1
                    item.update(status="FAILED", error_code=str(error))
                progress.append(item)
                run = session.get(AgentRun, run_id)
                run.result_json = {
                    **metadata,
                    "sources": progress.copy(),
                    "ai_requests": ai_requests,
                }
                session.commit()
            succeeded = sum(item.get("status") in {"SUCCEEDED", "PARTIAL"} for item in progress)
            status = "SUCCEEDED" if failures == 0 else ("PARTIAL_FAILED" if succeeded else "FAILED")
            finish_run(session, run_id, status, "SOURCE_FAILURE" if failures else None)
        except Exception:
            session.rollback()
            logger.error("Discovery run failed: %s", run_id)
            finish_run(session, run_id, "FAILED", "RUN_FAILED")


def scheduled_discovery():
    settings = get_settings()
    with Session(get_engine()) as session:
        recent = session.scalar(
            select(AgentRun)
            .where(
                AgentRun.started_at
                > datetime.now(UTC) - timedelta(hours=settings.discovery_interval_hours),
            )
            .limit(1)
        )
        if recent:
            return
        try:
            run = create_run(session)
            run_id = run.id
        except HTTPException:
            return
    execute_run(run_id)
