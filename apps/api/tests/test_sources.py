import json
import socket

import httpx
import pytest

from app.config import get_settings
from app.normalization import canonical_url, text
from app.sources import SourceError, feed_job, fetch_feed, fetch_search
from app.web_pages import PageBlocked, PageFetcher, PublicTransport, extract_jobs


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/job",
        "https://127.0.0.1/job",
        "https://localhost/job",
        "https://10.0.0.1/job",
        "https://169.254.169.254/latest",
        "https://[::1]/job",
        "https://person:secret@example.com/job",
        "https://example.com:8080/job",
        "javascript:alert(1)",
        "https://example.com\n/job",
    ],
)
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_normalization_keeps_job_identifiers_and_uses_html_parser():
    assert (
        canonical_url("https://EXAMPLE.com/job?utm_source=test&job_id=2&lang=en#apply")
        == "https://example.com/job?job_id=2&lang=en"
    )
    assert canonical_url("https://example.com/job?job_id=3") != canonical_url(
        "https://example.com/job?job_id=2"
    )
    assert (
        text("&lt;p&gt;Python &amp;amp; SQL&lt;/p&gt;<script>secret()</script>") == "Python & SQL"
    )


def test_feed_normalization_preserves_unknowns():
    row = feed_job(
        "arbeitnow",
        {
            "url": "https://example.com/job?utm_source=public_api",
            "slug": "job",
            "title": "Engineer",
            "description": "<p>Build software</p>",
            "remote": False,
            "job_types": [],
            "tags": [],
            "created_at": "bad",
        },
    )
    assert row.company is None and row.location is None and row.work_mode == "UNKNOWN"
    assert row.canonical_url == "https://example.com/job"
    assert row.source_url.endswith("?utm_source=public_api")
    assert row.salary_min is None and row.published_at is None
    row = feed_job(
        "jobicy",
        {
            "url": "https://jobicy.com/jobs/test",
            "id": 1,
            "jobTitle": "Developer",
            "jobLevel": "Any",
            "jobType": ["Full-Time"],
            "jobIndustry": ["Engineering"],
            "jobGeo": "Anywhere",
        },
    )
    assert row.experience_level is None and row.employment_type == "Full-time"
    assert row.work_mode == "REMOTE" and row.tags == ["engineering"]


def test_feed_pagination_uses_fixed_hosts_and_reports_truncation():
    calls = []

    def response(request):
        calls.append(str(request.url))
        page = request.url.params["page"]
        return httpx.Response(
            200,
            json={
                "data": [{"url": f"https://example.com/{page}", "slug": page, "title": "Engineer"}],
                "links": {"next": "http://127.0.0.1/private"},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = fetch_feed("arbeitnow", client)
    assert len(calls) == 3 and result.partial and len(result.jobs) == 3
    assert all(url.startswith("https://www.arbeitnow.com/") for url in calls)


def test_rate_limits_and_redirects_never_leak_search_credentials(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "private-test-key")
    get_settings.cache_clear()
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/"})

    with httpx.Client(transport=httpx.MockTransport(response)) as http:
        with pytest.raises(SourceError):
            fetch_search("engineer jobs", http)
    assert len(calls) == 1 and calls[0].url.host == "api.tavily.com"
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    headers={"Retry-After": "120"},
                )
            )
        ) as http,
        pytest.raises(SourceError, match="RATE_LIMITED") as error,
    ):
        fetch_feed("remotive", http)
    assert error.value.retry_after == 120


POSTING = {
    "@type": "JobPosting",
    "title": "Backend Engineer",
    "description": "<p>Build Python APIs.</p>",
    "hiringOrganization": {"name": "Example"},
    "jobLocationType": "TELECOMMUTE",
    "applicantLocationRequirements": {"@type": "Country", "name": "India"},
    "datePosted": "2026-10-30",
    "employmentType": "FULL_TIME",
    "baseSalary": {
        "currency": "USD",
        "value": {"minValue": 90000, "maxValue": 120000, "unitText": "YEAR"},
    },
}


