from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_auth
from app.db.session import get_session
from app.repositories.profile import get_profile
from app.schemas.profile import ProfileInput, ProfileResponse
from app.services.profile import save_profile, serialize

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])


@router.get("/auth/check")
def auth_check() -> dict[str, str]:
    return {"status": "authenticated"}


@router.get("/profile", response_model=ProfileResponse)
def read_profile(session: Session = Depends(get_session)):
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(404, "Create your verified profile to get started")
    return serialize(profile)


@router.put("/profile", response_model=ProfileResponse)
def update_profile(payload: ProfileInput, session: Session = Depends(get_session)):
    return save_profile(session, payload)
