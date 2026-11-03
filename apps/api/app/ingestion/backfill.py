"""Bounded, restart-safe legacy normalization; no inferred metadata or forced refetches."""

from sqlalchemy import select

from app.ingestion.eligibility import VERSION, apply_evaluation
from app.ingestion.normalizer import enrich, feed_location
from app.ingestion.schemas import NormalizedJob
from app.models import Job


def normalize_existing(row):
    if row.normalized_json:
        try:
            job = NormalizedJob.model_validate(row.normalized_json)
        except ValueError:
            job = None
    else:
        job = None
    if job is None:
        job = NormalizedJob(
            source=row.primary_source,
            external_id=str(row.id),
            company=row.company or "Unknown employer",
            title=row.title,
            description=row.description,
            location=feed_location(row.primary_source, row.location, row.work_mode),
            job_url=row.original_job_url or row.canonical_url,
            apply_url=row.apply_url,
            posted_at=row.published_at,
            valid_through=row.valid_through,
        )
    job = enrich(job)
    apply_evaluation(row, job)
    row.experience_min, row.experience_max = job.experience.min_years, job.experience.max_years
    row.normalized_json = job.model_dump(mode="json", exclude={"raw"})
    return job


def backfill(session, limit=250):
    rows = session.scalars(
        select(Job)
        .where(
            Job.normalization_version < VERSION,
            Job.listing_type == "JOB_POSTING",
        )
        .order_by(Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        normalize_existing(row)
    if rows:
        from app.ingestion.matching import mark_dirty

        mark_dirty(session)
    session.commit()
    return len(rows)
