import os
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.db.session import get_session

os.environ["APP_ENV"] = "test"
os.environ["API_TOKEN"] = "test-token-" + "a" * 48
os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    database = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False})

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()
