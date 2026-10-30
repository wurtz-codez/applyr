# Applyr

A backend for collecting job listings from public feeds and web search, storing them once,
and serving a filterable jobs dashboard. The previous application was removed in a separate
reset commit. This backend has no profile, matching, resume, or application workflow.

## What works now

- **Public feeds:** Arbeitnow, Remotive, and Jobicy; no company-board configuration or API keys.
- **Web discovery:** Tavily searches across websites using your local key and query.
- **Job-page extraction:** public pages with `JobPosting` JSON-LD are normalized into listings.
- **Storage:** canonical-URL deduplication, source attribution, tags, and first/last seen dates.
- **Dashboard API:** paginated jobs, job details, available filter values/counts, summary counts,
  and refresh progress/history.

A search hit is not automatically a job posting. Generic careers pages, blocked pages, and
pages without structured job data remain `SEARCH_RESULT` records with unknown company,
location, salary, and other fields left empty. `listing_type=JOB_POSTING` selects feed listings
and extracted postings. Search snippets are never promoted into structured job postings without page evidence.

This collects from the connected sources and indexed results, not literally every website.
It does not bypass access restrictions or confirm that every collected posting is still open.

## Run locally

Prerequisites: Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The Makefile also recognizes the existing `.tools/python/bin/uv` installation in this workspace.

```sh
python3 scripts/bootstrap.py
make install
make dev
```

The API runs at **http://127.0.0.1:8000**:

- `/docs` — interactive API explorer
- `/redoc` — API reference
- `/healthz` — liveness

The fresh database is `storage/jobs.sqlite3`. Startup applies Alembic migrations automatically.
This path is independent of the previous app's database. Run one API process for local SQLite
use. An optional `JOBS_DATABASE_URL` overrides the database; `DATABASE_URL` from the old app is
ignored.

The reset preserved `.env`, Git history, Python tools, and private archived data under
`storage/archive-*`. These are ignored by Git. The previous edited Compose example was archived
there too. The backend README does not depend on the ignored `IMPLEMENTATION_PLAN.md`.

## Collect jobs

Set your key in the root `.env`:

```dotenv
TAVILY_API_KEY=your_private_key
DEFAULT_SEARCH_QUERY=software engineer jobs India
SEARCH_RESULTS_PER_QUERY=10
MAX_SEARCH_REQUESTS_PER_DAY=10
ENRICH_WEB_RESULTS=true
```

Keep the generated `API_TOKEN`. Restart the API after editing configuration.
No key belongs in source code or a browser bundle.

In another terminal, from the repository root:

```sh
make refresh
make jobs
```

Or run a specific query/source:

```sh
uv run --project apps/api --frozen python -m app.cli refresh --query "backend engineer jobs India"
uv run --project apps/api --frozen python -m app.cli refresh --provider arbeitnow
uv run --project apps/api --frozen python -m app.cli jobs --q Python --limit 10
```

In this workspace, `.tools/python/bin/uv` can replace `uv`. Alternatively, after installation,
`apps/api/.venv/bin/python -m app.cli ...` works directly.

The default refresh uses the three public feeds and adds Tavily when a key is configured.
An explicit Tavily refresh without a key returns a configuration error. A query controls web
search; feed ingestion remains broad so the dashboard can apply different filters afterward.

The CLI and HTTP endpoint call the same collector. Failures retain existing listings and appear
per source. A refresh already in progress is protected by a database lease. Interrupted work
can be retried after the lease expires (15 minutes); in-process work is not a durable queue.

## Dashboard API contract

All `/api/v1` routes require `Authorization: Bearer <API_TOKEN>`. In `/docs`, use **Authorize**
and paste the value from `.env`. Health and the API schema are public. The key is not returned
by any data endpoint.

| Method | Endpoint | Result |
| --- | --- | --- |
| GET | `/api/v1/jobs` | Paginated matching records and total count |
| GET | `/api/v1/jobs/{id}` | Full job detail and provenance |
| GET | `/api/v1/jobs/filters` | Available filter values and counts for the current filters |
| GET | `/api/v1/dashboard` | Counts for current filters and latest refresh |
| GET | `/api/v1/sources` | Source configuration, attribution, refresh interval and last success |
| POST | `/api/v1/discovery/runs` | Start refresh; returns 202 and a run ID |
| GET | `/api/v1/discovery/runs` | Recent refreshes |
| GET | `/api/v1/discovery/runs/{id}` | Progress, per-source counts, errors and next refresh times |

