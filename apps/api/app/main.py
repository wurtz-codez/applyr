from contextlib import asynccontextmanager
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session, migrate
from app.discovery import create_run, execute_run, run_response
from app.models import DiscoveryRun, Job, SourceState, now
from app.queries import Filters, facets, filtered, list_jobs, serialize_many, total
from app.schemas import DiscoveryInput, JobResponse, JobsPage, RunResponse
from app.sources import PROVIDERS

bearer = HTTPBearer(auto_error=False)


def auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None or not compare_digest(
        credentials.credentials.encode(), get_settings().api_token.get_secret_value().encode()
    ):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})


@asynccontextmanager
async def lifespan(app):
    migrate()
    yield


app = FastAPI(
    title="Applyr Jobs Backend",
    version="0.2.0",
    lifespan=lifespan,
    description="Multi-source job collection and filterable dashboard data. Backend only.",
)
api = APIRouter(prefix="/api/v1", dependencies=[Depends(auth)])


@app.get("/healthz")
def health():
    return {"status": "ok"}


@api.get("/jobs", response_model=JobsPage)
def jobs(filters: Annotated[Filters, Query()], session: Session = Depends(get_session)):
    return list_jobs(session, filters)


@api.get("/jobs/filters")
def job_filters(filters: Annotated[Filters, Query()], session: Session = Depends(get_session)):
    return facets(session, filters)


@api.get("/jobs/{job_id}", response_model=JobResponse)
def detail(job_id: UUID, session: Session = Depends(get_session)):
    row = session.get(Job, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    return serialize_many(session, [row], detail=True)[0]


@api.get("/dashboard")
def dashboard(filters: Annotated[Filters, Query()], session: Session = Depends(get_session)):
    query = filtered(filters)
    latest = session.scalar(select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(1))
    return {
        "total": total(session, query),
        "job_postings": total(session, query.where(Job.listing_type == "JOB_POSTING")),
        "search_results": total(session, query.where(Job.listing_type == "SEARCH_RESULT")),
        "remote": total(session, query.where(Job.work_mode == "REMOTE")),
        "new_today": total(
            session,
            query.where(
                Job.first_seen_at >= now().replace(hour=0, minute=0, second=0, microsecond=0)
            ),
        ),
        "companies": session.scalar(
            select(func.count(func.distinct(Job.company))).where(
                Job.id.in_(query.with_only_columns(Job.id))
            )
        )
        or 0,
        "last_run": run_response(latest).model_dump(mode="json") if latest else None,
    }


@api.get("/sources")
def sources(session: Session = Depends(get_session)):
    results = []
    for key, item in PROVIDERS.items():
        last_success = session.scalar(
            select(func.max(SourceState.last_success_at)).where(SourceState.provider == key)
        )
        results.append(
            {
                "id": key,
                "name": item["name"],
                "attribution_url": item["url"],
                "configured": key != "tavily" or bool(get_settings().tavily_api_key),
                "minimum_refresh_seconds": item["interval"],
                "last_success_at": last_success,
                "kind": "web_search" if key == "tavily" else "public_feed",
            }
        )
    return results


@api.post("/discovery/runs", response_model=RunResponse, status_code=202)
def refresh(
    payload: DiscoveryInput, background: BackgroundTasks, session: Session = Depends(get_session)
):
    row = create_run(session, payload)
    response = run_response(row)
    background.add_task(execute_run, row.id, session.get_bind())
    return response


@api.get("/discovery/runs", response_model=list[RunResponse])
def history(limit: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_session)):
    rows = session.scalars(
        select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(limit)
    )
    return [run_response(row) for row in rows]


@api.get("/discovery/runs/{run_id}", response_model=RunResponse)
def run_detail(run_id: UUID, session: Session = Depends(get_session)):
    row = session.get(DiscoveryRun, run_id)
    if row is None:
        raise HTTPException(404, "Refresh run not found")
    return run_response(row)


app.include_router(api)
