"""Offline, transactional registry bootstrap with three-way reconciliation."""

import hashlib
import json
import logging
from pathlib import Path

from sqlalchemy import select, text

from app.config import get_settings
from app.ingestion.connectors.public_feeds import ENDPOINTS, FEED_INTERVALS
from app.ingestion.schemas import SourceCreate
from app.ingestion.service import register_source
from app.models import IngestionSource, MaintenanceState

log = logging.getLogger(__name__)
SEED = Path(__file__).with_name("seed") / "companies_india.json"
CANDIDATES = Path(__file__).with_name("seed") / "discovery_candidates.json"


def bundled_sources():
    for row in json.loads(SEED.read_text()):
        if not row.get("verification", {}).get("verified_at"):
            raise ValueError("SEED_REQUIRES_VERIFICATION")
        yield SourceCreate(
            company_name=row["company"],
            provider=row["ats_provider"],
            board_id=row["board_token"],
            career_url=row["source_url"],
            enabled=row["enabled"],
            access_policy="public_api",
            fetch_interval_seconds=row["sync_interval_hours"] * 3600,
            configuration={"country_focus": row["country_focus"]},
            permission_notes=(
                "Public ATS listing API; bundled validation evidence in companies_india.json"
            ),
        )
    for provider, endpoint in ENDPOINTS.items():
        yield SourceCreate(
            company_name=provider.title(),
            provider=provider,
            board_id="public",
            career_url=endpoint,
            access_policy="public_api",
            fetch_interval_seconds=FEED_INTERVALS[provider],
            permission_notes=(
                "Public job feed; attribution and linking required. See docs/JOB_INGESTION_V2.md"
            ),
            configuration={
                "request_interval_seconds": 2 if provider == "himalayas" else 1,
                **({"filters": {"country": "IN"}} if provider == "himalayas" else {}),
            },
        )


def reconcile(source, defaults):
    """Update only values still owned by the previous bundle, including nested config keys."""
    previous = source.seed_defaults
    if previous is None:
        return  # Existing manually registered source: entirely locally owned.
    overrides = set(source.local_overrides or [])
    missing = object()

    def merge(current, old, new, prefix):
        result = dict(current)
        for key in old.keys() | new.keys():
            path = f"{prefix}.{key}" if prefix else key
            before, after, actual = (
                old.get(key, missing),
                new.get(key, missing),
                current.get(key, missing),
            )
            if path in overrides or (not prefix and key in overrides):
                continue
            if isinstance(before, dict) and isinstance(after, dict) and isinstance(actual, dict):
                result[key] = merge(actual, before, after, path)
            elif actual != before:
                overrides.add(path)
            elif after is missing:
                result.pop(key, None)
            else:
                result[key] = after
        return result

    current = {k: getattr(source, k) for k in defaults}
    values = merge(current, previous, defaults, "")
    for key, value in values.items():
        setattr(source, key, value)
    source.seed_defaults, source.local_overrides = defaults, sorted(overrides)


def bootstrap(session, records=None, force=False):
    """No network or ingestion in API workers. Committed source rows form the durable schedule."""
    if records is None and not get_settings().ingestion_bootstrap_enabled:
        return 0
    records = list(bundled_sources() if records is None else records)
    digest = hashlib.sha256(
        json.dumps([r.model_dump() for r in records], sort_keys=True).encode()
    ).hexdigest()
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(624711203)")):
        session.rollback()
        return 0
    state = session.get(MaintenanceState, "bootstrap")
    if state and state.details.get("digest") == digest and not force:
        session.commit()
        return 0
    created, failures = 0, 0
    for payload in records:
        try:
            with session.begin_nested():
                source = session.scalar(
                    select(IngestionSource)
                    .where(
                        IngestionSource.provider == payload.provider,
                        IngestionSource.board_id == payload.board_id,
                    )
                    .with_for_update()
                )
                defaults = payload.model_dump(exclude={"website", "provider", "board_id"})
                if source:
                    reconcile(source, defaults)
                else:
                    source = register_source(session, payload, commit=False)
                    source.seed_defaults = defaults
                    if source.enabled:
                        from app.ingestion.engine import queue_run

                        queue_run(session, source.id, commit=False)
                    created += 1
        except Exception:
            failures += 1
            log.exception(
                "bootstrap_source_failed provider=%s board=%s", payload.provider, payload.board_id
            )
    if not failures:
        if state is None:
            state = MaintenanceState(key="bootstrap")
            session.add(state)
        state.details = {"digest": digest, "sources": len(records)}
    session.commit()
    log.info("ingestion_bootstrap created=%s failed=%s bundled=%s", created, failures, len(records))
    return created
