"""Keyless feeds on the shared connector pipeline; rolling feeds are not snapshots."""

import hashlib

from app.ingestion.http import FetchFailure
from app.ingestion.normalizer import enrich, feed_location, location
from app.ingestion.schemas import FetchError, FetchResult, NormalizedJob
from app.models import now
from app.normalization import canonical_url, date, text
from app.sources import feed_job

PUBLIC_FEEDS = {"arbeitnow", "jobicy", "remotive", "himalayas"}
FEED_INTERVALS = {"arbeitnow": 21600, "jobicy": 21600, "remotive": 43200, "himalayas": 86400}
ENDPOINTS = {
    "arbeitnow": "https://www.arbeitnow.com/api/job-board-api",
    "jobicy": "https://jobicy.com/api/jobs",
    "remotive": "https://remotive.com/api/remote-jobs",
    "himalayas": "https://himalayas.app/jobs/api",
}


def from_legacy(provider, item):
    return enrich(
        NormalizedJob(
            source=provider,
            external_id=item.external_id
            or "url:" + hashlib.sha256(item.canonical_url.encode()).hexdigest(),
            company=item.company or "Unknown employer",
            title=item.title,
            description=item.description,
            location=feed_location(provider, item.location, item.work_mode),
            job_url=item.source_url,
            apply_url=item.source_url,
            posted_at=item.published_at,
            skills=item.tags,
            employment_type=item.employment_type,
            experience_level=item.experience_level,
            salary_min=item.salary_min,
            salary_max=item.salary_max,
            salary_currency=item.salary_currency,
            salary_period=item.salary_period,
            salary_text=item.salary_text,
            source_fields=["location", "title", "description", "job_url"],
        )
    )


class PublicFeed:
    def __init__(self, http):
        self.http = http

    async def fetch_jobs(self, source, cursor=None):
        provider = source.provider
        params = dict(source.configuration.get("filters", {}))
        searching = provider == "himalayas" and bool(params)
        endpoint = ENDPOINTS[provider] + ("/search" if searching else "")
        if provider == "arbeitnow":
            params["page"] = int(cursor or 1)
        elif provider in {"jobicy", "himalayas"}:
            params["count" if provider == "jobicy" else "limit"] = (
                100 if provider == "jobicy" else 20
            )
            if searching:
                params["page"] = int(cursor or 1)
            elif cursor:
                params["cursor"] = cursor
        data, _, _ = await self.http.get(endpoint, params=params)
        records = (
            data.get("data" if provider == "arbeitnow" else "jobs")
            if isinstance(data, dict)
            else None
        )
        if not isinstance(records, list):
            raise FetchFailure("INVALID_PAYLOAD", False)
        result = FetchResult(complete_snapshot=provider == "remotive")
        for raw in records:
            try:
                if provider != "himalayas":
                    job = from_legacy(provider, feed_job(provider, raw))
                    job.raw = raw
                else:
                    restrictions = raw.get("locationRestrictions")
                    countries = []
                    for restriction in restrictions or []:
                        country = (
                            restriction.get("alpha2") or restriction.get("name")
                            if isinstance(restriction, dict)
                            else restriction
                        )
                        if isinstance(country, str):
                            countries.append(country)
                    url = raw["applicationLink"]
                    # Himalayas requires this source URL as the Apply destination.
                    job = NormalizedJob(
                        source=provider,
                        external_id=str(raw["id"])
                        if raw.get("id")
                        else "guid:"
                        + hashlib.sha256(
                            canonical_url(raw.get("guid") or url).encode()
                        ).hexdigest(),
                        company=raw["companyName"],
                        title=raw["title"],
                        description=text(raw.get("description") or raw.get("excerpt")),
                        job_url=url,
                        apply_url=url,
                        location=location(
                            ", ".join(countries) if countries else "Remote",
                            "remote",
                            eligible=countries or None,
                            # An empty country list plus timezone limits is NOT worldwide.
                            globally_remote=True
                            if restrictions == [] and not raw.get("timezoneRestrictions")
                            else None,
                        ),
                        derived={
                            "timezone_restrictions": raw.get("timezoneRestrictions") or [],
                            "source_updated_at": raw.get("pubDate"),
                        },
                        employment_type=raw.get("employmentType"),
                        # pubDate is the provider's update time, not an employer publication date.
                        posted_at=None,
                        valid_through=date(raw.get("expiryDate")),
                        raw=raw,
                        salary_min=raw.get("minSalary"),
                        salary_max=raw.get("maxSalary"),
                        salary_currency=raw.get("currency") or None,
                        source_fields=[
                            "title",
                            "locationRestrictions",
                            "timezoneRestrictions",
                            "applicationLink",
                        ],
                    )
                    job = enrich(job)
                result.jobs.append(job)
            except (ValueError, TypeError, KeyError, AttributeError):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
        if provider == "arbeitnow":
            links = data.get("links") or {}
            if not isinstance(links, dict):
                raise FetchFailure("INVALID_PAGINATION", False)
            if links.get("next"):
                result.next_cursor = str(int(cursor or 1) + 1)
        elif searching:
            # Official search endpoint uses page numbers, not browse cursors.
            total = data.get("totalCount")
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise FetchFailure("INVALID_PAGINATION_TOTAL", False)
            if records and int(cursor or 1) * 20 < total:
                result.next_cursor = str(int(cursor or 1) + 1)
        elif provider in {"jobicy", "himalayas"}:
            following = data.get("nextCursor")
            if following is not None and (
                not isinstance(following, str) or not 0 < len(following) <= 2000
            ):
                raise FetchFailure("INVALID_PAGINATION", False)
            if data.get("hasMore") and not following:
                raise FetchFailure("INVALID_PAGINATION", False)
            result.next_cursor = following
        if provider == "jobicy" and cursor is None:
            checked = date(source.state.get("last_status_check"))
            if source.configuration.get("verify_ids") and (
                checked is None or (now() - checked).total_seconds() >= 86400
            ):
                try:
                    statuses = []
                    for offset in range(0, len(source.configuration["verify_ids"]), 100):
                        ids = source.configuration["verify_ids"][offset : offset + 100]
                        payload, _, _ = await self.http.get(
                            "https://jobicy.com/api/jobs/status", params={"ids": ",".join(ids)}
                        )
                        if not isinstance(payload, dict) or not isinstance(
                            payload.get("jobs"), list
                        ):
                            raise FetchFailure("INVALID_STATUS_RESPONSE", False)
                        statuses.extend(payload["jobs"])
                    result.metadata["verified_statuses"] = statuses
                    result.metadata["last_status_check"] = now().isoformat()
                except FetchFailure as exc:
                    result.errors.append(exc.error)
        return result
