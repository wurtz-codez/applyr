from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import app
from app.schemas.profile import ProfileInput

AUTH = {"Authorization": "Bearer " + "test-token-" + "a" * 48}
FACT = {
    "id": "skill-python", "category": "skill", "statement": "Python",
    "evidence_source": "Candidate confirmation", "is_verified": True,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
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


def test_health_and_auth(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/v1/profile").status_code == 401
    assert client.put("/api/v1/profile", json={"full_name": "Anyone"}).status_code == 401
    wrong = client.get("/api/v1/auth/check", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401
    assert client.get("/api/v1/auth/check", headers=AUTH).status_code == 200


def test_profile_persists_and_versions_only_real_changes(client):
    assert client.get("/api/v1/profile", headers=AUTH).status_code == 404
    payload = {"full_name": "Test Candidate", "facts": [FACT]}
    created = client.put("/api/v1/profile", json=payload, headers=AUTH)
    assert created.status_code == 200
    first = created.json()
    assert first["current_version"] == 1
    assert first["preferences"]["country_codes"] == ["IN"]
    assert client.get("/api/v1/profile", headers=AUTH).json()["id"] == first["id"]
    same = client.put("/api/v1/profile", json=payload, headers=AUTH).json()
    assert same["current_version"] == 1
    changed = client.put(
        "/api/v1/profile", json={**payload, "full_name": "Updated Candidate"}, headers=AUTH,
    ).json()
    assert changed["current_version"] == 2
    assert changed["id"] == first["id"]


@pytest.mark.parametrize("facts", [
    [{**FACT, "is_verified": False}], [FACT, FACT], [{**FACT, "evidence_source": ""}],
])
def test_reject_unverified_or_ambiguous_facts(client, facts):
    result = client.put(
        "/api/v1/profile", json={"full_name": "Test", "facts": facts}, headers=AUTH,
    )
    assert result.status_code == 422


def test_profile_contract_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ProfileInput(full_name="Test", fabricated_field=True)


@pytest.mark.parametrize("overrides", [
    {"api_token": "short"}, {"auto_submit_enabled": True},
    {"application_mode": "automatic"}, {"llm_provider": "unimplemented"},
])
def test_unsafe_or_unimplemented_configuration_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_migration_roundtrip(tmp_path, monkeypatch):
    database = tmp_path / "roundtrip.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database}")
        assert {"users", "profiles"} <= set(inspect(engine).get_table_names())
        engine.dispose()
        command.downgrade(config, "base")
        engine = create_engine(f"sqlite:///{database}")
        assert "profiles" not in inspect(engine).get_table_names()
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_worker_task_runs_without_broker():
    from app.workers.tasks import healthcheck

    assert healthcheck.run() == {"status": "ok"}
