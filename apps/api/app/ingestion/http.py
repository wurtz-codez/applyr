"""Bounded HTTP retries, source-local pacing, and conditional JSON responses."""

import asyncio
import json
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.ingestion.schemas import FetchError


class FetchFailure(Exception):
    def __init__(self, code: str, recoverable=True, retry_after=None):
        self.error = FetchError(code=code, recoverable=recoverable, retry_after=retry_after)
        super().__init__(code)


def retry_seconds(value: str | None) -> float:
    try:
        return max(0, float(value or "0"))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


class HTTP:
    def __init__(self, client: httpx.AsyncClient, *, interval=1.0, sleep=asyncio.sleep):
        self.client, self.interval, self.sleep = client, interval, sleep
        self.last_request = 0.0
        self.lock = asyncio.Lock()
        self.requests = 0

    async def get(self, url: str, *, params=None, cached=None):
        headers = {}
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("modified"):
                headers["If-Modified-Since"] = cached["modified"]
        for attempt in range(3):
            try:
                async with self.lock:
                    await self.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
                    self.last_request = time.monotonic()
                    self.requests += 1
                    async with self.client.stream(
                        "GET", url, params=params, headers=headers, timeout=20
                    ) as response:
                        body = bytearray()
                        if response.status_code == 200:
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body) > 20 * 1024 * 1024:
                                    raise FetchFailure("RESPONSE_TOO_LARGE", False)
            except httpx.TimeoutException:
                if attempt == 2:
                    raise FetchFailure("HTTP_TIMEOUT") from None
            except httpx.RequestError:
                if attempt == 2:
                    raise FetchFailure("HTTP_NETWORK_ERROR") from None
            else:
                if response.status_code == 304:
                    if not cached or "data" not in cached:
                        raise FetchFailure("INVALID_NOT_MODIFIED", False)
                    return cached["data"], cached, True
                if response.status_code == 200:
                    try:
                        data = json.loads(body)
                    except ValueError:
                        raise FetchFailure("INVALID_JSON", False) from None
                    return (
                        data,
                        {
                            "etag": response.headers.get("etag"),
                            "modified": response.headers.get("last-modified"),
                            "data": data,
                        },
                        False,
                    )
                if response.status_code == 429:
                    delay = retry_seconds(response.headers.get("retry-after"))
                    if delay > 30 or attempt == 2:
                        raise FetchFailure("HTTP_429", retry_after=delay)
                    await self.sleep(delay)
                elif response.status_code < 500 or attempt == 2:
                    raise FetchFailure(f"HTTP_{response.status_code}", response.status_code >= 500)
            await self.sleep(2**attempt + random.random())
        raise FetchFailure("RETRIES_EXHAUSTED")
