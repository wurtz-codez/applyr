from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.profile import LOCAL_USER_ID, Profile
from app.repositories.profile import get_profile, lock_local_user
from app.schemas.profile import ProfileInput, ProfileResponse


def serialize(profile: Profile) -> ProfileResponse:
    timestamp = profile.updated_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return ProfileResponse(
        id=profile.id, full_name=profile.full_name, preferences=profile.preferences_json,
        facts=profile.facts_json, current_version=profile.current_version,
        updated_at=timestamp,
    )


def save_profile(session: Session, payload: ProfileInput) -> ProfileResponse:
    lock_local_user(session)
    profile = get_profile(session)
    values = payload.model_dump(mode="json")
    if profile is None:
        profile = Profile(
            user_id=LOCAL_USER_ID, full_name=payload.full_name,
            preferences_json=values["preferences"], facts_json=values["facts"],
        )
        session.add(profile)
    elif (profile.full_name, profile.preferences_json, profile.facts_json) != (
        payload.full_name, values["preferences"], values["facts"],
    ):
        profile.full_name = payload.full_name
        profile.preferences_json = values["preferences"]
        profile.facts_json = values["facts"]
        profile.current_version += 1
        profile.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(profile)
    return serialize(profile)
