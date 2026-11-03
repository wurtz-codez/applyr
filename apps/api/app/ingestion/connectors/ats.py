"""Documented public ATS APIs. Endpoint hosts are fixed, never taken from response refs."""

import hashlib
import json
from urllib.parse import quote, urlsplit

from app.ingestion.http import HTTP, FetchFailure
from app.ingestion.normalizer import enrich, location
from app.ingestion.schemas import FetchError, FetchResult, NormalizedJob, SourceConfig
from app.normalization import date, employment, text


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def base(
    source,
    raw,
    *,
    external_id,
    title,
    url,
    apply=None,
    description="",
    label=None,
    mode=None,
    country=None,
    posted=None,
    employment_type=None,
    requisition=None,
):
    return enrich(
        NormalizedJob(
            source=source.provider,
            external_id=str(external_id),
            company=source.company,
            title=text(title, 500),
            description=text(description),
            job_url=url,
            apply_url=apply,
            location=location(label, mode, country),
            posted_at=date(posted),
            employment_type=employment(employment_type),
            requisition_id=requisition,
            raw=raw,
            source_fields=["title", "job_url"]
            + [
                name
                for name, value in {
                    "description": description,
                    "location": label or country or mode,
                    "apply_url": apply,
                    "posted_at": posted,
                }.items()
                if value is not None and value != ""
            ],
        )
    )


class Greenhouse:
    def __init__(self, http: HTTP):
        self.http = http

    async def fetch_jobs(self, configuration: SourceConfig, cursor=None) -> FetchResult:
        s = configuration
        url = f"https://boards-api.greenhouse.io/v1/boards/{quote(s.board_id, safe='')}/jobs"
        listing, cache, unchanged = await self.http.get(
            url, params={"content": "true"}, cached=s.state.get("listing")
        )
        if not isinstance(listing, dict) or not isinstance(listing.get("jobs"), list):
            raise FetchFailure("INVALID_PAYLOAD", False)
        result = FetchResult(complete_snapshot=True, not_modified=unchanged)
        details = {}
        for summary in listing["jobs"]:
            try:
                key = str(summary["id"])
                previous = s.state.get("details", {}).get(key, {})
                version = summary.get("updated_at")
                if "content" in summary:
                    raw = summary
                elif version and previous.get("version") == version:
                    raw = previous["data"]
                else:
                    raw, _, _ = await self.http.get(f"{url}/{quote(key, safe='')}")
                details[key] = {"version": version, "data": raw}
                result.jobs.append(
                    base(
                        s,
                        raw,
                        external_id=key,
                        title=raw["title"],
                        url=raw["absolute_url"],
                        apply=raw["absolute_url"],
                        description=raw.get("content", ""),
                        label=(raw.get("location") or {}).get("name"),
                        requisition=raw.get("requisition_id"),
                        posted=raw.get("first_published") or summary.get("first_published"),
                        # updated_at is an edit time, not an employer publication date.
                    )
                )
            except FetchFailure as exc:
                result.errors.append(
                    exc.error.model_copy(update={"external_id": str(summary.get("id"))})
                )
            except (KeyError, TypeError, ValueError, AttributeError):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
        result.metadata = {"listing": cache, "details": details}
        result.statistics = {"listed": len(listing["jobs"]), "requests": self.http.requests}
        return result


class Lever:
    def __init__(self, http: HTTP):
        self.http = http

    async def fetch_jobs(self, configuration: SourceConfig, cursor=None) -> FetchResult:
        s = configuration
        offset, limit = int(cursor or 0), 100
        host = "api.eu.lever.co" if s.configuration.get("region") == "eu" else "api.lever.co"
        url = f"https://{host}/v0/postings/{quote(s.board_id, safe='')}"
        raw, cache, unchanged = await self.http.get(
            url,
            params={"mode": "json", "skip": offset, "limit": limit},
            cached=s.state.get("pages", {}).get(str(offset)),
        )
        if not isinstance(raw, list):
            raise FetchFailure("INVALID_PAYLOAD", False)
        result = FetchResult(
            next_cursor=str(offset + len(raw)) if len(raw) == limit else None,
            not_modified=unchanged,
            complete_snapshot=True,
        )
        for item in raw:
            try:
                cat = item.get("categories") or {}
                description = item.get("descriptionPlain") or item.get("description") or ""
                for section in item.get("lists", []):
                    description += (
                        "\n" + section.get("text", "") + "\n" + section.get("content", "")
                    )
                description += "\n" + (item.get("additionalPlain") or item.get("additional") or "")
                result.jobs.append(
                    base(
                        s,
                        item,
                        external_id=item["id"],
                        title=item["text"],
                        url=item["hostedUrl"],
                        apply=item.get("applyUrl"),
                        description=description,
                        label=cat.get("location"),
                        mode=item.get("workplaceType"),
                        country=item.get("country"),
                        employment_type=cat.get("commitment"),
                    )
                )
            except (KeyError, ValueError, TypeError, AttributeError):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
        result.metadata = {"pages": {**s.state.get("pages", {}), str(offset): cache}}
        return result


