import re
from urllib.parse import parse_qs, urlsplit

from app.normalization import canonical_url

PATTERNS = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "boards.eu.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.eu.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
    "careers.smartrecruiters.com": "smartrecruiters",
    "jobs.smartrecruiters.com": "smartrecruiters",
}


def detect(url: str) -> tuple[str, str] | None:
    value = urlsplit(canonical_url(url))
    provider = PATTERNS.get(value.hostname)
    if not provider:
        return None
    parts = value.path.strip("/").split("/")
    board = parts[0]
    if provider == "greenhouse" and board == "embed":
        board = parse_qs(value.query).get("for", [""])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", board):
        return None
    return provider, board
