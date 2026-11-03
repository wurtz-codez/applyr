# Developing connectors

Read [the architecture](JOB_INGESTION_ARCHITECTURE.md) and [setup](JOB_INGESTION_SETUP.md) first. A connector must use a documented supported interface or an explicitly permitted extraction method. Public accessibility alone is not authorization to redistribute data.

## Contract and registration

`app/ingestion/schemas.py` defines `JobConnector`, `SourceConfig`, `NormalizedJob`, `FetchResult`, and `FetchError`. The engine only calls:

```python
async def fetch_jobs(
    self, configuration: SourceConfig, cursor: str | None = None
) -> FetchResult: ...
```

`configuration` contains provider, board identifier, employer, career URL, operator settings and the last complete scan's synchronization state. Return normalized records, optional continuation cursor, state metadata, request statistics, and structured errors. Set `complete_snapshot=true` only if every page together describes the entire configured active source scope. An empty response with an invalid schema is an error, not a complete empty board.

Factories are registered by name in `app/ingestion/registry.py`. Add the connector module and one `register()` call in this composition root; do not edit the ingestion engine. Duplicate registration raises an error. Third-party packages can register factories before the worker/API imports complete; automatic Python entry-point loading is not implemented.

## Minimal working example

The following connector works with a permitted employer API whose documented response is `{"jobs": [{"id": ..., "title": ..., "url": ..., "description": ...}]}`. Replace the example domain only after reviewing a real provider's documentation and access terms.

```python
from urllib.parse import quote

from app.ingestion.http import HTTP, FetchFailure
from app.ingestion.normalizer import enrich, location
from app.ingestion.registry import register
from app.ingestion.schemas import FetchResult, NormalizedJob, SourceConfig
from app.normalization import text


class ExampleConnector:
    def __init__(self, http: HTTP):
        self.http = http

    async def fetch_jobs(
        self, configuration: SourceConfig, cursor: str | None = None
    ) -> FetchResult:
        # Fixed documented API host; never follow arbitrary response URLs.
        endpoint = (
            "https://jobs.example.com/api/boards/"
            + quote(configuration.board_id, safe="")
        )
        payload, cache, unchanged = await self.http.get(
            endpoint, cached=configuration.state.get("listing")
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise FetchFailure("INVALID_PAYLOAD", recoverable=False)
        jobs = [
            enrich(NormalizedJob(
                source=configuration.provider,
                external_id=str(row["id"]),
                company=configuration.company,
                title=text(row["title"], 500),
                description=text(row.get("description", "")),
                location=location(row.get("location")),
                job_url=row["url"],
                apply_url=row.get("apply_url"),
                raw=row,
                source_fields=["title", "job_url"],
            ))
            for row in payload["jobs"]
        ]
        return FetchResult(
            jobs=jobs,
            metadata={"listing": cache},
            not_modified=unchanged,
            complete_snapshot=True,
        )


register("example", ExampleConnector)
```

For this non-ATS example register an enabled source with `access_policy=permitted`, a career URL and permission notes. Production connectors should isolate malformed records with `FetchError` as the existing ATS adapters do, rather than allow a malformed row to abort an otherwise valid page. Registering a new ATS as a public API also requires updating the policy module's explicit `ATS` set and documenting the supported host/identifier validation.

## Pagination and incremental state

Return opaque string cursors; never invent pagination parameters for a provider. Lever uses numeric skip offsets; SmartRecruiters uses offset and totalFound. Greenhouse and Ashby return complete board snapshots and no continuation cursor. The engine keeps requesting pages, protects against repeated cursors, caps page counts, and commits each page's valid jobs.

Return incremental state in `metadata`. The engine merges it into the in-memory `SourceConfig.state` between pages and persists it only at the end of a scan. Do not overwrite complete caches with partial results after a failed page. Conditional caching must retain a response body or equivalent normalized records: a 304 without cached data cannot establish an empty board. Cache versioned detail records when the list exposes a reliable edit/repost token. An edit time is never a publication date.

Document how list ordering changes affect offset scans. The first implementation retries scans from the first page; cross-run mid-scan resumption is not implemented. Mark incomplete results as errors so freshness cannot interpret them as evidence of closure.

## Normalization and identity

