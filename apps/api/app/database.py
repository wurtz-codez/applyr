from functools import lru_cache
from pathlib import Path

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import get_settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }
    )


@lru_cache
def get_engine():
    url = get_settings().jobs_database_url
    if not url.startswith("postgresql"):
        raise RuntimeError(
            "Only PostgreSQL is supported. Set JOBS_DATABASE_URL to a PostgreSQL URL."
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


def get_session():
    with Session(get_engine()) as session:
        yield session


def migrate():
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