def test_structured_job_extraction_uses_only_published_fields():
    markup = '<script type="application/ld+json">' + json.dumps({"@graph": [POSTING]}) + "</script>"
    jobs = extract_jobs(markup, "https://example.com/job/1")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "Example" and job.location == "India"
    assert job.salary_min == 90000 and job.salary_period == "yearly"
    assert job.work_mode == "REMOTE" and job.enrichment_status == "EXTRACTED"
    assert job.description == "Build Python APIs."
    assert (
        extract_jobs(
            '<script type="application/ld+json">{"@type":"Article"}</script>',
            "https://example.com/",
        )
        == []
    )


def test_robots_and_redirect_target_checks():
    calls = []

    def denied(request):
        calls.append(request.url.path)
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="User-agent: *\nDisallow: /jobs"
        )

    with httpx.Client(transport=httpx.MockTransport(denied)) as http, pytest.raises(PageBlocked):
        PageFetcher(http).fetch("https://example.com/jobs/1")
    assert calls == ["/robots.txt"]

    def redirected(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    with httpx.Client(transport=httpx.MockTransport(redirected)) as http, pytest.raises(ValueError):
        PageFetcher(http).fetch("https://example.com/jobs/1")


def test_public_transport_blocks_private_dns_and_pins_public_ip(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
        ],
    )
    transport = PublicTransport()
    with pytest.raises(PageBlocked, match="PRIVATE_DESTINATION"):
        transport.handle_request(httpx.Request("GET", "https://public.example/jobs"))
    transport.close()
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    transport = PublicTransport()
    captured = []
    transport.transports["public.example"] = httpx.MockTransport(
        lambda request: captured.append(request) or httpx.Response(200)
    )
    transport.handle_request(httpx.Request("GET", "https://public.example/jobs"))
    request = captured[0]
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "public.example"
    assert request.extensions["sni_hostname"] == "public.example"
    transport.close()


def test_search_candidates_are_not_invented_jobs(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setenv("ENRICH_WEB_RESULTS", "true")
    get_settings.cache_clear()

    def response(request):
        assert request.headers["authorization"] == "Bearer fake-key"
        payload = json.loads(request.content)
        assert payload["include_answer"] is False and payload["auto_parameters"] is False
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "All software jobs",
                        "url": "https://example.com/jobs",
                        "content": "Search listings",
                    },
                ]
            },
        )

    class Pages:
        def fetch(self, url):
            return []

    with httpx.Client(transport=httpx.MockTransport(response)) as http:
        result = fetch_search("software jobs", http, Pages())
    assert result.jobs[0].listing_type == "SEARCH_RESULT"
    assert result.jobs[0].company is None and result.jobs[0].location is None


def test_later_page_failure_preserves_earlier_postings():
    def response(request):
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"title": "Engineer", "slug": "1", "url": "https://example.com/job/1"}
                    ],
                    "links": {"next": "page-2"},
                },
            )
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(response)) as http:
        result = fetch_feed("arbeitnow", http)
    assert len(result.jobs) == 1 and result.partial
    assert result.error_code == "SOURCE_UNAVAILABLE"


def test_pinned_tls_pools_are_isolated_by_hostname(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    pools = []

    def factory(**kwargs):
        pool = httpx.MockTransport(lambda request: httpx.Response(200))
        pools.append(pool)
        return pool

    monkeypatch.setattr("app.web_pages.httpx.HTTPTransport", factory)
    transport = PublicTransport()
    for host in ["one.example", "two.example", "one.example"]:
        transport.handle_request(httpx.Request("GET", f"https://{host}/jobs"))
    assert len(pools) == 2
    assert transport.transports["one.example"] is not transport.transports["two.example"]
    transport.close()


def test_configuration_errors_do_not_print_local_keys(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.delenv("API_TOKEN")
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, tavily_api_key="private-key-that-must-not-be-logged")
    assert "private-key-that-must-not-be-logged" not in str(error.value)