- Use `NormalizedJob` and the shared HTML-to-text, date, employment, location and experience helpers.
- Keep stable external IDs. For providers with no ID, use a documented stable job URL/identifier; avoid page-position IDs.
- Keep original job and application URLs, including attribution. The deduplicator separately canonicalizes known tracking parameters while preserving job identifiers.
- Leave unknown country, experience, salary, applicant eligibility and publication date null. Do not infer worldwide eligibility from the word “remote”.
- `source_fields` identifies fields supported by the provider; `derived` records deterministic extraction. Experience and geographic inference retain confidence/evidence.
- Keep permitted raw data in `raw`; archival is opt-in per source. Document response-cache retention separately.
- Do not perform matching inside a connector. Canonical storage, provenance, matching and freshness belong to shared services.
- Never merge jobs by title alone. Similarity candidates need review.

## Permissions and configuration

`public_api` is reserved for the supported ATS adapters and affirmed access to their documented public GET methods. All other connectors require `permitted` and meaningful permission notes. `pending`/`denied` sources cannot run. New configuration must be validated in `policies.validate_config` and bounded. Keep secrets in environment configuration; do not put credentials in source JSON.

For generic pages, preserve public DNS validation, pinned addresses, robots checks, HTTPS-only destinations, origin restrictions, request budgets and deadlines. Do not route arbitrary untrusted career URLs through an unrestricted HTTP client. Do not add logins, CAPTCHA handling, proxy rotation or bypass behavior.

JobSpy requires its extra, environment flag, an authorization reference, explicit site list and authorized-sites list. Playwright requires its extra, environment flag, binary installation, and separate browser worker. Neither belongs in the default ingestion/API process.

## Failure handling

The shared HTTP utility provides timeouts, paced requests, three attempts, 429 Retry-After, jittered backoff and conditional caching. Raise `FetchFailure` for source/page errors. Return record-level `FetchError` entries when other records can safely continue. Error codes must be stable and must not contain credentials, HTML, applicant data or response dumps. Use `recoverable=false` for invalid payloads or unsupported configurations.

Never delete or close existing jobs because a fetch failed. Only complete successful snapshots or explicit provider expiry/status may affect freshness. The worker isolates sources; a connector should not swallow a network failure and return an apparently successful empty snapshot.

## Tests

Use `httpx.MockTransport`, synthetic fixtures and the dedicated PostgreSQL test database. Do not use live internet in CI. Existing examples are in `apps/api/tests/test_ingestion.py` and `tests/fixtures/ats.json`.

A minimal deterministic test for the example above:

```python
import asyncio
import httpx
from app.ingestion.http import HTTP
from app.ingestion.schemas import SourceConfig
# Import ExampleConnector from your new module.


def test_example_connector():
    async def run():
        def reply(request):
            assert request.url.host == "jobs.example.com"
            return httpx.Response(200, json={"jobs": [{
                "id": "1", "title": "Junior Developer",
                "url": "https://jobs.example.com/1",
            }]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            config = SourceConfig(provider="example", board_id="demo", company="Demo")
            result = await ExampleConnector(HTTP(client, interval=0)).fetch_jobs(config)
            assert result.jobs[0].external_id == "1"
            assert result.jobs[0].posted_at is None
    asyncio.run(run())
```

Also test malformed payloads, absent optional fields, pagination termination, unchanged descriptions, 304 behavior, 429 delays, timeouts, listed/unlisted visibility and URL identity. Add a pipeline test when new identity or storage behavior is involved. See the setup document for exact test commands. `scripts/check_public_boards.py` is an optional live probe, not a CI test or a bundled dataset.

## Pull requests and company-board contributions

Include provider documentation links, supported regions/endpoints, an example redacted response shape, access/attribution/retention considerations, dependency changes, synthetic fixtures, tests and architecture/setup updates. New paid or third-party integrations must remain optional. Do not commit credentials, response dumps, copyrighted job datasets, or applicant records.

For company seeds, submit employer name/website, verified career URL, board provider/identifier, policy notes and sensible interval. Leave uncertain candidates disabled/pending and describe what has been verified. Run lint, PostgreSQL tests, migration checks and frontend type checking when affected. Registration and parsing belong in the connector composition root; no source-specific branches should be added to `engine.py`.
