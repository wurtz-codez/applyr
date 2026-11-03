"""Keyless expansion from permitted career pages, source hints, and catalog URLs."""

import asyncio
import json
import logging
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.bootstrap import CANDIDATES
from app.ingestion.discovery.ats_detector import detect
from app.ingestion.discovery.validation import validate_board
from app.ingestion.http import HTTP
from app.ingestion.schemas import SourceCreate
from app.ingestion.service import register_source
from app.models import IngestionSource, Job
from app.web_pages import PageFetcher

log = logging.getLogger(__name__)


def candidate_boards(session):
    """Only observed URLs; never guess board identifiers or scrape restricted platforms."""
    candidates = json.loads(CANDIDATES.read_text())
    known = session.scalars(select(IngestionSource).order_by(IngestionSource.id)).all()
    existing = {(s.provider, s.board_id) for s in known}
    for source in known:
        for hint in (source.sync_state or {}).get("discovered_boards", []):
            if isinstance(hint, dict):
                url = hint.get("career_url") or hint.get("url")
                if url:
                    candidates.append({"company": source.company_name, "source_url": url})
        # Career pages are crawled only with explicit permission, robots and SSRF protection.
        if (
            source.enabled
            and source.access_policy == "permitted"
            and source.provider == "career_page"
        ):
            candidates.append(
                {
                    "company": source.company_name,
                    "source_url": source.career_url,
                    "inspect_page": True,
                    "permitted": True,
                }
            )
    # ATS identities found in aggregator application links continuously expand the registry.
    for company, original, apply in session.execute(
        select(Job.company, Job.original_job_url, Job.apply_url)
        .where(
            Job.listing_type == "JOB_POSTING",
            Job.status == "active",
        )
        .order_by(Job.last_seen_at.desc())
        .limit(10000)
    ):
        for url in (original, apply):
            if url:
                candidates.append({"company": company or "Unknown employer", "source_url": url})
    return candidates, existing


def page_links(url):
    with_fetcher = PageFetcher(request_interval=1)
    try:
        deadline = time.monotonic() + 15
        with_fetcher.allowed(url, deadline)
        status, redirect, markup = with_fetcher.read(url, deadline, 2 * 1024 * 1024)
        if redirect:
            return [urljoin(url, redirect)]  # validate only; no cross-host HTML crawl
        if status != 200:
            return []
        return [
            urljoin(url, a["href"])
            for a in BeautifulSoup(markup, "html.parser").find_all("a", href=True)[:500]
        ]
    finally:
        with_fetcher.close()


async def discover_sources(engine, http_client=None):
    with Session(engine) as session:
        candidates, existing = candidate_boards(session)
    owned, count, attempted = http_client is None, 0, set()
    http_client = http_client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
    http = HTTP(http_client, interval=1)
    try:
        async with asyncio.timeout(480):
            for candidate in candidates[:10000]:
                urls = [candidate["source_url"]]
                if candidate.get("inspect_page") and candidate.get("permitted"):
                    try:
                        urls += await asyncio.to_thread(page_links, urls[0])
                    except Exception:
                        log.info("discovery_page_unavailable url=%s", urls[0])
                for url in urls:
                    try:
                        detected = detect(url)
                        if not detected or detected in existing or detected in attempted:
                            continue
                        if len(attempted) >= 100:
                            return count
                        attempted.add(detected)
                        provider, board = detected
                        region = "eu" if "jobs.eu.lever.co" in url else "global"
                        await validate_board(http, provider, board, region)
                        payload = SourceCreate(
                            company_name=candidate["company"],
                            provider=provider,
                            board_id=board,
                            career_url=url,
                            access_policy="public_api",
                            configuration={"region": region},
                            permission_notes=(
                                "Public listing endpoint validated by automated discovery"
                            ),
                        )
                        with Session(engine) as session:
                            try:
                                source = register_source(session, payload)
                                from app.ingestion.engine import queue_run

                                queue_run(session, source.id)
                                count += 1
                            except ValueError as exc:
                                if str(exc) != "SOURCE_ALREADY_REGISTERED":
                                    raise
                        existing.add(detected)
                    except Exception as exc:
                        log.info("discovery_candidate_unavailable error=%s", type(exc).__name__)
    finally:
        if owned:
            await http_client.aclose()
    return count
