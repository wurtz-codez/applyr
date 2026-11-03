from app.ingestion.schemas import SourceConfig
from app.normalization import canonical_url

ATS = {"greenhouse", "lever", "ashby", "smartrecruiters"}
PUBLIC_FEEDS = {"arbeitnow", "jobicy", "remotive", "himalayas"}
RESTRICTED = {"linkedin.com", "indeed.com", "naukri.com"}


def check_access(source) -> None:
    if not source.enabled or source.access_policy in {"pending", "denied"}:
        raise ValueError("SOURCE_NOT_AUTHORIZED")
    if source.provider in ATS | PUBLIC_FEEDS:
        if source.access_policy not in {"public_api", "permitted"}:
            raise ValueError("PUBLIC_API_PERMISSION_REQUIRED")
    elif source.access_policy != "permitted" or not source.permission_notes:
        raise ValueError("EXPLICIT_PERMISSION_REQUIRED")


def validate_config(config: SourceConfig) -> None:
    import re
    from urllib.parse import urlsplit

    if config.provider in ATS and not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", config.board_id):
        raise ValueError("INVALID_BOARD_IDENTIFIER")
    if config.provider not in ATS and not config.career_url:
        raise ValueError("CAREER_URL_REQUIRED")
    interval = config.configuration.get("request_interval_seconds", 1)
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not 1 <= interval <= 60
    ):
        raise ValueError("REQUEST_INTERVAL_MUST_BE_1_TO_60_SECONDS")
    max_pages = config.configuration.get("max_pages", 10)
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 20:
        raise ValueError("CRAWL_MAX_PAGES_MUST_BE_1_TO_20")
    if config.configuration.get("region", "global") not in {"global", "eu"}:
        raise ValueError("INVALID_REGION")
    if config.career_url:
        host = urlsplit(canonical_url(config.career_url)).hostname
        if config.provider != "jobspy" and any(
            host == h or host.endswith("." + h) for h in RESTRICTED
        ):
            raise ValueError("USE_AN_AUTHORIZED_INTEGRATION_OR_JOB_URL")
