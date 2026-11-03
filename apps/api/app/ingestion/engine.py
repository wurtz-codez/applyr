"""Source-independent orchestration, durable run state and transactional catalog writes."""

import asyncio
import hashlib
import json
import logging
from datetime import timedelta
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.ingestion.deduplicator import candidates, find_job
from app.ingestion.eligibility import VERSION, apply_evaluation
from app.ingestion.freshness import refresh_status
from app.ingestion.http import HTTP, FetchFailure
from app.ingestion.policies import check_access
from app.ingestion.registry import CONNECTORS
from app.ingestion.schemas import SourceConfig
from app.models import IngestionRun, IngestionSource, Job, JobSource, JobTag, SourceState, now
from app.normalization import canonical_url

log = logging.getLogger(__name__)
TERMINAL = {"SUCCEEDED", "PARTIAL", "FAILED", "INTERRUPTED"}


def source_config(source):
    return SourceConfig(
        provider=source.provider,
        board_id=source.board_id,
        company=source.company_name,
        career_url=source.career_url,
        configuration=source.configuration,
        state=source.sync_state or {},
    )


def queue_run(session: Session, source_id: UUID, *, commit=True) -> IngestionRun:
    source = session.scalar(
        select(IngestionSource).where(IngestionSource.id == source_id).with_for_update()
    )
    if source is None:
        raise LookupError("SOURCE_NOT_FOUND")
    check_access(source)
    timestamp = now()
    if source.active_run_id and source.lease_expires_at and source.lease_expires_at > timestamp:
        existing = session.get(IngestionRun, source.active_run_id)
        if commit:
            session.commit()
        return existing
    if source.active_run_id:
        previous = session.get(IngestionRun, source.active_run_id)
        if previous and previous.status not in TERMINAL:
            previous.status, previous.finished_at = "INTERRUPTED", timestamp
            previous.errors = [{"code": "LEASE_EXPIRED", "recoverable": True}]
    run = IngestionRun(source_id=source.id)
    session.add(run)
    session.flush()
    source.active_run_id, source.lease_expires_at = run.id, timestamp + timedelta(minutes=12)
    if commit:
        session.commit()
    return run


def publish(run_id: UUID) -> bool:
    from app.workers.celery_app import celery

    try:
        celery.send_task(
            "ingestion.run", args=[str(run_id)], task_id=str(run_id), queue="ingestion"
        )
        return True
    except Exception:
        # DB row is the durable queue; Beat republishes pending runs after broker recovery.
        log.warning("ingestion_dispatch_pending run_id=%s", run_id)
        return False


def store_job(session, source, item):
    row, occurrence, key = find_job(session, item, source)
    inserted, deduplicated = row is None, row is not None and occurrence is None
    candidate_ids = candidates(session, item, source) if row is None else []
    from app.ingestion.normalizer import enrich

    item = enrich(item)
    values = item.model_dump(mode="json", exclude={"raw"})
    content = {
        k: v for k, v in values.items() if k not in {"source", "external_id", "source_fields"}
    }
    content["job_url"] = canonical_url(item.job_url)
    content["apply_url"] = canonical_url(item.apply_url) if item.apply_url else None
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    if row is None:
        row = Job(
            canonical_url=canonical_url(
                item.job_url if source.source_type == "ats" else (item.apply_url or item.job_url)
            ),
            first_seen_at=now(),
            primary_source=source.provider,
        )
        session.add(row)
    # ATS data takes precedence over HTML/aggregator data. Provenance always updates.
    authoritative = inserted or row.primary_source == source.provider or source.source_type == "ats"
    changed = authoritative and (row.content_hash != digest or row.normalization_version != VERSION)
    if changed:
        row.title, row.company = item.title, item.company
        if source.source_type == "ats":
            row.company_id = source.company_id
        row.location, row.description = item.location.label, item.description
        row.work_mode = item.location.remote_type.upper()
        row.employment_type = item.employment_type
        row.published_at = item.posted_at
        row.experience_min, row.experience_max = (
            item.experience.min_years,
            item.experience.max_years,
        )
        apply_evaluation(row, item)
        for field in (
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "salary_text",
            "experience_level",
        ):
            setattr(row, field, getattr(item, field))
        row.apply_url = canonical_url(item.apply_url) if item.apply_url else None
        row.original_job_url = item.job_url
        row.normalized_json, row.content_hash = values, digest
        row.valid_through, row.requisition_id = item.valid_through, item.requisition_id
        row.primary_source = source.provider
    if key and not row.ats_identity:
        row.ats_identity = key
    row.last_seen_at = now()
    session.flush()
    if changed:
        from sqlalchemy import delete

        session.execute(delete(JobTag).where(JobTag.job_id == row.id))
        session.add_all(JobTag(job_id=row.id, tag=s.casefold()) for s in sorted(set(item.skills)))
    if occurrence is None:
        occurrence = JobSource(
            job_id=row.id,
            source_id=source.id,
            provider=source.provider,
            external_id=item.external_id,
            first_seen_at=now(),
        )
        session.add(occurrence)
    occurrence.source_url, occurrence.last_seen_at = item.job_url, now()
    occurrence.last_verified_at = now()
    occurrence.ats_identity = key
    occurrence.active = item.status == "active" and not (
        item.valid_through is not None and item.valid_through < now()
    )
    occurrence.metadata_json = {
        "apply_url": item.apply_url,
        "ats_identity": key,
        "requisition_id": item.requisition_id,
        "valid_through": item.valid_through.isoformat() if item.valid_through else None,
        "candidate_job_ids": candidate_ids,
    }
    occurrence.raw_json = item.raw if source.configuration.get("retain_raw", False) else None
    session.flush()
    status_changed = refresh_status(session, row.id)
    return inserted, (changed or status_changed) and not inserted, deduplicated


