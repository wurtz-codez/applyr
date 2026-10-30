"""Bounded, public-only HTML fetching and structured JobPosting extraction."""

import ipaddress
import json
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.normalization import canonical_url, date, employment, tags, text
from app.schemas import JobData

USER_AGENT = "ApplyrJobCollector/0.1"


class PageBlocked(Exception):
    pass


class PublicTransport(httpx.BaseTransport):
    """Resolve once, reject private destinations, and pin the connection to that IP."""

    def __init__(self):
        self.transports = {}

    def handle_request(self, request):
        host = request.url.host
        canonical_url(str(request.url))
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise PageBlocked("PRIVATE_DESTINATION")
        address = sorted(addresses, key=lambda value: (":" in value, value))[0]
        headers = httpx.Headers(request.headers)
        headers["Host"] = host
        extensions = {**request.extensions, "sni_hostname": host}
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=headers,
            extensions=extensions,
        )
        # Pools must remain keyed by hostname, not only by the pinned IP. Otherwise
        # two CDN hosts on one IP could reuse a TLS connection verified for the other host.
        if host not in self.transports:
            self.transports[host] = httpx.HTTPTransport(retries=0)
        return self.transports[host].handle_request(pinned)

    def close(self):
        for transport in self.transports.values():
            transport.close()


class StructuredParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside, self.parts, self.documents = False, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and "application/ld+json" in dict(attrs).get("type", "").lower():
            self.inside, self.parts = True, []

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.inside:
            self.inside = False
            try:
                self.documents.append(json.loads("".join(self.parts)))
            except (ValueError, RecursionError):
                pass


def job_nodes(node, depth=0):
    if depth > 20:
        return
    if isinstance(node, list):
        for item in node[:200]:
            yield from job_nodes(item, depth + 1)
    elif isinstance(node, dict):
        types = node.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if isinstance(types, list) and any(
            str(item).rsplit("/", 1)[-1] == "JobPosting" for item in types
        ):
            yield node
        for key in ["@graph", "mainEntity", "itemListElement", "item"]:
            if key in node:
                yield from job_nodes(node[key], depth + 1)


def location_name(value):
    if isinstance(value, str):
        return text(value, 500)
    if not isinstance(value, dict):
        return ""
    address = value.get("address", value)
    if not isinstance(address, dict):
        return text(address, 500)
    parts = []
    for key in ["addressLocality", "addressRegion", "addressCountry", "name"]:
        item = address.get(key)
        if isinstance(item, dict):
            item = item.get("name")
        if isinstance(item, str) and item not in parts:
            parts.append(text(item, 100))
    return ", ".join(parts)


def extract_jobs(markup: str, page_url: str) -> list[JobData]:
    parser = StructuredParser()
    parser.feed(markup)
    records = [item for doc in parser.documents for item in job_nodes(doc)][:100]
    jobs = []
    for record in records:
        try:
            # Multi-job pages must identify each posting, not collapse all roles onto one URL.
            if len(records) > 1 and not record.get("url"):
                continue
            url = canonical_url(urljoin(page_url, record.get("url") or page_url))
            locations = (
                record.get("jobLocation") or record.get("applicantLocationRequirements") or []
            )
            locations = locations if isinstance(locations, list) else [locations]
            company = record.get("hiringOrganization") or {}
            company = company.get("name") if isinstance(company, dict) else company
            salary = record.get("baseSalary") or {}
            salary = salary if isinstance(salary, dict) else {}
            amount = salary.get("value") or {}
            amount = amount if isinstance(amount, dict) else {"value": amount}
            minimum = amount.get("minValue", amount.get("value"))
            maximum = amount.get("maxValue", amount.get("value"))
            period = str(amount.get("unitText") or "").lower()
            period = {
                "year": "yearly",
                "month": "monthly",
                "hour": "hourly",
                "week": "weekly",
                "day": "daily",
            }.get(period)
            currency = salary.get("currency")
            currency = (
                currency.upper() if isinstance(currency, str) and len(currency) == 3 else None
            )
            jobs.append(
                JobData(
                    canonical_url=url,
                    source_url=page_url,
                    title=text(record.get("title"), 500),
                    company=text(company, 300) or None,
                    location="; ".join(filter(None, (location_name(item) for item in locations)))[
                        :500
                    ]
                    or None,
                    description=text(record.get("description")),
                    work_mode="REMOTE"
                    if record.get("jobLocationType") == "TELECOMMUTE"
                    else "UNKNOWN",
                    employment_type=employment(record.get("employmentType")),
                    salary_min=minimum
                    if isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
                    else None,
                    salary_max=maximum
                    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool)
                    else None,
                    salary_currency=currency,
                    salary_period=period,
                    published_at=date(record.get("datePosted")),
                    tags=tags(
                        record.get("skills") if isinstance(record.get("skills"), list) else []
                    ),
                    enrichment_status="EXTRACTED",
                )
            )
        except (ValueError, TypeError, AttributeError):
            continue
    return jobs


class PageFetcher:
    def __init__(self, client=None):
        self.owns_client = client is None
        self.client = client or httpx.Client(
            transport=PublicTransport(),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": USER_AGENT},
        )
        self.robots = {}

    def read(self, url, deadline, limit):
        canonical_url(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PageBlocked("PAGE_TIMEOUT")
        with self.client.stream("GET", url, timeout=min(5, remaining)) as response:
            if response.is_redirect:
                return response.status_code, response.headers.get("location"), ""
            if response.status_code != 200:
                return response.status_code, None, ""
            if not any(
                t in response.headers.get("content-type", "")
                for t in ["text/", "application/xhtml"]
            ):
                raise PageBlocked("UNSUPPORTED_CONTENT_TYPE")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > limit or time.monotonic() > deadline:
                    raise PageBlocked("PAGE_LIMIT")
            return 200, None, data.decode(response.encoding or "utf-8", errors="replace")

    def allowed(self, url, deadline):
        origin = f"https://{urlsplit(url).netloc}"
        if origin not in self.robots:
            status, _, content = self.read(origin + "/robots.txt", deadline, 256000)
            if status == 404:
                self.robots[origin] = None
            elif status == 200:
                rules = RobotFileParser()
                rules.parse(content.splitlines())
                self.robots[origin] = rules
            else:
                raise PageBlocked("ROBOTS_UNAVAILABLE")
        rules = self.robots[origin]
        if rules is not None:
            # Skip sites requiring a delay instead of fetching them too quickly.
            delay = rules.crawl_delay(USER_AGENT) or rules.crawl_delay("*")
            rate = rules.request_rate(USER_AGENT) or rules.request_rate("*")
            if not rules.can_fetch(USER_AGENT, url) or (delay and delay > 0) or rate:
                raise PageBlocked("ROBOTS_BLOCKED")

    def fetch(self, url):
        deadline = time.monotonic() + 15
        for _ in range(4):
            url = canonical_url(url)
            self.allowed(url, deadline)
            status, location, content = self.read(url, deadline, 2 * 1024 * 1024)
            if 300 <= status < 400 and location:
                url = urljoin(url, location)
                continue
            if status != 200:
                raise PageBlocked("PAGE_UNAVAILABLE")
            return extract_jobs(content, url)
        raise PageBlocked("TOO_MANY_REDIRECTS")

    def close(self):
        if self.owns_client:
            self.client.close()
