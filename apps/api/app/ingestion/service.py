import hashlib

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.ingestion.discovery.ats_detector import detect
from app.ingestion.engine import source_config
from app.ingestion.policies import ATS, validate_config
from app.ingestion.registry import CONNECTORS
from app.models import Company, IngestionSource, JobSource


def register_source(session, payload):
    values = payload.model_dump()
    website = values.pop("website")
    provider = values["provider"]
    if provider == "auto":
        detected = detect(values["career_url"]) if values["career_url"] else None
        if detected:
            values["provider"], values["board_id"] = detected
        else:
            values["provider"] = "career_page"
    if values["provider"] not in CONNECTORS:
        raise ValueError("UNKNOWN_CONNECTOR")
    if not values["board_id"]:
        if not values["career_url"]:
            raise ValueError("BOARD_ID_OR_CAREER_URL_REQUIRED")
        values["board_id"] = hashlib.sha256(values["career_url"].encode()).hexdigest()
    # Names without an employer URL are not enough to merge separate employer entities.
    company = None
    if website:
        session.execute(
            insert(Company)
            .values(name=values["company_name"], website=website)
            .on_conflict_do_nothing(index_elements=["website"])
        )
        company = session.scalar(select(Company).where(Company.website == website))
    if not company:
        company = Company(name=values["company_name"], website=website)
        session.add(company)
        session.flush()
    provider = values["provider"]
    values["source_type"] = "ats" if provider in ATS else provider
    if values["career_url"] and "jobs.eu.lever.co" in values["career_url"]:
        values["configuration"] = {**values["configuration"], "region": "eu"}
    if (
        provider == "greenhouse"
        and values["career_url"]
        and ".eu.greenhouse.io" in values["career_url"]
    ):
        raise ValueError("GREENHOUSE_EU_NOT_SUPPORTED")
    source = IngestionSource(company_id=company.id, **values)
    validate_config(source_config(source))
    session.add(source)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ValueError("SOURCE_ALREADY_REGISTERED") from None
    session.refresh(source)
    return source


def source_response(session, source):
    values = {
        key: getattr(source, key)
        for key in (
            "id",
            "company_id",
            "company_name",
            "career_url",
            "provider",
            "board_id",
            "source_type",
            "enabled",
            "access_policy",
            "permission_notes",
            "last_success_at",
            "last_attempt_at",
            "fetch_interval_seconds",
            "next_fetch_at",
            "failure_count",
            "health",
            "active_run_id",
        )
    }
    values["job_count"] = (
        session.scalar(
            select(func.count()).select_from(JobSource).where(JobSource.source_id == source.id)
        )
        or 0
    )
    values["discovered_boards"] = (source.sync_state or {}).get("discovered_boards", [])
    return values


def run_response(run):
    return {
        key: getattr(run, key)
        for key in (
            "id",
            "source_id",
            "status",
            "started_at",
            "finished_at",
            "fetched",
            "inserted",
            "updated",
            "deduplicated",
            "failed",
            "errors",
        )
    }
