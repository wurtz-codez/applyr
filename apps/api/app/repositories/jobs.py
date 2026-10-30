from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.discovery import Company, Job, JobMatch, Shortlist
from app.models.profile import LOCAL_USER_ID, Profile
from app.schemas.discovery import JobDetail, JobSummary, MatchResult
from app.services.matching import PROMPT_VERSION


def jobs_query(session: Session):
    profile = session.scalar(select(Profile).where(Profile.user_id == LOCAL_USER_ID))
    version = profile.current_version if profile else -1
    latest = (
        select(JobMatch.id)
        .where(
            JobMatch.user_id == LOCAL_USER_ID,
            JobMatch.job_id == Job.id,
            JobMatch.profile_version == version,
            JobMatch.job_hash == Job.description_hash,
            JobMatch.job_status == Job.status,
            JobMatch.prompt_version == PROMPT_VERSION,
        )
        .order_by((JobMatch.provider == "gemini").desc(), JobMatch.evaluated_at.desc())
        .limit(1)
    )
    query = (
        select(Job, Company, JobMatch, Shortlist.id)
        .join(Company)
        .outerjoin(
            JobMatch,
            JobMatch.id == latest.correlate(Job).scalar_subquery(),
        )
        .outerjoin(Shortlist, and_(Shortlist.job_id == Job.id, Shortlist.user_id == LOCAL_USER_ID))
    )
    return query, profile


def summarize(row, detail: bool = False, profile: Profile | None = None):
    job, company, match, shortlist = row
    result = MatchResult.model_validate(match.result_json) if match else None
    fields = dict(
        id=job.id,
        company=company.name,
        title=job.title,
        location_text=job.location_text,
        source_url=job.source_url,
        status=job.status,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        shortlisted=shortlist is not None,
        match=result,
        needs_rematch=match is None,
    )
    if detail:
        evidence = [
            fact
            for fact in (profile.facts_json if profile else [])
            if result and fact["id"] in result.matched_profile_fact_ids
        ]
        return JobDetail(**fields, description_text=job.description_text, evidence=evidence)
    return JobSummary(**fields)


def count_query(session: Session, query) -> int:
    return session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
