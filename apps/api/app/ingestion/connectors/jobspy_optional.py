"""Operator-authorized JobSpy integration; never imported by the default install."""

import asyncio

from app.ingestion.connectors.ats import base
from app.ingestion.http import FetchFailure
from app.ingestion.schemas import FetchError, FetchResult
from app.normalization import text


class JobSpy:
    def __init__(self, http=None):
        pass

    async def fetch_jobs(self, configuration, cursor=None):
        from app.config import get_settings

        if not get_settings().jobspy_enabled:
            raise FetchFailure("JOBSPY_DISABLED", False)
        try:
            from jobspy import scrape_jobs
        except ImportError:
            raise FetchFailure("INSTALL_JOBSPY_EXTRA", False) from None
        config = configuration.configuration
        if not config.get("authorization_reference"):
            raise FetchFailure("AUTHORIZATION_REFERENCE_REQUIRED", False)
        sites = config.get("site_name")
        authorized = config.get("authorized_sites")
        if (
            not isinstance(sites, list)
            or not sites
            or not isinstance(authorized, list)
            or not set(sites) <= set(authorized)
        ):
            raise FetchFailure("EXPLICIT_AUTHORIZED_SITES_REQUIRED", False)
        allowed = {
            key: config[key]
            for key in ("site_name", "search_term", "location", "country_indeed")
            if key in config
        }
        allowed["results_wanted"] = min(100, max(1, int(config.get("results_wanted", 25))))
        frame = await asyncio.to_thread(scrape_jobs, **allowed)
        result = FetchResult()
        for row in frame.to_dict(orient="records"):
            row = {k: v for k, v in row.items() if isinstance(v, (str, int, bool))}
            try:
                if not row.get("company"):
                    raise ValueError("Employer missing")
                job = base(
                    configuration,
                    row,
                    external_id=row.get("id") or row["job_url"],
                    title=row["title"],
                    url=row["job_url"],
                    apply=row.get("job_url_direct"),
                    description=row.get("description", ""),
                    label=row.get("location"),
                )
                job.company = text(row["company"], 300)
                result.jobs.append(job)
            except (ValueError, KeyError):
                result.errors.append(FetchError(code="INVALID_JOB", recoverable=False))
        return result
