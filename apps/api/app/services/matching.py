import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.llm.gemini import AIError, analyze
from app.models.discovery import Job, JobMatch
from app.models.profile import LOCAL_USER_ID, Profile
from app.schemas.discovery import Components, MatchResult
from app.schemas.profile import ProfileInput
from app.services.eligibility import eligibility

PROMPT_VERSION = "match-v1"
SKILLS = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Go",
    "C++",
    "C#",
    "React",
    "Next.js",
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "Git",
    "Linux",
    "REST",
    "GraphQL",
    "MongoDB",
    "Spring",
    "Angular",
    "Vue",
    "Rust",
    "Swift",
    "Kotlin",
]


def contains(text: str, phrase: str) -> bool:
    return bool(
        re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])", text.lower())
    )


def total(components: Components) -> int:
    return round(
        0.40 * components.skills
        + 0.25 * components.role
        + 0.20 * components.experience
        + 0.15 * components.projects
    )


def deterministic(job: Job, profile: ProfileInput) -> MatchResult:
    status, reasons = eligibility(job, profile)
    if status != "ELIGIBLE":
        return MatchResult(
            eligibility_status=status,
            eligibility_reasons=reasons,
            reason="Ranking is withheld until eligibility is confirmed.",
        )
    text = job.title + " " + job.description_text
    required = [skill for skill in SKILLS if contains(text, skill)]
    # A fact supports a skill only when its verified statement mentions that skill.
    matched = [
        skill for skill in required if any(contains(f.statement, skill) for f in profile.facts)
    ]
    fact_ids = [
        fact.id
        for fact in profile.facts
        if any(contains(fact.statement, skill) for skill in matched)
    ]
    project_skills = [
        skill
        for skill in matched
        if any(
            fact.category == "project" and contains(fact.statement, skill) for fact in profile.facts
        )
    ]
    role_terms = [
        term
        for term in ["backend", "frontend", "full stack", "software", "API", "web"]
        if contains(text, term)
    ]
    role_evidence = sum(
        any(contains(f.statement, term) for f in profile.facts) for term in role_terms
    )
    components = Components(
        skills=round(100 * len(matched) / len(required)) if required else 0,
        role=round(100 * role_evidence / len(role_terms)) if role_terms else 0,
        experience=50 if any(f.category == "experience" for f in profile.facts) else 0,
        projects=round(100 * len(project_skills) / len(required)) if required else 0,
    )
    return MatchResult(
        eligibility_status=status,
        eligibility_reasons=reasons,
        score=total(components),
        component_scores=components,
        matched_profile_fact_ids=fact_ids,
        matched_skills=matched,
        missing_skills=[s for s in required if s not in matched],
        confidence="medium" if required and fact_ids else "low",
        reason="Deterministic overlap with verified facts. Keyword coverage may miss requirements; "
        "this is a relative fit estimate, not a hiring probability.",
    )


def cache_key(job: Job, profile_version: int, provider: str, model: str) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                str(job.id),
                job.description_hash,
                job.status,
                profile_version,
                provider,
                model,
                PROMPT_VERSION,
            ]
        ).encode()
    ).hexdigest()


def cached(session: Session, job: Job, version: int, provider: str, model: str) -> JobMatch | None:
    return session.scalar(
        select(JobMatch).where(
            JobMatch.user_id == LOCAL_USER_ID,
            JobMatch.job_id == job.id,
            JobMatch.cache_key == cache_key(job, version, provider, model),
        )
    )


def save_match(session: Session, job: Job, profile: Profile, result: MatchResult) -> JobMatch:
    key = cache_key(job, profile.current_version, result.provider, result.model_id)
    existing = cached(session, job, profile.current_version, result.provider, result.model_id)
    if existing:
        return existing
    row = JobMatch(
        user_id=LOCAL_USER_ID,
        job_id=job.id,
        cache_key=key,
        profile_version=profile.current_version,
        job_hash=job.description_hash,
        job_status=job.status,
        provider=result.provider,
        model_id=result.model_id,
        prompt_version=PROMPT_VERSION,
        result_json=result.model_dump(mode="json"),
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
        return row
    except IntegrityError:
        return cached(session, job, profile.current_version, result.provider, result.model_id)


def evaluate(
    session: Session, job: Job, profile: Profile, use_ai: bool = False
) -> tuple[JobMatch, bool]:
    settings = get_settings()
    # Select only input fields; profile response IDs and version are not external input facts.
    source_profile = ProfileInput(
        full_name=profile.full_name, facts=profile.facts_json, preferences=profile.preferences_json
    )
    result = deterministic(job, source_profile)
    requested = False
    if use_ai and result.eligibility_status == "ELIGIBLE":
        if settings.llm_provider == "gemini" and settings.gemini_api_key and settings.llm_model:
            existing = cached(session, job, profile.current_version, "gemini", settings.llm_model)
            if existing:
                return existing, False
            requested = True
            try:
                ai = analyze(settings, source_profile, job.title, job.description_text)
                supported = [f for f in source_profile.facts if f.id in ai.matched_profile_fact_ids]
                result = result.model_copy(
                    update={
                        "provider": "gemini",
                        "model_id": settings.llm_model,
                        "score": total(ai.component_scores),
                        "component_scores": ai.component_scores,
                        "confidence": ai.confidence,
                        "reason": ai.reason,
                        "matched_profile_fact_ids": ai.matched_profile_fact_ids,
                        "missing_skills": ai.missing_skills,
                        "matched_skills": [
                            s
                            for s in ai.required_skills
                            if any(contains(f.statement, s) for f in supported)
                        ],
                    }
                )
            except AIError as error:
                result.warning = str(error)
        else:
            result.warning = "AI_NOT_CONFIGURED"
    row = save_match(session, job, profile, result)
    return row, requested
