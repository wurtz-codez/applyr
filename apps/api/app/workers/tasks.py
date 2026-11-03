from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.ingestion.engine import execute, publish, queue_run
from app.ingestion.freshness import expire_jobs
from app.models import IngestionRun, IngestionSource, now
from app.workers.celery_app import celery


@celery.task(name="ingestion.run")
def ingest_source(run_id: str):
    # A browser source gets its own queue; normal workers never launch a browser.
    with Session(get_engine()) as session:
        row = session.get(IngestionRun, UUID(run_id))
        if row and session.get(IngestionSource, row.source_id).provider == "browser":
            celery.send_task("ingestion.browser", args=[run_id], queue="browser")
            return
    execute(run_id)


@celery.task(name="ingestion.browser")
def ingest_browser(run_id: str):
    execute(run_id)


@celery.task(name="ingestion.schedule")
def schedule_sources():
    with Session(get_engine()) as session:
        ids = session.scalars(
            select(IngestionSource.id)
            .where(
                IngestionSource.enabled.is_(True),
                IngestionSource.access_policy.in_(["public_api", "permitted"]),
                or_(
                    IngestionSource.next_fetch_at.is_(None), IngestionSource.next_fetch_at <= now()
                ),
            )
            .limit(1000)
        ).all()
        for source_id in ids:
            try:
                queue_run(session, source_id)
            except ValueError:
                session.rollback()
        pending = session.scalars(
            select(IngestionRun.id).where(IngestionRun.status == "QUEUED").limit(1000)
        ).all()
    for run_id in pending:
        publish(run_id)


@celery.task(name="ingestion.freshness")
def freshness():
    with Session(get_engine()) as session:
        expire_jobs(session)
        session.commit()


@celery.task(name="matching.refresh")
def matching():
    from app.ingestion.matching import refresh_profiles

    with Session(get_engine()) as session:
        return refresh_profiles(session)