class Ashby:
    def __init__(self, http: HTTP):
        self.http = http

    async def fetch_jobs(self, configuration: SourceConfig, cursor=None) -> FetchResult:
        s = configuration
        payload, cache, unchanged = await self.http.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{quote(s.board_id, safe='')}",
            cached=s.state.get("listing"),
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise FetchFailure("INVALID_PAYLOAD", False)
        result = FetchResult(complete_snapshot=True, not_modified=unchanged)
        for item in payload["jobs"]:
            if not isinstance(item, dict):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
                continue
            if item.get("isListed") is not True:
                continue
            try:
                url = item["jobUrl"]
                address = (item.get("address") or {}).get("postalAddress") or {}
                result.jobs.append(
                    base(
                        s,
                        item,
                        external_id=item.get("id") or urlsplit(url).path.rstrip("/").split("/")[-1],
                        title=item["title"],
                        url=url,
                        apply=item.get("applyUrl"),
                        description=item.get("descriptionPlain") or item.get("descriptionHtml", ""),
                        label=item.get("location"),
                        country=address.get("addressCountry"),
                        mode=item.get("workplaceType"),
                        posted=item.get("publishedAt"),
                        employment_type=item.get("employmentType"),
                    )
                )
                job = result.jobs[-1]
                for secondary in item.get("secondaryLocations") or []:
                    if not isinstance(secondary, dict):
                        continue
                    extra_address = secondary.get("address") or {}
                    job.additional_locations.append(
                        location(
                            secondary.get("location"),
                            item.get("workplaceType"),
                            extra_address.get("addressCountry"),
                        )
                    )
                if job.location.remote_type != "remote" and any(
                    extra.india_eligible is True for extra in job.additional_locations
                ):
                    job.location.india_eligible = True
                    job.location.evidence = "source primary/secondary workplace"
                enrich(job)
            except (KeyError, ValueError, TypeError, AttributeError):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
        result.metadata = {"listing": cache}
        return result


class SmartRecruiters:
    def __init__(self, http: HTTP):
        self.http = http

    async def fetch_jobs(self, configuration: SourceConfig, cursor=None) -> FetchResult:
        s = configuration
        offset, limit = int(cursor or 0), 100
        url = f"https://api.smartrecruiters.com/v1/companies/{quote(s.board_id, safe='')}/postings"
        params = {"offset": offset, "limit": limit}
        # Only explicit source filters; local uncertainty never excludes junior roles.
        for key in ("q", "country", "city", "department"):
            if value := s.configuration.get("filters", {}).get(key):
                params[key] = value
        payload, cache, _ = await self.http.get(
            url, params=params, cached=s.state.get("pages", {}).get(str(offset))
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
            raise FetchFailure("INVALID_PAYLOAD", False)
        total = payload.get("totalFound")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise FetchFailure("INVALID_PAGINATION_TOTAL", False)
        records = payload["content"]
        next_offset = offset + len(records)
        more = next_offset < total
        if more and not records:
            raise FetchFailure("PAGINATION_STALLED", False)
        result = FetchResult(next_cursor=str(next_offset) if more else None, complete_snapshot=True)
        details = dict(s.state.get("details", {}))
        for summary in records:
            try:
                key = str(summary["id"])
                version = digest(summary)
                previous = details.get(key, {})
                if previous.get("version") == version:
                    raw = previous["data"]
                else:
                    raw, _, _ = await self.http.get(f"{url}/{quote(key, safe='')}")
                details[key] = {"version": version, "data": raw}
                loc = raw.get("location") or {}
                description = "\n".join(
                    section.get("text", "")
                    for section in (raw.get("jobAd") or {}).get("sections", {}).values()
                )
                apply = raw.get("applyUrl")
                if not apply:
                    raise ValueError("Missing public application URL")
                result.jobs.append(
                    base(
                        s,
                        raw,
                        external_id=key,
                        title=raw["name"],
                        url=raw.get("postingUrl") or apply,
                        apply=apply,
                        description=description,
                        label=", ".join(filter(None, [loc.get("city"), loc.get("country")])),
                        country=loc.get("country"),
                        mode="remote" if loc.get("remote") else "onsite",
                        posted=raw.get("releasedDate"),
                        employment_type=(raw.get("typeOfEmployment") or {}).get("label"),
                        requisition=raw.get("jobId"),
                    )
                )
                if raw.get("active") is False:
                    result.jobs[-1].status = "closed"
            except FetchFailure as exc:
                result.errors.append(
                    exc.error.model_copy(update={"external_id": str(summary.get("id"))})
                )
            except (KeyError, ValueError, TypeError, AttributeError):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
        result.metadata = {
            "pages": {**s.state.get("pages", {}), str(offset): cache},
            "details": details,
        }
        return result
