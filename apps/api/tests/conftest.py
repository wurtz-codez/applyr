import os

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_engine

os.environ["API_TOKEN"] = "test-token-" + "a" * 48
os.environ["TAVILY_API_KEY"] = ""
os.environ["ENRICH_WEB_RESULTS"] = "false"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBS_DATABASE_URL", f"sqlite:///{tmp_path / 'jobs.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    from app.main import app

    with TestClient(app) as value:
        yield value
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()
