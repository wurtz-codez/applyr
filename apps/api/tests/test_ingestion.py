import asyncio
import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.ingestion.connectors.ats import Ashby, Greenhouse, Lever, SmartRecruiters
from app.ingestion.connectors.generic import Generic, jsonld
from app.ingestion.deduplicator import ats_identity
from app.ingestion.discovery.ats_detector import detect
from app.ingestion.engine import ingest, queue_run, store_job
from app.ingestion.freshness import expire_jobs
from app.ingestion.http import HTTP, FetchFailure, retry_seconds
from app.ingestion.normalizer import experience, location
from app.ingestion.schemas import SourceConfig, SourceCreate
from app.ingestion.service import register_source
from app.models import IngestionRun, IngestionSource, Job, JobSource, now
from app.web_pages import PageFetcher

FIXTURE = json.loads((Path(__file__).parent / "fixtures/ats.json").read_text())
HEADERS = {"Authorization": "Bearer test-token-" + "a" * 48}


async def no_sleep(_):
    pass


def source_config(provider):
    return SourceConfig(provider=provider, board_id="example", company="Example")


def run_connector(factory, provider, handler, state=None, cursor=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            config = source_config(provider)
            config.state = state or {}
            return await factory(HTTP(client, interval=0, sleep=no_sleep)).fetch_jobs(
                config, cursor
            )

    return asyncio.run(run())


def test_greenhouse_parsing_incremental_descriptions():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        item = FIXTURE["greenhouse"]
        return httpx.Response(
            200,
            json={"jobs": [{k: v for k, v in item.items() if k != "content"}]}
            if request.url.path.endswith("/jobs")
            else item,
        )

    first = run_connector(Greenhouse, "greenhouse", handler)
    second = run_connector(Greenhouse, "greenhouse", handler, first.metadata)
    assert len(calls) == 3
    job = second.jobs[0]
    assert job.external_id == "123" and job.posted_at is None
    assert job.description.startswith("Python") and job.location.city == "Bengaluru"
    assert job.job_url.endswith("?utm_source=test")
    assert job.experience.min_years == 0 and job.experience.max_years == 2


def test_lever_parse_and_pagination():
    def handler(request):
        assert request.url.host == "api.lever.co"
        offset = int(request.url.params["skip"])
        return httpx.Response(
            200,
            json=[
                {**FIXTURE["lever"], "id": str(n)}
                for n in range(offset, offset + (100 if offset == 0 else 1))
            ],
        )

    first = run_connector(Lever, "lever", handler)
    second = run_connector(Lever, "lever", handler, first.metadata, first.next_cursor)
    assert first.next_cursor == "100" and second.next_cursor is None
    job = first.jobs[0]
    assert job.apply_url.endswith("/apply") and job.experience.min_years == 1
    assert job.experience.max_years is None and job.location.india_eligible is True
    assert "Requirements" in job.description and job.posted_at is None


def test_lever_eu_endpoint():
    async def run():
        def handler(request):
            assert request.url.host == "api.eu.lever.co"
            return httpx.Response(200, json=[])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            source = source_config("lever")
            source.configuration = {"region": "eu"}
            await Lever(HTTP(client, interval=0)).fetch_jobs(source)

    asyncio.run(run())


def test_ashby_public_endpoint_unlisted_and_hybrid():
    def handler(request):
        assert request.url.path == "/posting-api/job-board/example"
        return httpx.Response(
            200, json={"jobs": [FIXTURE["ashby"], {**FIXTURE["ashby"], "isListed": False}]}
        )

    result = run_connector(Ashby, "ashby", handler)
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.location.remote_type == "hybrid" and job.location.india_eligible is True
    assert job.posted_at is not None and job.employment_type == "Full-time"


def test_smartrecruiters_pagination_detail_cache_fixed_host():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.url.host == "api.smartrecruiters.com"
        if request.url.path.endswith("/postings"):
            offset = int(request.url.params["offset"])
            return httpx.Response(
                200,
                json={
                    "totalFound": 2,
                    "content": [
                        {
                            "id": f"sr-{offset + 1}",
                            "releasedDate": "2026-10-01",
                            "ref": "http://127.0.0.1/private",
                        }
                    ],
                },
            )
        return httpx.Response(200, json=FIXTURE["smartrecruiters"])

    first = run_connector(SmartRecruiters, "smartrecruiters", handler)
    second = run_connector(
        SmartRecruiters, "smartrecruiters", handler, first.metadata, first.next_cursor
    )
    assert first.next_cursor == "1" and second.next_cursor is None
    run_connector(SmartRecruiters, "smartrecruiters", handler, second.metadata)
    assert len(calls) == 5  # No detail download for unchanged list entry.
    assert first.jobs[0].location.india_eligible is True
    assert "PostgreSQL" in first.jobs[0].skills


@pytest.mark.parametrize(
    "factory,provider",
    [
        (Greenhouse, "greenhouse"),
        (Lever, "lever"),
        (Ashby, "ashby"),
        (SmartRecruiters, "smartrecruiters"),
    ],
)
def test_invalid_payload_is_not_empty_success(factory, provider):
    with pytest.raises(FetchFailure, match="INVALID_PAYLOAD"):
        run_connector(factory, provider, lambda r: httpx.Response(200, json={"error": "bad"}))


def test_http_timeouts_429_retry_and_conditionals():
    async def run():
        calls, sleeps = [], []

        async def sleep(value):
            sleeps.append(value)

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 2:
                return httpx.Response(200, headers={"etag": '"v1"'}, json={"jobs": []})
            assert request.headers["if-none-match"] == '"v1"'
            return httpx.Response(304)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            http = HTTP(client, interval=0, sleep=sleep)
            payload, cached, _ = await http.get("https://example.com/jobs")
            again, _, unchanged = await http.get("https://example.com/jobs", cached=cached)
            assert unchanged and payload == again and 2 in sleeps

        def timeout(request):
            raise httpx.ReadTimeout("timeout", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            http = HTTP(client, interval=0, sleep=no_sleep)
            with pytest.raises(FetchFailure, match="HTTP_TIMEOUT"):
                await http.get("https://example.com/jobs")
            assert http.requests == 3
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(429, headers={"Retry-After": "3600"})
            )
        ) as client:
            with pytest.raises(FetchFailure, match="HTTP_429") as error:
                await HTTP(client, interval=0, sleep=no_sleep).get("https://example.com/jobs")
            assert error.value.error.retry_after == 3600

    asyncio.run(run())
    assert retry_seconds("nonsense") == 0
    assert retry_seconds("Fri, 30 Oct 2099 00:00:00 GMT") > 30


