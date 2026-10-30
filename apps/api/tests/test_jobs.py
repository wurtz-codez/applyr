from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.discovery import create_run, execute_run, store_jobs
from app.models import DiscoveryRun, RunLock, now
from app.schemas import DiscoveryInput, JobData
from app.sources import Batch, SourceError

AUTH = {"Authorization": "Bearer test-token-" + "a" * 48}


def record(number="1", **values):
    return JobData(
        canonical_url=f"https://jobs.example/role/{number}",
        source_url=f"https://jobs.example/role/{number}",
        title="Software Engineer",
        company="Acme",
        location="India",
        tags=["python", "sql"],
        work_mode="REMOTE",
        employment_type="Full-time",
        experience_level="Junior",
        salary_min=100000,
        salary_max=130000,
        salary_currency="USD",
        salary_period="yearly",
        published_at=now() - timedelta(days=1),
        **values,
    )


def populate(client):
    one = record()
    two = one.model_copy(
        update={
            "canonical_url": "https://jobs.example/two",
            "source_url": "https://jobs.example/two",
            "title": "Designer",
            "company": "Beta",
            "location": "Berlin",
            "work_mode": "UNKNOWN",
            "tags": ["design"],
            "published_at": None,
            "salary_min": 30,
            "salary_max": 40,
            "salary_period": "hourly",
        }
    )
    three = one.model_copy(
        update={
            "canonical_url": "https://jobs.example/search",
            "source_url": "https://jobs.example/search",
            "title": "Engineering jobs",
            "company": None,
            "location": None,
            "listing_type": "SEARCH_RESULT",
            "tags": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
            "work_mode": "UNKNOWN",
        }
    )
    with Session(get_engine()) as session:
        store_jobs(session, "arbeitnow", [one, two])
        store_jobs(session, "tavily", [three])
        store_jobs(session, "remotive", [one])
    return one


def test_filters_pagination_and_provenance(client):
    populate(client)
    response = client.get("/api/v1/jobs", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    filters = {
        "q": "software",
        "location": "india",
        "work_mode": "REMOTE",
        "employment_type": "Full-time",
        "experience_level": "junior",
        "tag": ["python", "sql"],
        "source": ["remotive"],
        "posted_within_days": 7,
    }
    listing = client.get("/api/v1/jobs", params=filters, headers=AUTH).json()
    assert listing["total"] == 1
    job = listing["items"][0]
    assert len(job["sources"]) == 2
    assert job["first_seen_at"].endswith("Z")
    assert job["primary_source"] == "arbeitnow"
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=AUTH).json()["tags"] == ["python", "sql"]
    salary = client.get(
        "/api/v1/jobs",
        params={"min_salary": 90000, "currency": "USD", "salary_period": "yearly"},
        headers=AUTH,
    ).json()
    assert salary["total"] == 1
    assert client.get("/api/v1/jobs?min_salary=10", headers=AUTH).status_code == 422
    assert client.get("/api/v1/jobs?sort=salary_desc", headers=AUTH).status_code == 422
    assert client.get("/api/v1/jobs?posted_within_days=7", headers=AUTH).json()["total"] == 2
    page1 = client.get("/api/v1/jobs?page_size=1", headers=AUTH).json()
    page2 = client.get("/api/v1/jobs?page_size=1&page=2", headers=AUTH).json()
    assert page1["total_pages"] == 3 and page1["items"][0]["id"] != page2["items"][0]["id"]
    assert client.get("/api/v1/jobs?page_size=101", headers=AUTH).status_code == 422
    assert client.get("/api/v1/jobs?unknown=oops", headers=AUTH).status_code == 422
    facets = client.get("/api/v1/jobs/filters?work_mode=REMOTE", headers=AUTH).json()
    assert facets["company"] == [{"value": "Acme", "count": 1}]
    stats = client.get("/api/v1/dashboard", headers=AUTH).json()
    assert stats["total"] == 3 and stats["job_postings"] == 2 and stats["search_results"] == 1


def test_exact_url_dedupe_and_quality_upgrade(client):
    source = record()
    candidate = source.model_copy(update={"company": None, "listing_type": "SEARCH_RESULT"})
    with Session(get_engine()) as session:
        assert store_jobs(session, "tavily", [candidate])["new"] == 1
        assert store_jobs(session, "arbeitnow", [source])["updated"] == 1
        assert store_jobs(session, "tavily", [candidate])["unchanged"] == 1
        assert store_jobs(session, "arbeitnow", [source])["unchanged"] == 1
    job = client.get("/api/v1/jobs", headers=AUTH).json()["items"][0]
    assert job["listing_type"] == "JOB_POSTING" and job["company"] == "Acme"
    first_seen, job_id = job["first_seen_at"], job["id"]
    with Session(get_engine()) as session:
        store_jobs(session, "arbeitnow", [source.model_copy(update={"title": "Updated role"})])
    changed = client.get("/api/v1/jobs", headers=AUTH).json()["items"][0]
    assert changed["id"] == job_id and changed["first_seen_at"] == first_seen


