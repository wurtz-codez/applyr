import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://localhost/applyr_test",
)
if TEST_DATABASE_URL.startswith("postgres://"):
    TEST_DATABASE_URL = "postgresql+psycopg://" + TEST_DATABASE_URL.removeprefix("postgres://")
elif TEST_DATABASE_URL.startswith("postgresql://"):
    TEST_DATABASE_URL = "postgresql+psycopg://" + TEST_DATABASE_URL.removeprefix("postgresql://")

os.environ["JOBS_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["API_TOKEN"] = "test-token-" + "a" * 48
os.environ["TAVILY_API_KEY"] = ""
os.environ["ENRICH_WEB_RESULTS"] = "false"

from app.config import get_settings  # noqa: E402
from app.database import Base, get_engine, migrate  # noqa: E402
from app.models import RunLock  # noqa: E402


def ensure_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    name = url.database or ""
    if not name.endswith("_test") or not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError(
            "Tests only run against a dedicated PostgreSQL database whose name ends in _test."
        )

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("select 1 from pg_database where datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()


def reset_test_database() -> None:
    get_settings.cache_clear()
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with get_engine().begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        connection.execute(RunLock.__table__.insert().values(id=1))


@pytest.fixture(scope="session", autouse=True)
def postgres_database():
    ensure_test_database()
    get_settings.cache_clear()
    get_engine.cache_clear()
    migrate()
    yield
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client():
    reset_test_database()
    from app.main import app

    with TestClient(app) as value:
        yield value
    get_settings.cache_clear()