def test_location_and_experience_uncertainty():
    assert location("Bangalore, India", "onsite").city == "Bengaluru"
    assert location("Bengaluru", "hybrid").india_eligible is True
    assert location("Remote", "remote").india_eligible is None
    assert location("US Remote", "remote").india_eligible is None
    assert location("Remote", "remote", eligible=["US"]).india_eligible is False
    assert location("Remote", "remote", eligible=["India"]).india_eligible is True
    assert location("Remote", "remote", globally_remote=True).india_eligible is True
    assert experience("New grad, Python required").min_years is None
    assert experience("0-2 years of professional experience").max_years == 2
    assert experience("3+ years of experience").min_years == 3
    assert experience("No prior experience required").min_years == 0


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://jobs.ashbyhq.com/example-company", ("ashby", "example-company")),
        ("https://boards.greenhouse.io/embed/job_board?for=example", ("greenhouse", "example")),
        ("https://jobs.eu.lever.co/example", ("lever", "example")),
        ("https://jobs.lever.co.evil.example/example", None),
    ],
)
def test_detection(url, expected):
    assert detect(url) == expected


def make_source(session, provider="ashby", board="example", **kwargs):
    return register_source(
        session,
        SourceCreate(
            company_name="Example",
            provider=provider,
            board_id=board,
            access_policy="public_api" if provider in {"ashby", "greenhouse"} else "permitted",
            permission_notes="Employer authorized",
            **kwargs,
        ),
    )


