"""Small, permitted crawls: feeds, JSON-LD, configured HTML, conservative detail fallback."""

import asyncio
import hashlib
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree

from app.ingestion.discovery.ats_detector import detect
from app.ingestion.http import FetchFailure
from app.ingestion.normalizer import enrich, location
from app.ingestion.schemas import FetchError, FetchResult, NormalizedJob
from app.normalization import canonical_url, date, text
from app.web_pages import PageFetcher, StructuredParser, job_nodes, location_name


def external_key(value):
    value = str(value)
    return value if len(value) <= 200 else "url:" + hashlib.sha256(value.encode()).hexdigest()


def jsonld(markup, page_url, source):
    parser = StructuredParser()
    parser.feed(markup)
    result = []
    for record in (r for doc in parser.documents for r in job_nodes(doc)):
        try:
            url = urljoin(page_url, record.get("url") or page_url)
            loc = record.get("jobLocation") or []
            loc = loc if isinstance(loc, list) else [loc]
            label = "; ".join(filter(None, [location_name(item) for item in loc])) or None
            requirements = record.get("applicantLocationRequirements")
            countries = None
            if requirements:
                requirements = requirements if isinstance(requirements, list) else [requirements]
                countries = [r.get("name", "") if isinstance(r, dict) else r for r in requirements]
            identifier = record.get("identifier") or {}
            identifier = identifier.get("value") if isinstance(identifier, dict) else identifier
            org = record.get("hiringOrganization") or {}
            result.append(
                enrich(
                    NormalizedJob(
                        source=source.provider,
                        external_id=external_key(identifier or canonical_url(url)),
                        company=org.get("name") or source.company
                        if isinstance(org, dict)
                        else source.company,
                        title=text(record.get("title"), 500),
                        description=text(record.get("description")),
                        job_url=url,
                        apply_url=record.get("applicationUrl") or url,
                        location=location(
                            label,
                            "remote" if record.get("jobLocationType") == "TELECOMMUTE" else None,
                            eligible=countries,
                        ),
                        employment_type=record.get("employmentType")
                        if isinstance(record.get("employmentType"), str)
                        else None,
                        posted_at=date(record.get("datePosted")),
                        valid_through=date(record.get("validThrough")),
                        raw=record,
                        source_fields=list(record),
                    )
                )
            )
        except (TypeError, ValueError, AttributeError):
            continue
    return result


def html_jobs(markup, page_url, source):
    soup = BeautifulSoup(markup, "html.parser")
    config = source.configuration.get("html", {})
    records = soup.select(config["item"]) if config.get("item") else [soup]
    jobs = []
    for node in records[:100]:
        title = node.select_one(config.get("title", "h1"))
        description = node.select_one(config.get("description", "[itemprop=description]"))
        apply = node.select_one(config.get("apply", 'a[href*="apply"]'))
        # The generic fallback requires job detail evidence, never just a Careers heading.
        if not title or not description or not apply:
            continue
        url_node = node.select_one(config["url"]) if config.get("url") else None
        url = urljoin(page_url, url_node.get("href", "")) if url_node else page_url
        label = node.select_one(config["location"]) if config.get("location") else None
        try:
            jobs.append(
                enrich(
                    NormalizedJob(
                        source=source.provider,
                        external_id=external_key(canonical_url(url)),
                        company=source.company,
                        title=title.get_text(" ", strip=True),
                        description=text(str(description)),
                        job_url=url,
                        apply_url=urljoin(page_url, apply.get("href", "")),
                        location=location(label.get_text(" ", strip=True) if label else None),
                        source_fields=["title", "description", "job_url", "apply_url"],
                    )
                )
            )
        except ValueError:
            continue
    return jobs


