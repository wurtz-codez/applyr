import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

MAX_FEED_BYTES = 10 * 1024 * 1024


class SourceError(Exception):
    pass


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(content: str) -> str:
    parser = TextParser()
    parser.feed(html.unescape(content))
    return " ".join("".join(parser.parts).split())


@dataclass(frozen=True)
class NormalizedJob:
    external_id: str
    title: str
    location_text: str
    source_url: str
    description_text: str
    description_hash: str
    description_truncated: bool


def normalize(raw: dict, board: str) -> NormalizedJob:
    external_id = raw.get("id")
    if type(external_id) is not int or external_id <= 0:
        raise ValueError("Invalid job ID")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Missing job title")
    location = (raw.get("location") or {}).get("name") or "Unspecified"
    if not isinstance(location, str) or not isinstance(raw.get("content", ""), str):
        raise ValueError("Invalid job content")
    description = plain_text(raw.get("content", ""))
    url = raw.get("absolute_url", "")
    parsed = urlsplit(url)
    hosts = {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io"}
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username:
        url = f"https://job-boards.greenhouse.io/{board}/jobs/{external_id}"
    truncated = len(description) > 60000 or len(title) > 300 or len(location) > 500
    title, location, description = title[:300].strip(), location[:500], description[:60000]
    fingerprint = hashlib.sha256(
        json.dumps([title, location, description, truncated]).encode()
    ).hexdigest()
    return NormalizedJob(
        str(external_id),
        title,
        location,
        url[:1000],
        description,
        fingerprint,
        truncated,
    )


def fetch_jobs(board: str, client: httpx.Client | None = None) -> tuple[list[NormalizedJob], int]:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", board):
        raise SourceError("INVALID_BOARD_TOKEN")
    owns_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=False)
    try:
        for attempt in range(2):
            try:
                deadline = time.monotonic() + 30
                url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
                with client.stream("GET", url, params={"content": "true"}) as response:
                    if response.status_code == 429:
                        raise SourceError("SOURCE_RATE_LIMITED")
                    if response.status_code in {502, 503, 504} and attempt == 0:
                        time.sleep(0.5)
                        continue
                    response.raise_for_status()
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > MAX_FEED_BYTES or time.monotonic() > deadline:
                            raise SourceError("SOURCE_RESPONSE_LIMIT")
                data = json.loads(chunks)
                if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                    raise SourceError("INVALID_SOURCE_RESPONSE")
                if len(data["jobs"]) > 5000:
                    raise SourceError("SOURCE_RESPONSE_LIMIT")
                jobs, invalid = {}, 0
                for raw in data["jobs"]:
                    try:
                        job = normalize(raw, board)
                        jobs[job.external_id] = job
                    except (ValueError, TypeError, AttributeError):
                        invalid += 1
                return list(jobs.values()), invalid
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    continue
                raise SourceError("SOURCE_UNAVAILABLE") from None
            except (httpx.HTTPError, ValueError, TypeError):
                raise SourceError("INVALID_OR_UNAVAILABLE_SOURCE") from None
        raise SourceError("SOURCE_UNAVAILABLE")
    finally:
        if owns_client:
            client.close()