def pipeline(source_id, handler):
    with Session(get_engine()) as session:
        run_id = queue_run(session, source_id).id

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await ingest(run_id, http_client=http)

    asyncio.run(run())
    return run_id


def test_full_postgresql_pipeline_idempotency_api_and_failure_isolation(client):
    with Session(get_engine()) as session:
        source_id = make_source(session).id

    def handler(r):
        return httpx.Response(200, json={"jobs": [FIXTURE["ashby"]]})

    first_id, second_id = pipeline(source_id, handler), pipeline(source_id, handler)
    with Session(get_engine()) as session:
        first, second = session.get(IngestionRun, first_id), session.get(IngestionRun, second_id)
        assert first.inserted == 1 and second.inserted == 0 and second.updated == 0
        assert session.scalar(select(func.count()).select_from(JobSource)) == 1
    response = client.get(
        "/api/v1/jobs?source=ashby&india_eligible=true&include_uncertain=false", headers=HEADERS
    )
    assert response.status_code == 200 and response.json()["total"] == 1
    item = response.json()["items"][0]
    assert item["sources"][0]["provider"] == "ashby"
    assert item["normalized_json"]["location"]["city"] == "Bengaluru"
    assert client.get(f"/api/v1/jobs/{item['id']}", headers=HEADERS).json()["apply_url"]
    failed_id = pipeline(source_id, lambda r: httpx.Response(403))
    with Session(get_engine()) as session:
        assert session.get(IngestionRun, failed_id).status == "FAILED"
        source = session.get(IngestionSource, source_id)
        assert source.failure_count == 1 and source.health == "failing"
        assert session.get(Job, UUID(item["id"])).status == "active"
        assert source.last_success_at is not None


def test_cross_source_identity_url_requisition_and_no_title_only_merge(client):
    from app.ingestion.connectors.ats import base

    with Session(get_engine()) as session:
        source = make_source(session)
        item = base(
            source_config("ashby"),
            FIXTURE["ashby"],
            external_id="ashby-1",
            title="Software Engineer",
            url=FIXTURE["ashby"]["jobUrl"],
            apply=FIXTURE["ashby"]["applyUrl"],
            requisition="REQ-1",
            label="Bengaluru",
        )
        store_job(session, source, item)
        second = make_source(
            session, "career_page", "company-careers", career_url="https://example.com/jobs"
        )
        mirrored = item.model_copy(
            update={
                "source": "career_page",
                "external_id": "html-1",
                "job_url": "https://example.com/jobs/1",
            }
        )
        inserted, _, dedup = store_job(session, second, mirrored)
        assert not inserted and dedup
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        # Same title and location with independent identity stays a separate canonical job.
        other = item.model_copy(
            update={
                "external_id": "ashby-2",
                "requisition_id": None,
                "job_url": "https://jobs.ashbyhq.com/example/ashby-2",
                "apply_url": None,
            }
        )
        assert store_job(session, source, other)[0]
        session.commit()
        assert session.scalar(select(func.count()).select_from(JobSource)) == 3
        assert session.scalar(select(func.count()).select_from(Job)) == 2
        occurrences = session.scalars(
            select(JobSource).where(JobSource.external_id == "ashby-2")
        ).all()
        assert occurrences[0].metadata_json["candidate_job_ids"]
    assert (
        ats_identity("https://boards.greenhouse.io/example/jobs/123?utm_source=x")
        == "greenhouse:example:123"
    )


