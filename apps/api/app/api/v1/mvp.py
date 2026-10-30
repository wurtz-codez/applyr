from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.models.discovery import AgentRun, Application, Company, Job, JobMatch, Resume, Shortlist
from app.models.profile import LOCAL_USER_ID
from app.repositories.jobs import count_query, jobs_query, summarize
from app.repositories.profile import get_profile, lock_local_user
from app.schemas.discovery import (
    ApplicationInput,
    ApplicationResponse,
    ApplicationsResponse,
    CompanyInput,
    CompanyResponse,
    CompanyUpdate,
    DashboardStats,
    DiscoverInput,
    JobDetail,
    JobsResponse,
    MatchResult,
    ResumeResponse,
    RunResponse,
    SettingsSummary,
)
from app.services.discovery import create_run, execute_run, finish_run
from app.services.matching import evaluate
from app.services.resumes import MAX_RESUME_BYTES, set_default, upload

router = APIRouter()


@router.get("/settings", response_model=SettingsSummary)
def settings_summary() -> dict:
    settings = get_settings()
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "ai_configured": settings.llm_provider == "gemini"
        and bool(settings.gemini_api_key)
        and bool(settings.llm_model),
        "ai_max_jobs_per_run": settings.ai_max_jobs_per_run,
        "discovery_executor": settings.discovery_executor,
        "discovery_schedule_enabled": settings.discovery_schedule_enabled,
        "discovery_interval_hours": settings.discovery_interval_hours,
        "resume_max_bytes": MAX_RESUME_BYTES,
    }


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(session: Session = Depends(get_session)):
    return session.scalars(select(Company).order_by(Company.name)).all()


@router.post("/companies", response_model=CompanyResponse, status_code=201)
def add_company(payload: CompanyInput, session: Session = Depends(get_session)):
    lock_local_user(session)
    if (session.scalar(select(func.count()).select_from(Company)) or 0) >= 20:
        raise HTTPException(409, "The MVP supports up to 20 configured company boards")
    row = Company(**payload.model_dump())
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "This company board is already configured") from None
    session.refresh(row)
    return row


@router.patch("/companies/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID, payload: CompanyUpdate, session: Session = Depends(get_session)
):
    row = session.get(Company, company_id)
    if row is None:
        raise HTTPException(404, "Company board not found")
    row.enabled = payload.enabled
    session.commit()
    session.refresh(row)
    return row


@router.post("/jobs/discover", response_model=RunResponse, status_code=202)
def discover(
    payload: DiscoverInput, background: BackgroundTasks, session: Session = Depends(get_session)
):
    run = create_run(session, payload.use_ai)
    response = RunResponse.model_validate(run)
    if get_settings().discovery_executor == "celery":
        from app.workers.tasks import execute_discovery

        try:
            execute_discovery.delay(str(run.id))
        except Exception:
            finish_run(session, run.id, "FAILED", "QUEUE_UNAVAILABLE")
            raise HTTPException(503, "The job queue is unavailable") from None
    else:
        background.add_task(execute_run, run.id, session.get_bind())
    return response


@router.get("/jobs", response_model=JobsResponse)
def list_jobs(
    q: str = Query(default="", max_length=200),
    eligibility: Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_REVIEW"] | None = None,
    min_score: int = Query(default=0, ge=0, le=100),
    shortlisted: bool = False,
    status: Literal["OPEN", "CLOSED"] = "OPEN",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    query, _ = jobs_query(session)
    query = query.where(Job.status == status)
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            Job.title.ilike(pattern, escape="\\")
            | Company.name.ilike(pattern, escape="\\")
            | Job.location_text.ilike(pattern, escape="\\")
        )
    if eligibility:
        query = query.where(JobMatch.result_json["eligibility_status"].as_string() == eligibility)
    if min_score:
        query = query.where(JobMatch.result_json["score"].as_integer() >= min_score)
    if shortlisted:
        query = query.where(Shortlist.id.is_not(None))
    total = count_query(session, query)
    rows = session.execute(
        query.order_by(
            JobMatch.result_json["score"].as_integer().desc().nulls_last(),
            Job.last_seen_at.desc(),
            Job.id,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    return JobsResponse(
        items=[summarize(row) for row in rows], total=total, offset=offset, limit=limit
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
def job_detail(job_id: UUID, session: Session = Depends(get_session)):
    query, profile = jobs_query(session)
    row = session.execute(query.where(Job.id == job_id)).first()
    if row is None:
        raise HTTPException(404, "Job not found")
    return summarize(row, detail=True, profile=profile)


@router.post("/jobs/{job_id}/match", response_model=MatchResult)
def match_job(job_id: UUID, payload: DiscoverInput, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    profile = get_profile(session)
    if job is None:
        raise HTTPException(404, "Job not found")
    if profile is None or not profile.facts_json:
        raise HTTPException(409, "Add verified profile facts before matching")
    row, _ = evaluate(session, job, profile, payload.use_ai)
    session.commit()
    return MatchResult.model_validate(row.result_json)


@router.post("/jobs/{job_id}/shortlist", status_code=204)
def shortlist(job_id: UUID, session: Session = Depends(get_session)):
    lock_local_user(session)
    if session.get(Job, job_id) is None:
        raise HTTPException(404, "Job not found")
    existing = session.scalar(
        select(Shortlist).where(
            Shortlist.user_id == LOCAL_USER_ID,
            Shortlist.job_id == job_id,
        )
    )
    if not existing:
        session.add(Shortlist(user_id=LOCAL_USER_ID, job_id=job_id))
        session.commit()


@router.delete("/jobs/{job_id}/shortlist", status_code=204)
def remove_shortlist(job_id: UUID, session: Session = Depends(get_session)):
    row = session.scalar(
        select(Shortlist).where(
            Shortlist.user_id == LOCAL_USER_ID,
            Shortlist.job_id == job_id,
        )
    )
    if row:
        session.delete(row)
        session.commit()


@router.get("/runs", response_model=list[RunResponse])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_session)
):
    return session.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)).all()


