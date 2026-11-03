"""Ingestion v2 acceptance tests: real PostgreSQL, bounded mocked public endpoints."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.discovery import store_jobs
from app.ingestion.backfill import backfill
from app.ingestion.bootstrap import SEED, bootstrap
from app.ingestion.connectors.ats import Greenhouse
from app.ingestion.connectors.public_feeds import PublicFeed
from app.ingestion.discovery.automatic import discover_sources
from app.ingestion.eligibility import VERSION, evaluate
from app.ingestion.engine import ingest, queue_run, store_job
from app.ingestion.http import HTTP
from app.ingestion.maintenance import run_maintenance
from app.ingestion.normalizer import enrich, location
from app.ingestion.schemas import NormalizedJob, SourceConfig, SourceCreate
from app.ingestion.service import register_source
from app.models import (
    IngestionRun,
    IngestionSource,
    Job,
    JobSource,
    MaintenanceState,
    SourceState,
    now,
)
from app.schemas import JobData

AUTH = {"Authorization": "Bearer test-token-" + "a" * 48}


def normalized(label=None, mode=None, description="", **kwargs):
    return NormalizedJob(
        source="ashby",
        external_id="1",
        company="Employer",
        title="Software Engineer",
        location=location(label, mode, **kwargs),
        description=description,
        job_url="https://jobs.ashbyhq.com/employer/1",
    )


@pytest.mark.parametrize(
    "label,mode,description,expected",
    [
        ("Bengaluru, India", "onsite", "", "CONFIRMED"),
        ("Remote — India", "remote", "", "CONFIRMED"),
        ("Remote — US only", "remote", "", "NOT_ELIGIBLE"),
        ("Remote — Worldwide", "remote", "", "CONFIRMED"),
        ("Remote", "remote", "", "UNCERTAIN"),
        ("London", "hybrid", "", "NOT_ELIGIBLE"),
        ("APAC", "remote", "", "UNCERTAIN"),
        ("Remote", "remote", "Our company has offices in India", "UNCERTAIN"),
        ("Remote", "remote", "Candidates based in India are welcome", "CONFIRMED"),
        ("Worldwide except India", "remote", "", "NOT_ELIGIBLE"),
        ("Worldwide", "remote", "Must overlap UTC-8 time zone", "UNCERTAIN"),
        ("Indiana", "onsite", "", "UNCERTAIN"),
    ],
)
def test_geographic_evidence(label, mode, description, expected):
    result = evaluate(normalized(label, mode, description))
    assert result["status"] == expected
    assert result["reason"] and result["method"] == "deterministic"


def test_structured_restrictions_and_country_only_office():
    assert evaluate(normalized("Remote", "remote", eligible=["US"]))["status"] == "NOT_ELIGIBLE"
    assert evaluate(normalized("Remote", "remote", eligible=["India"]))["status"] == "CONFIRMED"
    assert evaluate(normalized("Remote", "remote", country="IN"))["status"] == "UNCERTAIN"
    multi = normalized("London", "onsite")
    multi.additional_locations = [location("Pune", "hybrid")]
    assert evaluate(multi)["status"] == "CONFIRMED"


def seed_payload(board="employer", **kwargs):
    return SourceCreate(
        company_name="Employer",
        provider="ashby",
        board_id=board,
        career_url=f"https://jobs.ashbyhq.com/{board}",
        access_policy="public_api",
        **kwargs,
    )


def test_bootstrap_idempotency_three_way_updates_and_user_sources(client):
    with Session(get_engine()) as session:
        assert bootstrap(session, [seed_payload(configuration={"filters": {"country": "IN"}})]) == 1
        source = session.scalar(select(IngestionSource))
        source_id = source.id
        assert source.active_run_id is not None
        assert bootstrap(session, [seed_payload(configuration={"filters": {"country": "IN"}})]) == 0
        source.enabled = False
        source.configuration = {"filters": {"country": "CA"}, "retain_raw": True}
        session.commit()
        updated = seed_payload(
            configuration={"filters": {"country": "US"}, "new_option": True},
            fetch_interval_seconds=43200,
        )
        bootstrap(session, [updated])
        session.refresh(source)
        assert not source.enabled and source.fetch_interval_seconds == 43200
        assert source.configuration == {
            "filters": {"country": "CA"},
            "retain_raw": True,
            "new_option": True,
        }
        assert "enabled" in source.local_overrides
        manual = register_source(session, seed_payload("manual", fetch_interval_seconds=86400))
        bootstrap(session, [seed_payload("manual"), updated], force=True)
        session.refresh(manual)
        assert manual.fetch_interval_seconds == 86400 and manual.seed_defaults is None
        bootstrap(session, [], force=True)
        assert session.get(IngestionSource, source_id) is not None
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 1


def test_bootstrap_concurrent_startup(client):
    def start(_):
        with Session(get_engine()) as session:
            return bootstrap(session, [seed_payload()])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(start, range(8)))
    assert sum(results) == 1
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(IngestionSource)) == 1
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 1


def test_bundled_sources_have_validation_evidence_and_no_duplicates():
    rows = json.loads(SEED.read_text())
    assert len(rows) >= 40
    identities = {(r["ats_provider"], r["board_token"]) for r in rows}
    assert len(identities) == len(rows)
    for row in rows:
        assert row["verification"]["http_status"] == 200
        assert row["verification"]["india_jobs_observed"] > 0
        assert row["verification"]["evidence_location"]
        assert row["enabled"] is True


def test_scheduler_bootstraps_without_user_actions_and_recovers_lease(client, monkeypatch):
    from app.config import get_settings
    from app.workers import tasks

    settings = get_settings()
    monkeypatch.setattr(settings, "ingestion_bootstrap_enabled", True)
    calls = []
    monkeypatch.setattr(tasks, "publish", calls.append)
    tasks.schedule_sources.run()
    with Session(get_engine()) as session:
        source = session.scalar(select(IngestionSource).where(IngestionSource.provider == "jobicy"))
        old_id = source.active_run_id
        assert old_id in calls
        old = session.get(IngestionRun, old_id)
        old.status = "RUNNING"
        source.next_fetch_at = now() + timedelta(days=1)
        source.lease_expires_at = now() - timedelta(minutes=1)
        session.commit()
        source_id = source.id
    tasks.schedule_sources.run()
    with Session(get_engine()) as session:
        assert session.get(IngestionRun, old_id).status == "INTERRUPTED"
        assert session.get(IngestionSource, source_id).active_run_id != old_id


def test_backfill_is_bounded_versioned_and_excludes_search_pages(client):
    with Session(get_engine()) as session:
        for n, (label, mode) in enumerate(
            [("India", "ONSITE"), ("London", "HYBRID"), ("Remote", "REMOTE")]
        ):
            session.add(
                Job(
                    canonical_url=f"https://example.com/{n}",
                    title="Software Engineer",
                    company="Company",
                    description="0-2 years of experience with Python",
                    location=label,
                    work_mode=mode,
                    primary_source="jobicy",
                    content_hash="a" * 64,
                )
            )
        session.add(
            Job(
                canonical_url="https://example.com/search",
                title="Search page",
                listing_type="SEARCH_RESULT",
                primary_source="tavily",
                content_hash="b" * 64,
            )
        )
        session.commit()
        assert backfill(session, 2) == 2
        assert backfill(session, 2) == 1
        timestamps = {j.id: j.eligibility_evaluated_at for j in session.scalars(select(Job))}
        assert backfill(session) == 0
        rows = session.scalars(select(Job).where(Job.listing_type == "JOB_POSTING")).all()
        assert {r.india_status for r in rows} == {"CONFIRMED", "NOT_ELIGIBLE", "UNCERTAIN"}
        assert all(r.normalization_version == VERSION and r.experience_max == 2 for r in rows)
        assert all(r.eligibility_evaluated_at == timestamps[r.id] for r in rows)


def test_public_feed_cursor_pagination_metadata_and_restrictions():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            assert request.url.params["count"] == "100"
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 1,
                            "url": "https://jobicy.com/jobs/1",
                            "jobTitle": "Backend Developer",
                            "companyName": "Employer",
                            "jobGeo": "India",
                            "jobDescription": "Python, 0-2 years of experience",
                        }
                    ],
                    "nextCursor": "opaque" if len(calls) == 1 else None,
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            connector = PublicFeed(HTTP(client, interval=0))
            config = SourceConfig(provider="jobicy", board_id="public", company="Jobicy")
            first = await connector.fetch_jobs(config)
            await connector.fetch_jobs(config, first.next_cursor)
            assert calls[-1].url.params["cursor"] == "opaque"
            assert first.jobs[0].location.india_eligible is True
            assert first.jobs[0].experience.max_years == 2 and not first.complete_snapshot

    asyncio.run(run())


@pytest.mark.parametrize(
    "restrictions,zones,expected",
    [
        ([{"alpha2": "IN", "name": "India"}], [], True),
        ([{"alpha2": "US", "name": "United States"}], [], False),
        ([], [], True),
        ([], ["-8"], None),
        (None, [], None),
    ],
)
def test_himalayas_keyless_locations_and_original_application_links(restrictions, zones, expected):
    async def run():
        raw = {
            "guid": "https://himalayas.app/companies/employer/jobs/role",
            "title": "Software Engineer",
            "companyName": "Employer",
            "applicationLink": "https://himalayas.app/companies/employer/jobs/role",
            "locationRestrictions": restrictions,
            "timezoneRestrictions": zones,
            "description": "Python",
            "expiryDate": 1900000000,
        }

        def handler(request):
            assert "authorization" not in request.headers
            assert request.url.params["limit"] == "20"
            return httpx.Response(200, json={"jobs": [raw], "nextCursor": "cursor-token"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            batch = await PublicFeed(HTTP(client, interval=0)).fetch_jobs(
                SourceConfig(provider="himalayas", board_id="public", company="Himalayas")
            )
            assert batch.jobs[0].location.india_eligible is expected
            assert (
                batch.jobs[0].apply_url == raw["applicationLink"]
                and batch.next_cursor == "cursor-token"
            )
            assert batch.jobs[0].valid_through is not None

    asyncio.run(run())


def test_feed_adopts_legacy_occurrence_and_scheduler_respects_manual_cooldown(client):
    raw = JobData(
        canonical_url="https://jobicy.com/jobs/1",
        source_url="https://jobicy.com/jobs/1",
        external_id="1",
        title="Software Engineer",
        company="Employer",
        location="India",
        work_mode="REMOTE",
    )
    with Session(get_engine()) as session:
        store_jobs(session, "jobicy", [raw])
        old_job = session.scalar(select(Job))
        old_id = old_job.id
        source = register_source(
            session,
            SourceCreate(
                company_name="Jobicy",
                provider="jobicy",
                board_id="public",
                career_url="https://jobicy.com/api/jobs",
                access_policy="public_api",
            ),
        )
        job = enrich(
            NormalizedJob(
                source="jobicy",
                external_id="1",
                company="Employer",
                title="Software Engineer",
                job_url=raw.source_url,
                location=location("India", "remote"),
            )
        )
        assert store_job(session, source, job)[0] is False
        session.commit()
        assert session.scalar(select(func.count()).select_from(JobSource)) == 1
        assert session.scalar(select(JobSource)).source_id == source.id
        assert session.get(Job, old_id).india_status == "CONFIRMED"
        session.add(
            SourceState(key="jobicy", provider="jobicy", next_allowed_at=now() + timedelta(hours=2))
        )
        session.commit()
        run_id = queue_run(session, source.id).id

    async def run():
        def forbidden(_):
            raise AssertionError("Cooldown must prevent any HTTP request")

        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
            await ingest(run_id, http_client=client)

    asyncio.run(run())
    with Session(get_engine()) as session:
        assert session.get(IngestionRun, run_id).fetched == 0


def test_maintenance_shared_lease_due_state_and_failure_backoff(client):
    engine = get_engine()
    calls = []
    assert run_maintenance(engine, "test", 86400, lambda: calls.append(1) or 1)
    assert run_maintenance(engine, "test", 86400, lambda: calls.append(2)) is None
    assert calls == [1]

    def failed():
        raise RuntimeError("transient failure")

    run_maintenance(engine, "failed", 60, failed)
    with Session(engine) as session:
        row = session.get(MaintenanceState, "failed")
        assert row.failure_count == 1 and row.next_run_at > now() + timedelta(minutes=4)
        assert row.lease_token is None


def test_keyless_discovery_validates_observed_urls_and_is_idempotent(client):
    with Session(get_engine()) as session:
        session.add(
            Job(
                canonical_url="https://jobs.ashbyhq.com/new-employer/abc",
                apply_url="https://jobs.ashbyhq.com/new-employer/abc",
                original_job_url="https://jobs.ashbyhq.com/new-employer/abc",
                title="Developer",
                primary_source="arbeitnow",
                company="New Employer",
                content_hash="a" * 64,
            )
        )
        session.commit()

    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            assert request.url.host == "api.ashbyhq.com"
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": "abc",
                            "title": "Developer",
                            "jobUrl": "https://jobs.ashbyhq.com/new-employer/abc",
                            "isListed": True,
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await discover_sources(get_engine(), client) == 1
            assert await discover_sources(get_engine(), client) == 0
            assert len(calls) == 1

    asyncio.run(run())
    with Session(get_engine()) as session:
        assert session.scalar(select(IngestionSource)).active_run_id is not None


def test_india_first_ranking_and_explicit_status_filter(client):
    with Session(get_engine()) as session:
        source = register_source(session, seed_payload())
        for n, (label, title) in enumerate(
            [
                ("US only", "Software Engineer"),
                ("Remote", "Software Engineer"),
                ("India", "Software Engineer"),
                ("India", "Senior Software Engineer"),
            ]
        ):
            job = normalized(label, "remote")
            job.external_id, job.job_url, job.title = (
                str(n),
                f"https://jobs.ashbyhq.com/employer/{n}",
                title,
            )
            store_job(session, source, job)
        session.commit()
    response = client.get("/api/v1/jobs?sort=india", headers=AUTH).json()
    assert response["items"][0]["india_status"] == "CONFIRMED"
    assert response["items"][0]["title"] == "Software Engineer"
    confirmed = client.get("/api/v1/jobs?india_status=CONFIRMED", headers=AUTH).json()
    assert confirmed["total"] == 2
    assert confirmed["items"][0]["eligibility_evaluated_at"]
    assert confirmed["items"][0]["sources"][0]["last_verified_at"]


def test_greenhouse_bulk_content_uses_one_request():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            assert request.url.params["content"] == "true"
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 1,
                            "title": "Software Engineer",
                            "absolute_url": "https://boards.greenhouse.io/employer/jobs/1",
                            "content": "Python",
                            "location": {"name": "India"},
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await Greenhouse(HTTP(client, interval=0)).fetch_jobs(
                SourceConfig(provider="greenhouse", board_id="employer", company="Employer")
            )
            assert len(calls) == 1 and result.jobs[0].description == "Python"

    asyncio.run(run())


def test_himalayas_india_search_uses_page_numbers():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            assert request.url.path == "/jobs/api/search"
            assert request.url.params["country"] == "IN"
            assert "cursor" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "title": "Developer",
                            "companyName": "Employer",
                            "applicationLink": "https://himalayas.app/companies/employer/jobs/developer",
                            "guid": "https://himalayas.app/companies/employer/jobs/developer",
                            "locationRestrictions": ["India"],
                        }
                    ],
                    "totalCount": 21,
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            connector = PublicFeed(HTTP(client, interval=0))
            config = SourceConfig(
                provider="himalayas",
                company="Himalayas",
                board_id="public",
                configuration={"filters": {"country": "IN"}},
            )
            first = await connector.fetch_jobs(config)
            second = await connector.fetch_jobs(config, first.next_cursor)
            assert first.next_cursor == "2" and second.next_cursor is None
            assert calls[1].url.params["page"] == "2"
            assert first.jobs[0].location.india_eligible is True
            assert first.jobs[0].posted_at is None

    asyncio.run(run())


def test_rolling_feed_disappearance_is_not_closure_and_explicit_status_is(client):
    with Session(get_engine()) as session:
        source = register_source(
            session,
            SourceCreate(
                company_name="Jobicy",
                provider="jobicy",
                board_id="public",
                career_url="https://jobicy.com/api/jobs",
                access_policy="public_api",
            ),
        )
        job = normalized("India", "remote")
        job.source, job.external_id = "jobicy", "1234"
        store_job(session, source, job)
        session.commit()
        source_id = source.id
        run_id = queue_run(session, source_id).id

    async def run():
        def handler(request):
            if request.url.path.endswith("/status"):
                assert request.url.params["ids"] == "1234"
                return httpx.Response(200, json={"jobs": [{"id": 1234, "status": "closed"}]})
            return httpx.Response(200, json={"jobs": [], "nextCursor": None})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await ingest(run_id, http_client=http)

    asyncio.run(run())
    with Session(get_engine()) as session:
        assert session.scalar(select(Job)).status == "closed"
        assert session.scalar(select(JobSource)).last_verified_at is not None


def test_failed_board_validation_never_registers_a_source(client):
    with Session(get_engine()) as session:
        session.add(
            Job(
                canonical_url="https://jobs.lever.co/missing/123",
                apply_url="https://jobs.lever.co/missing/123",
                title="Developer",
                primary_source="arbeitnow",
                company="Missing Employer",
                content_hash="a" * 64,
            )
        )
        session.commit()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(404))
        ) as http:
            assert await discover_sources(get_engine(), http) == 0

    asyncio.run(run())
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(IngestionSource)) == 0


def test_himalayas_different_employers_with_identical_slugs_have_distinct_ids():
    async def run():
        jobs = [
            {
                "companyName": company,
                "title": "Software Engineer",
                "applicationLink": f"https://himalayas.app/companies/{company}/jobs/software-engineer",
                "guid": f"https://himalayas.app/companies/{company}/jobs/software-engineer",
                "locationRestrictions": ["India"],
            }
            for company in ["one", "two"]
        ]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"jobs": jobs}))
        ) as client:
            result = await PublicFeed(HTTP(client, interval=0)).fetch_jobs(
                SourceConfig(provider="himalayas", company="Himalayas", board_id="public")
            )
            assert len({job.external_id for job in result.jobs}) == 2

    asyncio.run(run())


def test_distinct_ats_openings_with_shared_application_form_stay_separate(client):
    with Session(get_engine()) as session:
        source = register_source(session, seed_payload())
        for external in ["first", "second"]:
            job = normalized("India", "onsite")
            job.external_id = external
            job.job_url = f"https://jobs.ashbyhq.com/employer/{external}"
            job.apply_url = "https://example.com/application-form"
            assert store_job(session, source, job)[0]
        session.commit()
        assert session.scalar(select(func.count()).select_from(Job)) == 2


def test_feed_country_metadata_is_not_confused_with_office_location():
    from app.ingestion.normalizer import feed_location

    assert feed_location("jobicy", "USA", "REMOTE").india_eligible is False
    assert feed_location("remotive", "USA, Canada", "REMOTE").india_eligible is False
    assert feed_location("jobicy", "APAC", "REMOTE").india_eligible is None
    assert feed_location("jobicy", "USA, APAC", "REMOTE").india_eligible is None
    assert feed_location("remotive", "Anywhere", "REMOTE").india_eligible is True
    assert feed_location("arbeitnow", "USA", "REMOTE").india_eligible is None


def test_expired_jobicy_cursor_recovers_after_persisted_cooldown(client):
    import hashlib

    with Session(get_engine()) as session:
        source = register_source(
            session,
            SourceCreate(
                company_name="Jobicy",
                provider="jobicy",
                board_id="public",
                career_url="https://jobicy.com/api/jobs",
                access_policy="public_api",
            ),
        )
        source.sync_state = {
            "resume_cursor": "expired",
            "traversal_filters": hashlib.sha256(b"{}").hexdigest(),
        }
        session.commit()
        source_id, run_id = source.id, queue_run(session, source.id).id

    async def run():
        def handler(request):
            assert request.url.params["cursor"] == "expired"
            return httpx.Response(400)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await ingest(run_id, http_client=client)

    asyncio.run(run())
    with Session(get_engine()) as session:
        source = session.get(IngestionSource, source_id)
        assert source.sync_state["resume_cursor"] is None
        assert source.next_fetch_at >= now() + timedelta(hours=5)
        assert session.get(IngestionRun, run_id).status == "FAILED"
