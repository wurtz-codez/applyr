"""Expire only when all known provenance independently supports closure."""

from sqlalchemy import select

from app.models import Job, JobSource, now
from app.normalization import date


def reconcile_snapshot(session, source_id, run_started_at):
    """Two complete successful snapshots must independently confirm an absence."""
    changed = False
    for occurrence in session.scalars(select(JobSource).where(JobSource.source_id == source_id)):
        metadata = dict(occurrence.metadata_json or {})
        if occurrence.last_seen_at >= run_started_at:
            metadata["consecutive_absences"] = 0
        else:
            metadata["consecutive_absences"] = metadata.get("consecutive_absences", 0) + 1
            if metadata["consecutive_absences"] >= 2:
                occurrence.active = False
        occurrence.metadata_json = metadata
        session.flush()
        changed = refresh_status(session, occurrence.job_id) or changed
    if changed:
        from app.ingestion.matching import mark_dirty

        mark_dirty(session)


def refresh_status(session, job_id):
    job = session.get(Job, job_id)
    previous = job.status
    occurrences = session.scalars(select(JobSource).where(JobSource.job_id == job_id)).all()
    if occurrences:
        job.status = "active" if any(o.active for o in occurrences) else "closed"
        if job.normalized_json and job.normalized_json.get("status") != job.status:
            job.normalized_json = {**job.normalized_json, "status": job.status}
    return previous != job.status


def expire_jobs(session):
    # validThrough is explicit employer evidence, never a failed poll or elapsed first_seen time.
    changed = False
    for job in session.scalars(
        select(Job).where(Job.valid_through < now(), Job.status == "active")
    ):
        for occurrence in session.scalars(select(JobSource).where(JobSource.job_id == job.id)):
            validity = (occurrence.metadata_json or {}).get("valid_through")
            expiry = date(validity)
            if expiry and expiry < now():
                occurrence.active = False
        session.flush()
        changed = refresh_status(session, job.id) or changed
    if changed:
        from app.ingestion.matching import mark_dirty

        mark_dirty(session)
