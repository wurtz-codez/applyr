import hashlib
import json
from datetime import UTC, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import (
    DiscoveryRun,
    Job,
    JobSource,
    JobTag,
    RunLock,
    SearchAttempt,
    SourceState,
    now,
)
from app.schemas import DiscoveryInput, RunResponse, SourceResult
from app.sources import PROVIDERS, SourceError, fetch


def run_response(row):
    return RunResponse(
        id=row.id,
        status=row.status,
        query=row.query,
        providers=row.providers_json,
        results=row.results_json,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error_code=row.error_code,
    )


def create_run(session: Session, payload: DiscoveryInput):
    providers = payload.providers
    if providers is None:
        providers = ["arbeitnow", "remotive", "jobicy"]
        if get_settings().tavily_api_key:
            providers.append("tavily")
    providers = list(dict.fromkeys(providers))
    if "tavily" in providers and not get_settings().tavily_api_key:
        raise HTTPException(409, "Set TAVILY_API_KEY in the local .env to enable web search")
    query = (payload.query.strip() or get_settings().default_search_query).strip()
    if "tavily" in providers and not query:
        raise HTTPException(422, "A search query is required for Tavily")
    row = DiscoveryRun(query=query, providers_json=providers)
    session.add(row)
    session.flush()
    previous = session.get(RunLock, 1)
    previous_id = previous.run_id
    acquired = session.execute(
        update(RunLock)
        .where(
            RunLock.id == 1,
            or_(RunLock.run_id.is_(None), RunLock.expires_at < now()),
        )
        .values(run_id=row.id, expires_at=now() + timedelta(minutes=15))
        .execution_options(synchronize_session=False)
    )
    if acquired.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "A refresh is already running")
    if previous_id:
        session.execute(
            update(DiscoveryRun)
            .where(
                DiscoveryRun.id == previous_id,
                DiscoveryRun.status.in_(["QUEUED", "RUNNING"]),
            )
            .values(status="INTERRUPTED", error_code="LEASE_EXPIRED", finished_at=now())
        )
    session.commit()
    session.refresh(row)
    return row


def fingerprint(item):
    values = item.model_dump(mode="json", exclude={"source_url", "external_id"})
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def priority(provider, listing_type, enrichment):
    return (
        2 if listing_type == "JOB_POSTING" else 1,
        2 if enrichment == "EXTRACTED" else 1,
        {"arbeitnow": 4, "jobicy": 3, "remotive": 2, "tavily": 1}[provider],
    )


def store_jobs(session, provider, items):
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    unique = {}
    for item in items:
        unique[item.canonical_url] = item
    for item in unique.values():
        row = session.scalar(select(Job).where(Job.canonical_url == item.canonical_url))
        digest = fingerprint(item)
        write = row is None
        if row is None:
            row = Job(canonical_url=item.canonical_url, first_seen_at=now())
            session.add(row)
            counts["new"] += 1
        else:
            better = priority(provider, item.listing_type, item.enrichment_status) >= priority(
                row.primary_source,
                row.listing_type,
                row.enrichment_status,
            )
            write = better and digest != row.content_hash
            counts["updated" if write else "unchanged"] += 1
        if write:
            for name, value in item.model_dump(
                exclude={"external_id", "source_url", "tags"}
            ).items():
                setattr(row, name, value)
            row.content_hash, row.primary_source = digest, provider
        row.last_seen_at = now()
        session.flush()
        if write:
            session.execute(delete(JobTag).where(JobTag.job_id == row.id))
            session.add_all(JobTag(job_id=row.id, tag=tag) for tag in item.tags)
        source = session.scalar(
            select(JobSource).where(JobSource.job_id == row.id, JobSource.provider == provider)
        )
        if source is None:
            source = JobSource(job_id=row.id, provider=provider)
            session.add(source)
        source.source_url, source.external_id, source.last_seen_at = (
            item.source_url,
            item.external_id,
            now(),
        )
    session.commit()
    return counts


def source_key(provider, query):
    return provider + (
        ":" + hashlib.sha256(query.encode()).hexdigest() if provider == "tavily" else ""
    )