def test_source_api_validation_auth_lease_and_run_monitoring(client, monkeypatch):
    assert client.get("/api/v1/sources/registry").status_code == 401
    assert client.post("/api/v1/sources", json={}, headers=HEADERS).status_code == 422
    payload = {
        "company_name": "Example",
        "career_url": "https://jobs.ashbyhq.com/example",
        "access_policy": "public_api",
    }
    source = client.post("/api/v1/sources", json=payload, headers=HEADERS)
    assert source.status_code == 201
    source_id = source.json()["id"]
    assert source.json()["provider"] == "ashby" and source.json()["health"] == "unverified"
    assert client.post("/api/v1/sources", json=payload, headers=HEADERS).status_code == 409
    path = f"/api/v1/sources/{source_id}"
    first = client.post(path + "/sync", headers=HEADERS)
    second = client.post(path + "/sync", headers=HEADERS)
    assert first.status_code == 202 and first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "QUEUED"
    assert client.get("/api/v1/ingestion/runs", headers=HEADERS).json()["total"] == 1
    assert (
        client.get("/api/v1/ingestion/runs/" + first.json()["id"], headers=HEADERS).status_code
        == 200
    )
    assert (
        client.get("/api/v1/ingestion/stats", headers=HEADERS).json()["run_status"]["QUEUED"] == 1
    )
    assert client.get("/api/v1/sources/registry?page_size=0", headers=HEADERS).status_code == 422
    client.patch(path, json={"enabled": False}, headers=HEADERS)
    assert client.post(path + "/sync", headers=HEADERS).status_code == 409
    restricted = {
        "company_name": "Example",
        "career_url": "https://www.linkedin.com/jobs",
        "provider": "career_page",
    }
    assert client.post("/api/v1/sources", json=restricted, headers=HEADERS).status_code == 422


def test_scheduler_and_task_redelivery_are_idempotent(client, monkeypatch):
    from app.workers import tasks

    calls = []
    monkeypatch.setattr(tasks, "publish", lambda run: calls.append(run))
    with Session(get_engine()) as session:
        source_id = make_source(session).id
    tasks.schedule_sources.run()
    tasks.schedule_sources.run()
    assert len(set(calls)) == 1

    async def execute_twice():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"jobs": [FIXTURE["ashby"]]})
            )
        ) as http:
            await ingest(calls[0], http_client=http)
            await ingest(calls[0], http_client=http)

    asyncio.run(execute_twice())
    with Session(get_engine()) as session:
        assert session.get(IngestionSource, source_id).health == "healthy"
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        run = session.get(IngestionRun, calls[0])
        assert run.fetched == 1
    tasks.schedule_sources.run()
    assert len(calls) == 2  # Future next_fetch_at prevents another run.


def test_explicit_freshness_and_partial_fetch_preserve_jobs(client):
    with Session(get_engine()) as session:
        source_id = make_source(session).id
    pipeline(source_id, lambda r: httpx.Response(200, json={"jobs": [FIXTURE["ashby"]]}))
    pipeline(
        source_id,
        lambda r: httpx.Response(200, json={"jobs": [FIXTURE["ashby"], {"isListed": True}]}),
    )
    with Session(get_engine()) as session:
        row = session.scalar(select(Job))
        assert row.status == "active"
        assert session.get(IngestionSource, source_id).health == "degraded"
        occurrence = session.scalar(select(JobSource))
        row.valid_through = now() - timedelta(days=1)
        occurrence.metadata_json = {"valid_through": row.valid_through.isoformat()}
        session.commit()
        expire_jobs(session)
        session.commit()
        assert row.status == "closed"


def test_jsonld_crawl_sitemap_robots_and_remote_restrictions():
    record = {
        "@type": "JobPosting",
        "title": "Junior Developer",
        "description": "Python",
        "url": "https://example.com/jobs/1",
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {"@type": "Country", "name": "India"},
    }
    markup = '<script type="application/ld+json">' + json.dumps(record) + "</script>"
    config = SourceConfig(
        provider="career_page",
        board_id="example",
        company="Example",
        career_url="https://example.com/careers",
        configuration={"sitemap": True},
    )
    job = jsonld(markup, "https://example.com/jobs/1", config)[0]
    assert job.location.india_eligible is True and job.posted_at is None

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/sitemap.xml":
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                text="<urlset><url><loc>https://example.com/jobs/1</loc></url></urlset>",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=markup if request.url.path.endswith("/1") else "<h1>Careers</h1>",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = Generic(fetcher=PageFetcher(http)).crawl(config)
    assert len(result.jobs) == 1 and not result.errors

    def denied(request):
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="User-agent: *\nDisallow: /"
        )

    with httpx.Client(transport=httpx.MockTransport(denied)) as http:
        blocked = Generic(fetcher=PageFetcher(http)).crawl(config)
    assert not blocked.jobs and blocked.errors


