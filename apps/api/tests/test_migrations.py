from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.database import get_engine


def test_migration_roundtrip_and_metadata(client):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.check(config)
    command.downgrade(config, "base")
    assert "jobs" not in inspect(get_engine()).get_table_names()
    command.upgrade(config, "head")
    assert "jobs" in inspect(get_engine()).get_table_names()
    command.check(config)


def test_ingestion_upgrade_preserves_legacy_job_and_occurrence(client):
    from uuid import uuid4

    from sqlalchemy import text

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    job_id, occurrence_id = uuid4(), uuid4()
    command.downgrade(config, "dda5755cd4ae")
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text("""
                INSERT INTO jobs (id, canonical_url, title, description, work_mode,
                    listing_type, enrichment_status, primary_source, first_seen_at,
                    last_seen_at, content_hash)
                VALUES (:id, 'https://example.com/legacy', 'Legacy Developer', '',
                    'UNKNOWN', 'JOB_POSTING', 'NOT_NEEDED', 'arbeitnow', now(), now(), :digest)
            """),
                {"id": job_id, "digest": "a" * 64},
            )
            connection.execute(
                text("""
                INSERT INTO job_sources (id, job_id, provider, source_url, last_seen_at)
                VALUES (:id, :job_id, 'arbeitnow', 'https://example.com/legacy', now())
            """),
                {"id": occurrence_id, "job_id": job_id},
            )
        command.upgrade(config, "head")
        with get_engine().connect() as connection:
            row = connection.execute(
                text("""
                SELECT job_id, source_id, first_seen_at, last_seen_at
                FROM job_source_occurrences WHERE id=:id
            """),
                {"id": occurrence_id},
            ).one()
            assert row.job_id == job_id and row.source_id is None
            assert row.first_seen_at == row.last_seen_at
            assert (
                connection.execute(
                    text("SELECT status FROM jobs WHERE id=:id"), {"id": job_id}
                ).scalar_one()
                == "active"
            )
    finally:
        command.upgrade(config, "head")
