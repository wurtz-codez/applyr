from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.profile import LOCAL_USER_ID, Profile, User


def get_profile(session: Session) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.user_id == LOCAL_USER_ID))


def lock_local_user(session: Session) -> None:
    # An early write also serializes SQLite writers; SELECT FOR UPDATE handles PostgreSQL.
    session.execute(update(User).where(User.id == LOCAL_USER_ID).values(email=User.email))
    session.execute(select(User).where(User.id == LOCAL_USER_ID).with_for_update()).scalar_one()