async def ingest(run_id: UUID, engine=None, http_client=None):
    engine = engine or get_engine()
    with Session(engine) as session:
        run = session.get(IngestionRun, run_id)
        if not run:
            return
        source = session.scalar(
            select(IngestionSource).where(IngestionSource.id == run.source_id).with_for_update()
        )
        if source.active_run_id != run.id:
            session.rollback()
            return
        claimed = session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id, IngestionRun.status == "QUEUED")
            .values(status="RUNNING", started_at=now())
        )
        if claimed.rowcount != 1:
            session.rollback()
            return
        from app.ingestion.connectors.public_feeds import FEED_INTERVALS

        if source.provider in FEED_INTERVALS:
            # Share the request reservation with the legacy manual endpoint.
            session.execute(
                insert(SourceState)
                .values(key=source.provider, provider=source.provider)
                .on_conflict_do_nothing()
            )
            state = session.scalar(
                select(SourceState).where(SourceState.key == source.provider).with_for_update()
            )
            if state.next_allowed_at and state.next_allowed_at > now():
                source.next_fetch_at = state.next_allowed_at
                source.active_run_id, source.lease_expires_at = None, None
                run.status, run.finished_at = "SUCCEEDED", now()
                session.commit()
                return
            state.next_allowed_at = now() + timedelta(
                seconds=max(source.fetch_interval_seconds, FEED_INTERVALS[source.provider])
            )
        source.last_attempt_at = now()
        source.lease_expires_at = now() + timedelta(minutes=12)
        session.commit()
        owned = http_client is None
        http_client = http_client or httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "ApplyrJobCollector/0.2"},
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        )
        errors = []
        retry_after = 0
        try:
            check_access(source)
            config = source_config(source)
            if source.provider == "jobicy":
                # Oldest verification first, bounded to ten status requests per daily check.
                ids = session.scalars(
                    select(JobSource.external_id)
                    .where(
                        JobSource.source_id == source.id,
                    )
                    .order_by(JobSource.last_verified_at.asc().nulls_first(), JobSource.id)
                    .limit(1000)
                ).all()
                config.configuration = {
                    **config.configuration,
                    "verify_ids": [i for i in ids if i and i.isdigit()],
                }
            connector = CONNECTORS[source.provider](
                HTTP(http_client, interval=source.configuration.get("request_interval_seconds", 1))
            )
            rolling = source.provider in {"arbeitnow", "jobicy", "himalayas"}
            if rolling:
                filter_hash = hashlib.sha256(
                    json.dumps(config.configuration.get("filters", {}), sort_keys=True).encode()
                ).hexdigest()
                if config.state.get("traversal_filters") != filter_hash:
                    config.state["resume_cursor"] = None
                config.state["traversal_filters"] = filter_hash
            cursor = config.state.get("resume_cursor") if rolling else None
            visited, complete_snapshot = set(), True
            async with asyncio.timeout(540):
                for _ in range(get_settings().ingestion_max_pages):
                    result = await connector.fetch_jobs(config, cursor)
                    complete_snapshot = complete_snapshot and result.complete_snapshot
                    # Recheck authorization and ownership before every catalog write.
                    session.refresh(source, with_for_update=True)
                    check_access(source)
                    if source.active_run_id != run_id:
                        raise FetchFailure("LEASE_LOST", False)
                    for item in result.jobs:
                        try:
                            with session.begin_nested():
                                inserted, updated, deduped = store_job(session, source, item)
                            run.inserted += int(inserted)
                            run.updated += int(updated)
                            run.deduplicated += int(deduped)
                        except (ValueError, TypeError):
                            errors.append({"code": "INVALID_JOB", "recoverable": False})
                    run.fetched += len(result.jobs)
                    errors.extend(e.model_dump() for e in result.errors)
                    # Never replace complete state with a partial page checkpoint on failure.
                    statuses = result.metadata.pop("verified_statuses", [])
                    for verified in statuses:
                        if not isinstance(verified, dict) or verified.get("status") not in {
                            "active",
                            "closed",
                        }:
                            continue
                        occurrence = session.scalar(
                            select(JobSource).where(
                                JobSource.source_id == source.id,
                                JobSource.external_id == str(verified.get("id")),
                            )
                        )
                        if occurrence:
                            occurrence.active = verified["status"] == "active"
                            occurrence.last_verified_at = now()
                            session.flush()
                            if refresh_status(session, occurrence.job_id):
                                from app.ingestion.matching import mark_dirty

                                mark_dirty(session)
                    config.state.update(result.metadata)
                    if len(json.dumps(config.state).encode()) > (
                        get_settings().ingestion_max_state_mb * 1024 * 1024
                    ):
                        raise FetchFailure("SYNC_STATE_LIMIT", False)
                    if run.inserted or run.updated:
                        from app.ingestion.matching import mark_dirty

                        mark_dirty(session)
                    if rolling:
                        config.state["resume_cursor"] = result.next_cursor
                        source.sync_state = dict(config.state)
                    session.commit()
                    cursor = result.next_cursor
                    if cursor is None:
                        source.sync_state = config.state
                        if complete_snapshot and not errors:
                            from app.ingestion.freshness import reconcile_snapshot

                            reconcile_snapshot(session, source.id, run.started_at)
                        session.commit()
                        break
                    if cursor in visited:
                        raise FetchFailure("PAGINATION_CYCLE", False)
                    visited.add(cursor)
                else:
                    if not rolling:
                        raise FetchFailure("PAGE_LIMIT_REACHED")
        except FetchFailure as exc:
            if source.provider in {"jobicy", "himalayas"} and exc.error.code == "HTTP_400":
                # Opaque feed cursors may expire or become invalid after filter changes.
                source.sync_state = {**(source.sync_state or {}), "resume_cursor": None}
                session.flush()  # Persist before the final ownership refresh reloads the source.
            errors.append(exc.error.model_dump())
            retry_after = exc.error.retry_after or 0
        except (TimeoutError, httpx.TimeoutException):
            errors.append({"code": "RUN_TIMEOUT", "recoverable": True})
        except Exception:
            session.rollback()
            log.exception("ingestion_failed run_id=%s source_id=%s", run_id, source.id)
            errors.append({"code": "CONNECTOR_ERROR", "recoverable": True})
        finally:
            if owned:
                await http_client.aclose()
        session.refresh(source)
        if source.active_run_id != run_id:
            return
        retry_after = max([retry_after] + [e.get("retry_after") or 0 for e in errors])
        run.errors, run.failed = errors[:100], len(errors)
        run.status = "PARTIAL" if errors and run.fetched else "FAILED" if errors else "SUCCEEDED"
        run.finished_at = now()
        if errors:
            source.failure_count += 1
            source.health = "degraded" if run.fetched else "failing"
            delay = max(retry_after, min(86400, 300 * 2 ** min(source.failure_count, 8)))
        else:
            source.last_success_at, source.failure_count, source.health = now(), 0, "healthy"
            delay = source.fetch_interval_seconds
        if source.provider in FEED_INTERVALS:
            state = session.get(SourceState, source.provider)
            delay = max(delay, FEED_INTERVALS[source.provider])
            state.next_allowed_at = now() + timedelta(seconds=delay)
            state.last_error = errors[0]["code"] if errors else None
            if not errors:
                state.last_success_at = now()
        source.next_fetch_at = now() + timedelta(seconds=delay)
        source.active_run_id, source.lease_expires_at = None, None
        session.commit()
        log.info(
            "ingestion_finished run_id=%s source_id=%s status=%s fetched=%s inserted=%s",
            run.id,
            source.id,
            run.status,
            run.fetched,
            run.inserted,
        )


def execute(run_id: str):
    asyncio.run(ingest(UUID(run_id)))
