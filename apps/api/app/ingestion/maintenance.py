"""Database leases and persistent due times survive Beat/Redis/process restarts."""

import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import MaintenanceState, now

log = logging.getLogger(__name__)


def run_maintenance(engine, key, interval, callback):
    token = uuid4()
    with Session(engine) as session:
        session.execute(
            insert(MaintenanceState)
            .values(key=key, failure_count=0, details={})
            .on_conflict_do_nothing()
        )
        claimed = session.execute(
            update(MaintenanceState)
            .where(
                MaintenanceState.key == key,
                or_(MaintenanceState.next_run_at.is_(None), MaintenanceState.next_run_at <= now()),
                or_(
                    MaintenanceState.lease_expires_at.is_(None),
                    MaintenanceState.lease_expires_at <= now(),
                ),
            )
            .values(lease_token=token, lease_expires_at=now() + timedelta(minutes=11))
        )
        session.commit()
        if not claimed.rowcount:
            return None
    error, details = None, {}
    try:
        details = {"processed": callback()}  # callback owns short DB transactions
    except Exception as exc:
        error = type(exc).__name__
        log.exception("ingestion_maintenance_failed key=%s", key)
    with Session(engine) as session:
        row = session.scalar(
            select(MaintenanceState)
            .where(MaintenanceState.key == key, MaintenanceState.lease_token == token)
            .with_for_update()
        )
        if row is None:
            return None
        row.failure_count = row.failure_count + 1 if error else 0
        delay = max(300, min(86400, 300 * 2 ** min(row.failure_count, 8))) if error else interval
        row.next_run_at = now() + timedelta(seconds=delay)
        row.lease_token, row.lease_expires_at = None, None
        row.details = {"error": error} if error else details
        if not error:
            row.last_success_at = now()
        session.commit()
    log.info("ingestion_maintenance_finished key=%s error=%s details=%s", key, error, details)
    return details
