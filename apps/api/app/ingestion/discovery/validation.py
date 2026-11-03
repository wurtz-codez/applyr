"""Validate candidate boards through fixed public listing endpoints, without scraping."""

import re
from urllib.parse import quote

from app.ingestion.http import FetchFailure
from app.ingestion.policies import ATS


def board_endpoint(provider, board, region="global"):
    if provider not in ATS or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", board):
        raise ValueError("INVALID_BOARD_IDENTIFIER")
    token = quote(board, safe="")
    lever_host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    return {
        "greenhouse": (f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {}),
        "lever": (
            f"https://{lever_host}/v0/postings/{token}",
            {"mode": "json", "limit": 100},
        ),
        "ashby": (f"https://api.ashbyhq.com/posting-api/job-board/{token}", {}),
        "smartrecruiters": (
            f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
            {"limit": 100, "country": "in"},
        ),
    }[provider]


def board_records(provider, data):
    records = (
        data
        if provider == "lever"
        else (
            data.get("content" if provider == "smartrecruiters" else "jobs")
            if isinstance(data, dict)
            else None
        )
    )
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise FetchFailure("INVALID_BOARD_RESPONSE", False)
    # A valid empty board is real, but it cannot supply evidence for the India seed.
    return records


async def validate_board(http, provider, board, region="global"):
    url, params = board_endpoint(provider, board, region)
    data, _, _ = await http.get(url, params=params)
    records = board_records(provider, data)
    # Some providers return an empty success even for nonexistent board identifiers.
    # Defer these candidates until there is a public posting proving the board exists.
    if not records:
        raise FetchFailure("BOARD_HAS_NO_VERIFIABLE_POSTINGS", False)
    return records
