from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session
from app.ingestion.engine import queue_run
from app.ingestion.matching import ProfileInput
from app.ingestion.schemas import SourceCreate, SourcePatch
from app.ingestion.service import register_source, run_response, source_response
from app.models import IngestionRun, IngestionSource, Job, JobSource, MatchingProfile, now

router = APIRouter()


@router.post("/matching/profiles", status_code=202)
def matching_profile(payload: ProfileInput, session: Session = Depends(get_session)):
    values = {"configuration": payload.model_dump(), "needs_refresh": True, "updated_at": now()}
    profile_id = session.scalar(
        insert(MatchingProfile)
        .values(user_key=payload.user_key, **values)
        .on_conflict_do_update(index_elements=["user_key"], set_=values)
        .returning(MatchingProfile.id)
    )
    session.commit()
    return {"id": profile_id, "status": "PENDING", "user_key": payload.user_key}


@router.get("/matching/profiles")
def matching_profiles(
    page: int = Query(1, ge=1, le=100000), session: Session = Depends(get_session)
):
    rows = session.scalars(
        select(MatchingProfile).order_by(MatchingProfile.id).offset((page - 1) * 25).limit(25)
    )
    return {
        "items": [
            {
                "id": p.id,
                "user_key": p.user_key,
                "pending": p.needs_refresh,
                "updated_at": p.updated_at,
            }
            for p in rows
        ],
        "page": page,
    }


def source_or_404(session, source_id):
    row = session.get(IngestionSource, source_id)
    if row is None:
        raise HTTPException(404, {"code": "SOURCE_NOT_FOUND"})
    return row


@router.get("/sources/registry")
def registry(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    rows = session.scalars(
        select(IngestionSource)
        .order_by(IngestionSource.created_at.desc(), IngestionSource.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [source_response(session, s) for s in rows],
        "page": page,
        "page_size": page_size,
        "total": session.scalar(select(func.count()).select_from(IngestionSource)),
    }


@router.post("/sources", status_code=201)
def add_source(payload: SourceCreate, session: Session = Depends(get_session)):
    try:
        return source_response(session, register_source(session, payload))
    except ValueError as exc:
        session.rollback()
        code = str(exc)
        raise HTTPException(
            409 if code == "SOURCE_ALREADY_REGISTERED" else 422, {"code": code}
        ) from None


@router.get("/sources/{source_id}")
def source_detail(source_id: UUID, session: Session = Depends(get_session)):
    return source_response(session, source_or_404(session, source_id))


@router.patch("/sources/{source_id}")
def patch_source(source_id: UUID, payload: SourcePatch, session: Session = Depends(get_session)):
    source = source_or_404(session, source_id)
    for key, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(source, key, value)
    session.commit()
    return source_response(session, source)


def enqueue(session, source_id):
    source_or_404(session, source_id)
    try:
        run = queue_run(session, source_id)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, {"code": str(exc)}) from None
    # The committed run is the durable queue. Beat dispatches pending rows, so
    # API latency and availability do not depend on Redis or a running worker.
    return {**run_response(run), "task_id": str(run.id), "dispatched": False}


@router.post("/sources/{source_id}/sync", status_code=202)
def sync_source(source_id: UUID, session: Session = Depends(get_session)):
    return enqueue(session, source_id)


@router.post("/ingestion/sync", status_code=202)
def sync_all(limit: int = Query(100, ge=1, le=1000), session: Session = Depends(get_session)):
    ids = session.scalars(
        select(IngestionSource.id)
        .where(
            IngestionSource.enabled.is_(True),
            IngestionSource.access_policy.in_(["public_api", "permitted"]),
        )
        .order_by(IngestionSource.id)
        .limit(limit)
    ).all()
    results = []
    for source_id in ids:
        try:
            results.append(enqueue(session, source_id))
        except HTTPException as exc:
            results.append({"source_id": source_id, "error": exc.detail})
    return {"items": results}


@router.get("/ingestion/runs")
def runs(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(25, ge=1, le=100),
    source_id: UUID | None = None,
    session: Session = Depends(get_session),
):
    query = select(IngestionRun)
    if source_id:
        query = query.where(IngestionRun.source_id == source_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(IngestionRun.started_at.desc(), IngestionRun.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [run_response(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/ingestion/runs/{run_id}")
def run_detail(run_id: UUID, session: Session = Depends(get_session)):
    row = session.get(IngestionRun, run_id)
    if row is None:
        raise HTTPException(404, {"code": "RUN_NOT_FOUND"})
    return run_response(row)


@router.get("/ingestion/stats")
def stats(session: Session = Depends(get_session)):
    health = session.execute(
        select(IngestionSource.health, func.count()).group_by(IngestionSource.health)
    )
    statuses = session.execute(
        select(IngestionRun.status, func.count()).group_by(IngestionRun.status)
    )
    return {
        "source_health": dict(health.all()),
        "run_status": dict(statuses.all()),
        "jobs": session.scalar(select(func.count()).select_from(Job)),
        "occurrences": session.scalar(select(func.count()).select_from(JobSource)),
        "last_success_at": session.scalar(select(func.max(IngestionSource.last_success_at))),
    }
