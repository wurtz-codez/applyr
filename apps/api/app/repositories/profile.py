from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import LOCAL_USER_ID, Profile, User


def get_profile(session: Session) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.user_id == LOCAL_USER_ID))


def lock_local_user(session: Session) -> None:
    # Serialize revisions on PostgreSQL. SQLite is for single-process development only.
    session.execute(select(User).where(User.id == LOCAL_USER_ID).with_for_update()).scalar_one()