Start a refresh with a JSON body:

```json
{
  "query": "software engineer jobs India",
  "providers": ["arbeitnow", "remotive", "jobicy", "tavily"]
}
```

Omit `providers` to use configured defaults. Job-list responses include short descriptions;
full descriptions are loaded from job detail. Summary counts distinguish `job_postings` from
`search_results`. `new_today` means first collected today, not necessarily published today.
All timestamps in API responses use UTC.

### Filters

Filters work together and also apply to `/jobs/filters` and `/dashboard`:

| Parameter | Meaning |
| --- | --- |
| `q` | Literal keyword search in title, company and description |
| `company` | Company name, case-insensitive exact match |
| `location` | Location text contains the value; not a country/eligibility inference |
| `work_mode` | `REMOTE`, `HYBRID`, `ONSITE`, or `UNKNOWN` |
| `employment_type` | Source-reported job type, such as `Full-time` or `Contract` |
| `experience_level` | Source-reported seniority, when available |
| `listing_type` | `JOB_POSTING` or `SEARCH_RESULT` |
| `source` | Provider; repeat for multiple providers (OR) |
| `tag` | Repeat for multiple tags; every selected tag must match (AND) |
| `posted_within_days` | Uses published date; unknown publication dates do not match |
| `seen_within_days` | Uses last observed date |
| `min_salary` | Requires both `currency` and `salary_period` |
| `currency` | Three uppercase letters, e.g. `USD` |
| `salary_period` | `hourly`, `daily`, `weekly`, `monthly`, or `yearly` |
| `sort` | `newest`, `oldest`, `title`, or `salary_desc` |
| `page`, `page_size` | Page starts at 1; at most 100 records per page |

The main jobs grid should request `listing_type=JOB_POSTING`; incomplete search leads can be
shown separately with `listing_type=SEARCH_RESULT`.

Example: `/api/v1/jobs?q=Python&work_mode=REMOTE&tag=python&listing_type=JOB_POSTING&page_size=25`.
Salary sorting also requires currency and period, so currencies and hourly/yearly amounts are
never silently mixed. Facets come from stored data rather than invented filter choices.

## Collection limits and safety

- Public feeds are fetched from fixed endpoints. Pagination is bounded to three pages per
  source per refresh, and truncated traversals are marked `partial`.
- Arbeitnow and Jobicy refresh at most hourly; Remotive at most every six hours. Repeated
  requests within the interval use stored data. Rate-limit responses and cooldowns are visible.
- Tavily caches the same query for 30 minutes, caps daily search requests, uses basic search,
  disables automatic provider parameter selection, and does not request generated answers.
- At most ten search-result pages are fetched for structured extraction per query. Requests
  have deadlines and size limits. Redirects are checked, private addresses are blocked, DNS
  destinations are pinned with the original TLS hostname, and robots rules are respected.
- Descriptions must be rendered as plain text, never inserted as HTML. Missing salary, location, seniority and company are not guessed.
  A source link and attribution remain with each record.
- Source outages do not delete old jobs. Presence in the database is not proof of current
  availability; last-seen and publication dates are exposed for review.

Source data has coverage limits: Arbeitnow focuses on European markets; Remotive and Jobicy
supply remote roles. Remote location text is not proof that an India-based applicant is eligible.
Remotive's public data is delayed and requires attribution. The future UI must display the
returned source names/links and preserve the provider's original listing link.

## Validate

```sh
make check
```

This runs Ruff, 28 backend tests and the migration/schema check. Tests use isolated databases
and HTTP fixtures, not your live jobs or paid API calls. They cover filters/pagination, salary
units, deduplication/provenance, quality upgrades, source failures/cooldowns, search budgets,
run leases, structured extraction, robots/redirect/DNS protections, authentication and migrations.

Live collection has also been verified against stored feed records and Tavily responses.
Connectivity in the agent command environment may differ from your own terminal; the CLI
prints source-level connection errors rather than substituting fixture data.

The dashboard frontend is a separate step. Frontend changes already present under `apps/web`
are independent of this backend reset; this implementation does not overwrite them.

## Source references

[Arbeitnow API](https://www.arbeitnow.com/blog/job-board-api) ·
[Remotive API](https://github.com/remotive-com/remote-jobs-api) ·
[Jobicy API](https://github.com/Jobicy/remote-jobs-api) ·
[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) ·
[JobPosting structured data](https://developers.google.com/search/docs/appearance/structured-data/job-posting)

[MIT license](LICENSE).
