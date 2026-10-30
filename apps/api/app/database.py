from functools import lru_cache
from pathlib import Path

from sqlalchemy import MetaData, create_engine, event
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
    sqlite = url.startswith("sqlite")
    if sqlite and ":memory:" not in url:
        path = Path(url.removeprefix("sqlite:///"))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {},
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def get_session():
    with Session(get_engine()) as session:
        yield session


def migrate():
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