def test_optional_integrations_disabled_by_default(client):
    from app.ingestion.connectors.generic import Browser
    from app.ingestion.connectors.jobspy_optional import JobSpy

    assert not get_settings().jobspy_enabled and not get_settings().browser_enabled
    for connector, code in [(Browser(), "BROWSER_DISABLED"), (JobSpy(), "JOBSPY_DISABLED")]:
        with pytest.raises(FetchFailure, match=code):
            asyncio.run(connector.fetch_jobs(source_config("career_page")))


def test_snapshot_absence_requires_two_complete_successes_and_reopens(client):
    with Session(get_engine()) as session:
        source_id = make_source(session).id

    def present(r):
        return httpx.Response(200, json={"jobs": [FIXTURE["ashby"]]})

    def empty(r):
        return httpx.Response(200, json={"jobs": []})

    pipeline(source_id, present)
    pipeline(source_id, empty)
    pipeline(source_id, lambda r: httpx.Response(403))
    with Session(get_engine()) as session:
        assert session.scalar(select(Job)).status == "active"
        assert session.scalar(select(JobSource)).metadata_json["consecutive_absences"] == 1
    pipeline(source_id, empty)
    with Session(get_engine()) as session:
        assert session.scalar(select(Job)).status == "closed"
    pipeline(source_id, present)
    with Session(get_engine()) as session:
        assert session.scalar(select(Job)).status == "active"
        assert session.get(IngestionSource, source_id).sync_state["listing"]["data"]["jobs"]


def test_profiles_rank_independently_and_recompute_only_when_dirty(client):
    from app.ingestion.matching import refresh_profiles
    from app.models import JobMatch, MatchingProfile

    with Session(get_engine()) as session:
        source_id = make_source(session).id
    pipeline(source_id, lambda r: httpx.Response(200, json={"jobs": [FIXTURE["ashby"]]}))
    profiles = []
    for user_key, skills in [("alice", ["Python", "SQL"]), ("bob", ["Rust"])]:
        response = client.post(
            "/api/v1/matching/profiles",
            headers=HEADERS,
            json={"user_key": user_key, "skills": skills},
        )
        assert response.status_code == 202 and response.json()["status"] == "PENDING"
        profiles.append(response.json()["id"])
    with Session(get_engine()) as session:
        assert refresh_profiles(session) == 2
        assert refresh_profiles(session) == 0
        assert session.scalar(select(func.count()).select_from(JobMatch)) == 2
    alice = client.get(
        f"/api/v1/jobs?match_profile={profiles[0]}&sort=match", headers=HEADERS
    ).json()
    bob = client.get(f"/api/v1/jobs?match_profile={profiles[1]}&sort=match", headers=HEADERS).json()
    assert alice["items"][0]["match_score"] > bob["items"][0]["match_score"]
    assert any(r.startswith("missing_skill:") for r in bob["items"][0]["match_reasons"])
    assert client.get("/api/v1/jobs?sort=match", headers=HEADERS).status_code == 422
    # Unchanged observations do not enqueue matching again.
    pipeline(source_id, lambda r: httpx.Response(200, json={"jobs": [FIXTURE["ashby"]]}))
    with Session(get_engine()) as session:
        assert not session.scalar(select(MatchingProfile.needs_refresh).limit(1))
    pipeline(
        source_id,
        lambda r: httpx.Response(
            200,
            json={"jobs": [{**FIXTURE["ashby"], "descriptionPlain": "Python, SQL and TypeScript"}]},
        ),
    )
    with Session(get_engine()) as session:
        assert session.scalar(select(MatchingProfile.needs_refresh).limit(1))


