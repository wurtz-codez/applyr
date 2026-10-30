import time
from dataclasses import dataclass, field

import httpx

from app.config import get_settings
from app.normalization import canonical_url, date, employment, tags, text
from app.schemas import JobData
from app.web_pages import PageBlocked, PageFetcher

PROVIDERS = {
    "arbeitnow": {"name": "Arbeitnow", "url": "https://www.arbeitnow.com", "interval": 3600},
    "remotive": {"name": "Remotive", "url": "https://remotive.com", "interval": 21600},
    "jobicy": {"name": "Jobicy", "url": "https://jobicy.com", "interval": 3600},
    "tavily": {"name": "Tavily web search", "url": "https://tavily.com", "interval": 1800},
}


class SourceError(Exception):
    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.retry_after = retry_after


@dataclass
class Batch:
    jobs: list[JobData] = field(default_factory=list)
    invalid: int = 0
    partial: bool = False
    enriched: int = 0
    error_code: str | None = None
    retry_after: int | None = None


def client():
    return httpx.Client(
        timeout=20, follow_redirects=False, headers={"User-Agent": "ApplyrJobCollector/0.1"}
    )


def request_json(http, method, url, **kwargs):
    try:
        deadline = time.monotonic() + 30
        with http.stream(method, url, **kwargs) as response:
            if response.status_code == 429:
                try:
                    retry = min(86400, max(60, int(response.headers.get("retry-after", "3600"))))
                except ValueError:
                    retry = 3600
                raise SourceError("RATE_LIMITED", retry)
            if response.status_code in {401, 403}:
                raise SourceError("ACCESS_DENIED")
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 15 * 1024 * 1024 or time.monotonic() > deadline:
                    raise SourceError("RESPONSE_LIMIT")
        import json

        data = json.loads(content)
        if not isinstance(data, dict):
            raise SourceError("INVALID_RESPONSE")
        return data
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise SourceError("CONNECTION_FAILED", 60) from None
    except (httpx.HTTPError, ValueError, TypeError):
        raise SourceError("SOURCE_UNAVAILABLE") from None


def feed_job(provider, raw):
    if not isinstance(raw, dict):
        raise ValueError("Invalid listing")
    if provider == "arbeitnow":
        url = canonical_url(raw["url"])
        kinds = raw.get("job_types", [])
        level = next(
            (
                value
                for value in kinds
                if isinstance(value, str)
                and value.casefold() in {"junior", "mid", "senior", "experienced", "entry"}
            ),
            None,
        )
        return JobData(
            canonical_url=url,
            source_url=raw["url"].strip(),
            external_id=str(raw["slug"])[:200],
            title=text(raw.get("title"), 500),
            company=text(raw.get("company_name"), 300) or None,
            description=text(raw.get("description")),
            location=text(raw.get("location"), 500) or None,
            work_mode="REMOTE" if raw.get("remote") is True else "UNKNOWN",
            employment_type=employment(kinds),
            experience_level=level,
            tags=tags(raw.get("tags")),
            published_at=date(raw.get("created_at")),
        )
    if provider == "remotive":
        url = canonical_url(raw["url"])
        return JobData(
            canonical_url=url,
            source_url=raw["url"].strip(),
            external_id=str(raw["id"])[:200],
            title=text(raw.get("title"), 500),
            company=text(raw.get("company_name"), 300) or None,
            description=text(raw.get("description")),
            location=text(raw.get("candidate_required_location"), 500) or None,
            work_mode="REMOTE",
            employment_type=employment(raw.get("job_type")),
            tags=tags(raw.get("tags")),
            published_at=date(raw.get("publication_date")),
            salary_text=text(raw.get("salary"), 500) or None,
        )
    url = canonical_url(raw["url"])
    currency = raw.get("salaryCurrency")
    currency = currency.upper() if isinstance(currency, str) and len(currency) == 3 else None
    minimum, maximum = raw.get("salaryMin"), raw.get("salaryMax")
    level = text(raw.get("jobLevel"), 80)
    return JobData(
        canonical_url=url,
        source_url=raw["url"].strip(),
        external_id=str(raw["id"])[:200],
        title=text(raw.get("jobTitle"), 500),
        company=text(raw.get("companyName"), 300) or None,
        description=text(raw.get("jobDescription") or raw.get("jobExcerpt")),
        location=text(raw.get("jobGeo"), 500) or None,
        work_mode="REMOTE",
        employment_type=employment(raw.get("jobType")),
        experience_level=level if level.casefold() not in {"", "any"} else None,
        tags=tags(raw.get("jobIndustry")),
        published_at=date(raw.get("pubDate")),
        salary_min=minimum
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
        else None,
        salary_max=maximum
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool)
        else None,
        salary_currency=currency,
        salary_period=text(raw.get("salaryPeriod"), 20) or None,
    )