def test_refresh_progress_cache_and_partial_failure(client, monkeypatch):
    calls = []

    def fetch(provider, query):
        calls.append(provider)
        if provider == "remotive":
            raise SourceError("RATE_LIMITED", 3600)
        return Batch(jobs=[record()])

    monkeypatch.setattr("app.discovery.fetch", fetch)
    response = client.post(
        "/api/v1/discovery/runs", json={"providers": ["arbeitnow", "remotive"]}, headers=AUTH
    )
    assert response.status_code == 202
    run = client.get(f"/api/v1/discovery/runs/{response.json()['id']}", headers=AUTH).json()
    assert run["status"] == "PARTIAL_FAILED"
    assert run["results"][0]["new"] == 1 and run["results"][1]["error_code"] == "RATE_LIMITED"
    repeated = client.post(
        "/api/v1/discovery/runs", json={"providers": ["arbeitnow", "remotive"]}, headers=AUTH
    )
    again = client.get(f"/api/v1/discovery/runs/{repeated.json()['id']}", headers=AUTH).json()
    assert again["results"][0]["status"] == "CACHED"
    assert again["results"][1]["status"] == "COOLDOWN" and len(calls) == 2
    assert client.get("/api/v1/jobs", headers=AUTH).json()["total"] == 1


def test_discovery_lock_recovery_and_duplicate_delivery(client, monkeypatch):
    monkeypatch.setattr("app.discovery.fetch", lambda provider, query: Batch(jobs=[record()]))
    with Session(get_engine()) as session:
        old = create_run(session, DiscoveryInput(providers=["arbeitnow"]))
        old_id = old.id
        import pytest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            create_run(session, DiscoveryInput(providers=["arbeitnow"]))
        assert error.value.status_code == 409
        lock = session.get(RunLock, 1)
        lock.expires_at = now() - timedelta(seconds=1)
        session.commit()
        new = create_run(session, DiscoveryInput(providers=["arbeitnow"]))
        new_id = new.id
        assert session.get(DiscoveryRun, old_id).status == "INTERRUPTED"
    execute_run(new_id)
    execute_run(new_id)
    assert client.get("/api/v1/jobs", headers=AUTH).json()["total"] == 1


def test_search_budget_and_key_privacy(client, monkeypatch):
    assert (
        client.post(
            "/api/v1/discovery/runs", json={"providers": ["tavily"]}, headers=AUTH
        ).status_code
        == 409
    )
    monkeypatch.setenv("TAVILY_API_KEY", "secret-test-key")
    monkeypatch.setenv("MAX_SEARCH_REQUESTS_PER_DAY", "1")
    get_settings.cache_clear()
    monkeypatch.setattr("app.discovery.fetch", lambda provider, query: Batch(jobs=[record()]))
    first = client.post(
        "/api/v1/discovery/runs",
        json={"providers": ["tavily"], "query": "alpha jobs"},
        headers=AUTH,
    )
    assert first.status_code == 202
    second = client.post(
        "/api/v1/discovery/runs", json={"providers": ["tavily"], "query": "beta jobs"}, headers=AUTH
    )
    run = client.get(f"/api/v1/discovery/runs/{second.json()['id']}", headers=AUTH).json()
    assert run["results"][0]["error_code"] == "DAILY_SEARCH_BUDGET"
    assert "secret-test-key" not in client.get("/api/v1/sources", headers=AUTH).text


def test_api_authentication_and_literal_search(client):
    for path in ["/jobs", "/jobs/filters", "/dashboard", "/sources", "/discovery/runs"]:
        assert client.get("/api/v1" + path).status_code == 401
    assert client.get("/healthz").status_code == 200
    assert client.post("/api/v1/discovery/runs", json={}).status_code == 401
    with Session(get_engine()) as session:
        store_jobs(
            session,
            "arbeitnow",
            [record(), record("2").model_copy(update={"title": "Engineer_100%"})],
        )
    assert client.get("/api/v1/jobs?q=%25", headers=AUTH).json()["total"] == 1
    assert client.get("/api/v1/jobs?q=_", headers=AUTH).json()["total"] == 1