@router.get("/runs/{run_id}", response_model=RunResponse)
def read_run(run_id: UUID, session: Session = Depends(get_session)):
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(session: Session = Depends(get_session)) -> dict:
    query, profile = jobs_query(session)
    query = query.where(Job.status == "OPEN")
    latest = session.scalar(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(1))
    return {
        "active_jobs": count_query(session, query),
        "eligible_jobs": count_query(
            session,
            query.where(JobMatch.result_json["eligibility_status"].as_string() == "ELIGIBLE"),
        ),
        "strong_matches": count_query(
            session, query.where(JobMatch.result_json["score"].as_integer() >= 80)
        ),
        "new_today": count_query(
            session,
            query.where(
                Job.first_seen_at
                >= datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            ),
        ),
        "shortlisted": count_query(session, query.where(Shortlist.id.is_not(None))),
        "profile_version": profile.current_version if profile else None,
        "latest_run": RunResponse.model_validate(latest).model_dump(mode="json")
        if latest
        else None,
    }


@router.get("/resumes", response_model=list[ResumeResponse])
def list_resumes(session: Session = Depends(get_session)):
    return session.scalars(
        select(Resume).where(Resume.user_id == LOCAL_USER_ID).order_by(Resume.version.desc())
    ).all()


@router.get("/resumes/default", response_model=ResumeResponse)
def default_resume(session: Session = Depends(get_session)):
    row = session.scalar(
        select(Resume).where(
            Resume.user_id == LOCAL_USER_ID,
            Resume.is_default.is_(True),
        )
    )
    if row is None:
        raise HTTPException(404, "Upload and select a default resume first")
    return row


@router.post(
    "/resumes",
    response_model=ResumeResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload_resume(
    request: Request,
    filename: str = Query(min_length=1, max_length=200),
    session: Session = Depends(get_session),
):
    if request.headers.get("content-type", "").split(";")[0] != "application/pdf":
        raise HTTPException(415, "Only PDF resumes are supported")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_RESUME_BYTES:
            raise HTTPException(413, "PDF must be at most 5 MiB")
    return upload(session, bytes(data), filename)


@router.post("/resumes/{resume_id}/default", response_model=ResumeResponse)
def choose_default(resume_id: UUID, session: Session = Depends(get_session)):
    row = session.get(Resume, resume_id)
    if row is None or row.user_id != LOCAL_USER_ID:
        raise HTTPException(404, "Resume not found")
    return set_default(session, row)


@router.get("/resumes/{resume_id}/download")
def download_resume(resume_id: UUID, session: Session = Depends(get_session)):
    row = session.get(Resume, resume_id)
    if row is None or row.user_id != LOCAL_USER_ID:
        raise HTTPException(404, "Resume not found")
    root = (get_settings().storage_dir / "resumes").resolve()
    path = (root / row.file_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(404, "Resume file is unavailable")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=row.original_filename,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post("/jobs/{job_id}/application", response_model=ApplicationResponse)
def track_application(
    job_id: UUID, payload: ApplicationInput, session: Session = Depends(get_session)
):
    lock_local_user(session)
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    row = session.scalar(
        select(Application).where(
            Application.user_id == LOCAL_USER_ID,
            Application.job_id == job_id,
        )
    )
    if row is None:
        resume = session.scalar(
            select(Resume).where(
                Resume.user_id == LOCAL_USER_ID,
                Resume.is_default.is_(True),
            )
        )
        row = Application(
            user_id=LOCAL_USER_ID, job_id=job_id, resume_id=resume.id if resume else None
        )
        session.add(row)
    row.status, row.notes, row.updated_at = payload.status, payload.notes, datetime.now(UTC)
    session.commit()
    session.refresh(row)
    return serialize_application(session, row)


def serialize_application(session: Session, row: Application) -> ApplicationResponse:
    job = session.get(Job, row.job_id)
    company = session.get(Company, job.company_id)
    resume = session.get(Resume, row.resume_id) if row.resume_id else None
    return ApplicationResponse(
        id=row.id,
        job_id=job.id,
        title=job.title,
        company=company.name,
        source_url=job.source_url,
        resume_id=row.resume_id,
        resume_version=resume.version if resume else None,
        status=row.status,
        notes=row.notes,
        applied_at=row.applied_at,
        updated_at=row.updated_at,
    )


@router.get("/applications", response_model=ApplicationsResponse)
def list_applications(
    job_id: UUID | None = None,
    status: Literal["APPLIED", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    query = select(Application).where(Application.user_id == LOCAL_USER_ID)
    if job_id:
        query = query.where(Application.job_id == job_id)
    if status:
        query = query.where(Application.status == status)
    total = count_query(session, query)
    rows = session.scalars(
        query.order_by(Application.updated_at.desc()).offset(offset).limit(limit)
    )
    return ApplicationsResponse(
        items=[serialize_application(session, row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )
