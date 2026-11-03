"""Identity merges only; similar titles are review candidates."""

from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import or_, select, text

from app.ingestion.discovery.ats_detector import detect
from app.models import Job, JobSource
from app.normalization import canonical_url


def ats_identity(url: str) -> str | None:
    detected = detect(url)
    if not detected:
        return None
    provider, board = detected
    parsed = urlsplit(url)
    parts = parsed.path.strip("/").split("/")
    external = None
    if provider == "greenhouse":
        external = parse_qs(parsed.query).get("gh_jid", [None])[0]
        if "jobs" in parts and parts.index("jobs") + 1 < len(parts):
            external = parts[parts.index("jobs") + 1]
    elif len(parts) > 1:
        external = parts[1].split("-", 1)[0] if provider == "smartrecruiters" else parts[1]
    return f"{provider}:{board}:{external}" if external else None


def identity(item, source):
    from app.ingestion.policies import ATS

    if source.provider in ATS:
        return f"{source.provider}:{source.board_id}:{item.external_id}"
    return ats_identity(item.apply_url or item.job_url)


def find_job(session, item, source):
    key = identity(item, source)
    urls = sorted({canonical_url(u) for u in (item.job_url, item.apply_url) if u})
    # Cross-source workers serialize identity resolution inside the same DB transaction.
    keys = urls + ([key] if key else [])
    if item.requisition_id and source.source_type not in {
        "arbeitnow",
        "jobicy",
        "remotive",
        "himalayas",
    }:
        keys.append(f"req:{source.company_id}:{item.requisition_id}")
    for value in sorted(keys):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": value}
        )
    occurrence = session.scalar(
        select(JobSource).where(
            JobSource.source_id == source.id, JobSource.external_id == item.external_id
        )
    )
    if occurrence:
        return session.get(Job, occurrence.job_id), occurrence, key
    # Adopt a legacy feed occurrence instead of manufacturing another appearance.
    if source.provider in {"arbeitnow", "jobicy", "remotive"}:
        occurrence = session.scalar(
            select(JobSource)
            .where(
                JobSource.source_id.is_(None),
                JobSource.provider == source.provider,
                JobSource.external_id == item.external_id,
            )
            .limit(1)
        )
        if occurrence:
            occurrence.source_id = source.id
            return session.get(Job, occurrence.job_id), occurrence, key
    if key:
        row = session.scalar(select(Job).where(Job.ats_identity == key))
        if row:
            return row, None, key
        occurrence = session.scalar(select(JobSource).where(JobSource.ats_identity == key).limit(1))
        if occurrence:
            return session.get(Job, occurrence.job_id), None, key
    row = session.scalar(
        select(Job).where(or_(Job.canonical_url.in_(urls), Job.apply_url.in_(urls)))
    )
    if row:
        # A shared application form is weaker evidence than two distinct requisitions
        # on the same verified ATS board. Keep those openings separate.
        conflict = (
            key
            and row.ats_identity
            and key.rsplit(":", 1)[0] == row.ats_identity.rsplit(":", 1)[0]
            and key != row.ats_identity
        )
        if not conflict:
            return row, None, key
    if item.requisition_id and source.source_type not in {
        "arbeitnow",
        "jobicy",
        "remotive",
        "himalayas",
    }:
        row = session.scalar(
            select(Job).where(
                Job.company_id == source.company_id, Job.requisition_id == item.requisition_id
            )
        )
        if row:
            return row, None, key
    return None, None, key


def candidates(session, item, source):
    rows = session.scalars(
        select(Job)
        .where(Job.company_id == source.company_id, Job.location == item.location.label)
        .limit(100)
    )
    return [
        str(j.id)
        for j in rows
        if SequenceMatcher(None, j.title.casefold(), item.title.casefold()).ratio() > 0.9
    ][:5]