def finish(session, row, status, error=None):
    row.status, row.error_code, row.finished_at = status, error, now()
    session.execute(
        update(RunLock).where(RunLock.run_id == row.id).values(run_id=None, expires_at=None)
    )
    session.commit()


def execute_run(run_id: UUID | str, engine=None):
    with Session(engine or get_engine()) as session:
        row = session.get(DiscoveryRun, UUID(str(run_id)))
        if not row:
            return
        claimed = session.execute(
            update(DiscoveryRun)
            .where(
                DiscoveryRun.id == row.id,
                DiscoveryRun.status == "QUEUED",
            )
            .values(status="RUNNING")
        )
        if claimed.rowcount != 1:
            session.rollback()
            return
        session.commit()
        results = []
        try:
            for provider in row.providers_json:
                lock = session.get(RunLock, 1, populate_existing=True)
                if lock.run_id != row.id or lock.expires_at.replace(tzinfo=UTC) < now():
                    finish(session, row, "INTERRUPTED", "LEASE_EXPIRED")
                    return
                state = session.get(SourceState, source_key(provider, row.query))
                if (
                    state
                    and state.next_allowed_at
                    and state.next_allowed_at.replace(tzinfo=UTC) > now()
                ):
                    status = "CACHED" if state.last_error is None else "COOLDOWN"
                    result = SourceResult(
                        provider=provider,
                        status=status,
                        error_code=state.last_error,
                        next_refresh_at=state.next_allowed_at,
                    )
                else:
                    if state is None:
                        state = SourceState(key=source_key(provider, row.query), provider=provider)
                        session.add(state)
                    if provider == "tavily":
                        attempts = (
                            session.scalar(
                                select(func.count())
                                .select_from(SearchAttempt)
                                .where(
                                    SearchAttempt.attempted_at
                                    >= now().replace(hour=0, minute=0, second=0, microsecond=0),
                                )
                            )
                            or 0
                        )
                        if attempts >= get_settings().max_search_requests_per_day:
                            results.append(
                                SourceResult(
                                    provider=provider,
                                    status="SKIPPED",
                                    error_code="DAILY_SEARCH_BUDGET",
                                ).model_dump(mode="json")
                            )
                            row.results_json = list(results)
                            session.commit()
                            continue
                        session.add(SearchAttempt())
                    state.next_allowed_at = now() + timedelta(
                        seconds=PROVIDERS[provider]["interval"]
                    )
                    session.commit()  # Reserve the request before external I/O.
                    try:
                        batch = fetch(provider, row.query)
                        counts = store_jobs(session, provider, batch.jobs)
                        state.last_success_at, state.last_error = now(), batch.error_code
                        if batch.retry_after is not None:
                            state.next_allowed_at = now() + timedelta(seconds=batch.retry_after)
                        result = SourceResult(
                            provider=provider,
                            status="PARTIAL_FAILED" if batch.error_code else "SUCCEEDED",
                            error_code=batch.error_code,
                            fetched=len(batch.jobs),
                            invalid=batch.invalid,
                            partial=batch.partial,
                            enriched=batch.enriched,
                            next_refresh_at=state.next_allowed_at,
                            **counts,
                        )
                    except SourceError as error:
                        session.rollback()
                        state = session.get(SourceState, source_key(provider, row.query))
                        state.last_error = str(error)
                        if error.retry_after is not None:
                            state.next_allowed_at = now() + timedelta(seconds=error.retry_after)
                        result = SourceResult(
                            provider=provider,
                            status="FAILED",
                            error_code=str(error),
                            next_refresh_at=state.next_allowed_at,
                        )
                    session.commit()
                results.append(result.model_dump(mode="json"))
                row.results_json = list(results)
                session.commit()
            failed = sum(item["status"] in {"FAILED", "COOLDOWN", "SKIPPED"} for item in results)
            status = (
                "SUCCEEDED"
                if not failed
                else ("FAILED" if failed == len(results) else "PARTIAL_FAILED")
            )
            if any(item["status"] == "PARTIAL_FAILED" for item in results):
                status = "PARTIAL_FAILED"
            finish(session, row, status)
        except Exception:
            session.rollback()
            row = session.get(DiscoveryRun, UUID(str(run_id)))
            finish(session, row, "FAILED", "INTERNAL_REFRESH_ERROR")