def test_application_url_and_employer_requisition_deduplicate(client):
    from app.ingestion.connectors.ats import base

    with Session(get_engine()) as session:
        source = make_source(session, website="https://example.com/")
        second = make_source(
            session,
            "career_page",
            "careers",
            website="https://example.com/",
            career_url="https://example.com/careers",
        )
        item = base(
            source_config("ashby"),
            {},
            external_id="one",
            title="Developer",
            url="https://example.com/job/one",
            apply="https://example.com/apply?id=one&utm_source=x",
            requisition="req-one",
        )
        store_job(session, source, item)
        same_url = item.model_copy(
            update={
                "source": "career_page",
                "external_id": "two",
                "job_url": "https://example.com/careers/two",
                "apply_url": "https://example.com/apply?id=one&utm_source=y",
            }
        )
        assert store_job(session, second, same_url)[2]
        same_req = item.model_copy(
            update={
                "source": "career_page",
                "external_id": "three",
                "job_url": "https://example.com/careers/three",
                "apply_url": "https://example.com/apply?id=three",
            }
        )
        assert store_job(session, second, same_req)[2]
        different = item.model_copy(
            update={
                "external_id": "four",
                "requisition_id": "req-four",
                "job_url": "https://example.com/job/four",
                "apply_url": "https://example.com/apply?id=four",
            }
        )
        assert store_job(session, source, different)[0]
        session.commit()
        assert session.scalar(select(func.count()).select_from(Job)) == 2
        assert session.scalar(select(func.count()).select_from(JobSource)) == 4


def test_expired_worker_lease_is_recovered(client):
    with Session(get_engine()) as session:
        source = make_source(session)
        old = queue_run(session, source.id)
        old_id = old.id
        source.lease_expires_at = now() - timedelta(minutes=1)
        session.commit()
        replacement = queue_run(session, source.id)
        assert replacement.id != old_id
        assert session.get(IngestionRun, old_id).status == "INTERRUPTED"
        assert replacement.status == "QUEUED"


def test_canonical_url_preserves_identifiers():
    from app.normalization import canonical_url

    assert (
        canonical_url("https://example.com/job?gh_jid=123&utm_campaign=x&jobId=abc#apply")
        == "https://example.com/job?gh_jid=123&jobId=abc"
    )
    assert location("Remote - Worldwide", "remote").globally_remote is True
    assert location("Remote - Global excluding India", "remote").india_eligible is None


def test_tavily_only_suggests_unverified_sources(client, monkeypatch):
    from app.ingestion.discovery.company_finder import discover

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    get_settings.cache_clear()

    async def run():
        def handler(request):
            assert request.url.host == "api.tavily.com"
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "https://jobs.ashbyhq.com/example"},
                        {"url": "https://example.com/news"},
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await discover("software companies India", http)

    suggestions = asyncio.run(run())
    assert len(suggestions) == 1 and suggestions[0]["verified"] is False
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(IngestionSource)) == 0


def test_feed_and_configured_html_extraction():
    from app.ingestion.connectors.generic import html_jobs

    config = SourceConfig(
        provider="career_page",
        board_id="example",
        company="Example",
        career_url="https://example.com/jobs",
        configuration={
            "html": {
                "item": ".posting",
                "title": "h2",
                "description": ".body",
                "apply": ".apply",
                "url": "h2 a",
                "location": ".city",
            }
        },
    )
    markup = (
        '<div class="posting"><h2><a href="/jobs/1">Backend Developer</a></h2>'
        '<div class="body">Python</div><span class="city">Bangalore</span>'
        '<a class="apply" href="/apply/1">Apply</a></div>'
    )
    jobs = html_jobs(markup, config.career_url, config)
    assert len(jobs) == 1 and jobs[0].location.city == "Bengaluru"
    assert jobs[0].apply_url == "https://example.com/apply/1"
    assert html_jobs("<h1>Careers</h1>", config.career_url, source_config("career_page")) == []