class Generic:
    def __init__(self, http=None, fetcher=None):
        self.fetcher = fetcher

    async def fetch_jobs(self, configuration, cursor=None):
        return await asyncio.to_thread(self.crawl, configuration)

    def crawl(self, source):
        pages = self.fetcher or PageFetcher(
            request_interval=source.configuration.get("request_interval_seconds", 1)
        )
        deadline = time.monotonic() + 90
        root = source.career_url
        origin = urlsplit(root).netloc
        queue = [source.configuration.get("feed_url") or root]
        if source.configuration.get("sitemap", False):
            queue.append(urljoin(root, "/sitemap.xml"))
        seen, jobs, errors, discovered = set(), [], [], []
        max_pages = min(20, max(1, int(source.configuration.get("max_pages", 10))))
        try:
            while queue and len(seen) < max_pages:
                try:
                    url = canonical_url(queue.pop(0))
                except ValueError:
                    errors.append(FetchError(code="INVALID_DISCOVERED_URL", recoverable=False))
                    continue
                if url in seen or urlsplit(url).netloc != origin:
                    continue
                seen.add(url)
                try:
                    pages.allowed(url, deadline)
                    status, redirect, markup = pages.read(url, deadline, 2 * 1024 * 1024)
                    if redirect:
                        target = canonical_url(urljoin(url, redirect))
                        if urlsplit(target).netloc == origin:
                            queue.append(target)
                        continue
                    if status != 200:
                        raise ValueError("PAGE_UNAVAILABLE")
                    if markup.lstrip().startswith("<?xml") or markup.lstrip().startswith(
                        ("<rss", "<feed", "<urlset", "<sitemapindex")
                    ):
                        tree = ElementTree.fromstring(markup)

                        def local(tag):
                            return tag.rsplit("}", 1)[-1]

                        if local(tree.tag) in {"urlset", "sitemapindex"}:
                            queue.extend(
                                n.text for n in tree.iter() if local(n.tag) == "loc" and n.text
                            )
                        else:
                            for entry in tree.iter():
                                if local(entry.tag) not in {"entry", "item"}:
                                    continue
                                fields = {local(n.tag): n for n in entry}
                                link = fields.get("link")
                                if link is not None:
                                    target = link.get("href") or link.text
                                    if target:
                                        queue.append(urljoin(url, target))
                        queue = queue[:1000]
                        continue
                    extracted = jsonld(markup, url, source) or html_jobs(markup, url, source)
                    jobs.extend(extracted)
                    soup = BeautifulSoup(markup, "html.parser")
                    for a in soup.select("a[href]")[:1000]:
                        target = urljoin(url, a["href"])
                        try:
                            canonical_url(target)
                            if detected := detect(target):
                                discovered.append(
                                    {
                                        "provider": detected[0],
                                        "board_id": detected[1],
                                        "url": target,
                                    }
                                )
                            elif any(
                                token in urlsplit(target).path.lower()
                                for token in ("job", "career", "position")
                            ):
                                queue.append(target)
                        except ValueError:
                            continue
                    queue = queue[:1000]
                except Exception as exc:
                    # Codes only; page content, query secrets, and HTML never enter run errors.
                    errors.append(FetchError(code="PAGE_EXTRACTION_FAILED", recoverable=True))
                    if isinstance(exc, TimeoutError):
                        break
            if queue:
                errors.append(FetchError(code="CRAWL_LIMIT", recoverable=True))
            if not jobs:
                errors.append(FetchError(code="NO_JOBPOSTINGS_EXTRACTED", recoverable=False))
            return FetchResult(
                jobs=list({j.external_id: j for j in jobs}.values()),
                errors=errors,
                metadata={"discovered_boards": discovered[:30]},
                statistics={"pages": len(seen)},
            )
        finally:
            if not self.fetcher:
                pages.close()


class Feed(Generic):
    """RSS/Atom feeds supply permitted detail URLs; details remain the source of job fields."""


class Browser:
    def __init__(self, http=None):
        pass

    async def fetch_jobs(self, configuration, cursor=None):
        from app.config import get_settings

        if not get_settings().browser_enabled:
            raise FetchFailure("BROWSER_DISABLED", False)
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise FetchFailure("INSTALL_BROWSER_EXTRA", False) from None
        # All browser requests are fulfilled by the existing pinned public HTTP transport.
        # This enforces DNS, robots, HTTPS, and resource bounds outside browser networking.
        pages = PageFetcher(
            request_interval=configuration.configuration.get("request_interval_seconds", 1)
        )
        resource_lock = asyncio.Lock()
        deadline, count = time.monotonic() + 45, 0
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(service_workers="block", accept_downloads=False)

                async def route(request_route):
                    nonlocal count
                    request = request_route.request
                    count += 1
                    if (
                        count > 80
                        or request.method != "GET"
                        or request.resource_type in {"image", "media", "font"}
                    ):
                        await request_route.abort()
                        return
                    try:
                        url = canonical_url(request.url)

                        def read():
                            pages.allowed(url, deadline)
                            return pages.read(url, deadline, 2 * 1024 * 1024)

                        async with resource_lock:
                            status, redirect, body = await asyncio.to_thread(read)
                        if redirect or status != 200:
                            await request_route.abort()
                            return
                        mime = (
                            "text/html"
                            if request.resource_type == "document"
                            else "application/javascript"
                            if request.resource_type == "script"
                            else "text/css"
                            if request.resource_type == "stylesheet"
                            else "application/json"
                        )
                        await request_route.fulfill(status=200, body=body, content_type=mime)
                    except Exception:
                        await request_route.abort()

                await context.route("**/*", route)

                async def block_socket(ws):
                    await ws.close()

                await context.route_web_socket("**/*", block_socket)
                page = await context.new_page()
                try:
                    await page.goto(
                        configuration.career_url, wait_until="networkidle", timeout=30000
                    )
                    markup = await page.content()
                    jobs = jsonld(markup, configuration.career_url, configuration) or html_jobs(
                        markup, configuration.career_url, configuration
                    )
                    return FetchResult(
                        jobs=jobs,
                        statistics={"requests": count},
                        errors=[] if jobs else [FetchError(code="NO_JOBPOSTINGS_EXTRACTED")],
                    )
                finally:
                    await context.close()
                    await browser.close()
        finally:
            pages.close()