def fetch_feed(provider, http):
    batch = Batch()
    cursor = None
    for page in range(1, 4):
        try:
            if provider == "arbeitnow":
                data = request_json(
                    http,
                    "GET",
                    "https://www.arbeitnow.com/api/job-board-api",
                    params={"page": page},
                )
                records = data.get("data")
            elif provider == "remotive":
                data = request_json(http, "GET", "https://remotive.com/api/remote-jobs")
                records = data.get("jobs")
            else:
                params = {"count": 200}
                if cursor:
                    params["cursor"] = cursor
                data = request_json(http, "GET", "https://jobicy.com/api/jobs", params=params)
                records = data.get("jobs")
            if not isinstance(records, list) or len(records) > 5000:
                raise SourceError("INVALID_RESPONSE")
            for raw in records:
                try:
                    batch.jobs.append(feed_job(provider, raw))
                except (ValueError, TypeError, KeyError, AttributeError):
                    batch.invalid += 1
            if provider == "remotive":
                break
            if provider == "arbeitnow":
                links = data.get("links") or {}
                if not isinstance(links, dict):
                    raise SourceError("INVALID_PAGINATION")
                more = bool(links.get("next"))
            else:
                cursor = data.get("nextCursor")
                if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 2000):
                    raise SourceError("INVALID_PAGINATION")
                more = bool(cursor)
                if data.get("hasMore") and not more:
                    raise SourceError("INVALID_PAGINATION")
            if not more:
                break
            batch.partial = page == 3
        except SourceError as error:
            if not batch.jobs:
                raise
            batch.partial, batch.error_code = True, str(error)
            batch.retry_after = error.retry_after
            break
    return batch


def fetch_search(query, http, pages=None):
    settings = get_settings()
    if not settings.tavily_api_key:
        raise SourceError("NOT_CONFIGURED")
    data = request_json(
        http,
        "POST",
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {settings.tavily_api_key.get_secret_value()}",
        },
        json={
            "query": query,
            "topic": "general",
            "search_depth": "basic",
            "max_results": settings.search_results_per_query,
            "include_answer": False,
            "include_raw_content": False,
            "auto_parameters": False,
        },
    )
    records = data.get("results")
    if not isinstance(records, list):
        raise SourceError("INVALID_RESPONSE")
    batch = Batch()
    owns_pages = pages is None
    pages = pages or PageFetcher()
    try:
        for index, raw in enumerate(records[: settings.search_results_per_query]):
            try:
                url = canonical_url(raw["url"])
                result = JobData(
                    canonical_url=url,
                    source_url=raw["url"].strip(),
                    title=text(raw.get("title"), 500),
                    description=text(raw.get("content")),
                    listing_type="SEARCH_RESULT",
                    enrichment_status="DISABLED",
                    published_at=None,
                )
                if settings.enrich_web_results and index < 10:
                    try:
                        jobs = pages.fetch(url)
                        if jobs:
                            batch.jobs.extend(jobs)
                            batch.enriched += len(jobs)
                            continue
                        result.enrichment_status = "NO_STRUCTURED_JOB"
                    except (PageBlocked, httpx.HTTPError, OSError, ValueError):
                        result.enrichment_status = "PAGE_UNAVAILABLE_OR_BLOCKED"
                batch.jobs.append(result)
            except (ValueError, TypeError, KeyError, AttributeError):
                batch.invalid += 1
    finally:
        if owns_pages:
            pages.close()
    return batch


def fetch(provider, query):
    with client() as http:
        return fetch_search(query, http) if provider == "tavily" else fetch_feed(provider, http)