def test_concurrent_source_reservations_share_one_run(client):
    from concurrent.futures import ThreadPoolExecutor

    with Session(get_engine()) as session:
        source_id = make_source(session).id

    def reserve(_):
        with Session(get_engine()) as session:
            return queue_run(session, source_id).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(reserve, range(4)))
    assert len(set(ids)) == 1


def test_concurrent_cross_source_identity_creates_one_canonical(client):
    from concurrent.futures import ThreadPoolExecutor

    from app.ingestion.connectors.ats import base

    with Session(get_engine()) as session:
        first = make_source(session)
        second = make_source(
            session, "career_page", "careers", career_url="https://example.com/jobs"
        )
        ids = [first.id, second.id]

    def store(source_id):
        with Session(get_engine()) as session:
            source = session.get(IngestionSource, source_id)
            item = base(
                source_config(source.provider),
                {},
                external_id="ashby-1",
                title="Software Engineer",
                url="https://jobs.ashbyhq.com/example/ashby-1",
            )
            store_job(session, source, item)
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(store, ids))
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(JobSource)) == 2


def test_feed_links_are_followed_to_structured_details():
    record = {
        "@type": "JobPosting",
        "title": "Graduate Developer",
        "description": "Python",
        "url": "https://example.com/jobs/1",
    }
    config = SourceConfig(
        provider="feed", board_id="feed", company="Example", career_url="https://example.com/feed"
    )

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/feed":
            return httpx.Response(
                200,
                headers={"content-type": "application/atom+xml"},
                text='<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://example.com/jobs/1"/></entry></feed>',
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<script type="application/ld+json">' + json.dumps(record) + "</script>",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = Generic(fetcher=PageFetcher(http)).crawl(config)
    assert len(result.jobs) == 1 and result.jobs[0].title == "Graduate Developer"


def test_celery_scheduler_dispatches_to_real_embedded_worker(client, monkeypatch):
    import time

    from celery.beat import ScheduleEntry, Scheduler
    from celery.contrib.testing.worker import start_worker

    from app.ingestion.connectors.ats import base
    from app.ingestion.registry import CONNECTORS
    from app.ingestion.schemas import FetchResult
    from app.workers.celery_app import celery

    class StaticConnector:
        async def fetch_jobs(self, configuration, cursor=None):
            return FetchResult(
                jobs=[
                    base(
                        configuration,
                        {},
                        external_id="worker-1",
                        title="Software Engineer",
                        url="https://jobs.ashbyhq.com/example/worker-1",
                    )
                ],
                complete_snapshot=True,
            )

    monkeypatch.setitem(CONNECTORS, "ashby", lambda _: StaticConnector())
    monkeypatch.setitem(celery.conf, "broker_url", "memory://")
    monkeypatch.setitem(celery.conf, "broker_connection_retry_on_startup", False)
    with Session(get_engine()) as session:
        source_id = make_source(session).id
    # Exercise Celery scheduling, serialization, broker delivery, task dispatch,
    # actual worker execution and PostgreSQL persistence without an external service.
    with start_worker(celery, perform_ping_check=False, queues=["ingestion"], shutdown_timeout=10):
        scheduler = Scheduler(app=celery, lazy=True)
        scheduler.apply_async(
            ScheduleEntry(name="due-test", task="ingestion.schedule", schedule=60.0, app=celery),
            advance=False,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with Session(get_engine()) as session:
                source = session.get(IngestionSource, source_id)
                if source.health == "healthy":
                    assert session.scalar(select(func.count()).select_from(Job)) == 1
                    break
            time.sleep(0.05)
        else:
            pytest.fail("Embedded Celery worker did not finish the scheduled ingestion")
