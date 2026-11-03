"""Transparent profile ranking baseline. AI reranking can consume these persisted matches."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.models import Job, JobMatch, MatchingProfile, now


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_key: str = Field(min_length=1, max_length=200)
    skills: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100
    )
    roles: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=lambda: ["software", "sde", "backend", "full stack", "developer"],
        max_length=30,
    )
    max_experience: int = Field(default=2, ge=0, le=60)
    india_only: bool = True


def score(job: Job, profile: ProfileInput) -> tuple[float, list[str]]:
    data = job.normalized_json or {}
    derived = data.get("derived", {})
    reasons, value = [], 0.0
    if any(role.casefold() in job.title.casefold() for role in profile.roles):
        value += 25
    else:
        reasons.append("role_mismatch")
    if derived.get("senior"):
        reasons.append("senior_role")
        value -= 25
    if not profile.india_only or job.india_eligible is True:
        value += 20
    elif job.india_eligible is None:
        value += 10
        reasons.append("geography_uncertain")
    else:
        reasons.append("geography_mismatch")
    if job.experience_min is None:
        value += 12
        reasons.append("experience_uncertain")
    elif job.experience_min <= profile.max_experience:
        value += 25
    else:
        reasons.append("experience_mismatch")
    required = {s.casefold() for s in data.get("skills", [])}
    known = {s.casefold() for s in profile.skills}
    if required:
        value += 30 * len(required & known) / len(required)
        reasons.extend(f"missing_skill:{s}" for s in sorted(required - known))
    else:
        value += 15
        reasons.append("skills_uncertain")
    if job.status == "closed":
        reasons.append("job_closed")
        value = 0
    if profile.india_only and job.india_eligible is False:
        value = 0
    return round(max(0, min(100, value)), 2), reasons


def mark_dirty(session):
    session.execute(
        update(MatchingProfile).where(MatchingProfile.enabled.is_(True)).values(needs_refresh=True)
    )


def refresh_profiles(session):
    # Competing matching workers skip claimed profiles. A concurrent ingestion must
    # acquire this profile lock before setting dirty, so an update cannot be lost.
    profiles = session.scalars(
        select(MatchingProfile)
        .where(MatchingProfile.enabled.is_(True), MatchingProfile.needs_refresh.is_(True))
        .order_by(MatchingProfile.id)
        .limit(10)
        .with_for_update(skip_locked=True)
    ).all()
    for profile in profiles:
        config = ProfileInput.model_validate(profile.configuration)
        for job in session.scalars(
            select(Job)
            .where(Job.listing_type == "JOB_POSTING")
            .order_by(Job.id)
            .execution_options(yield_per=500)
        ):
            value, reasons = score(job, config)
            values = {
                "score": value,
                "reasons": reasons,
                "content_hash": job.content_hash,
                "evaluated_at": now(),
            }
            session.execute(
                insert(JobMatch)
                .values(profile_id=profile.id, job_id=job.id, **values)
                .on_conflict_do_update(index_elements=["profile_id", "job_id"], set_=values)
            )
        profile.needs_refresh, profile.updated_at = False, now()
    session.commit()
    return len(profiles)
