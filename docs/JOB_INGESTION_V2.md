# Job Ingestion v2

Applyr maintains one shared catalog of jobs and independent profile matches. The default
installation automatically registers 71 publicly validated India-focused employer boards
and four keyless public feeds. No Tavily, Adzuna, OpenAI, or other search/model key is
required. The administrator API token is a locally generated application secret, not a
third-party API subscription.

## Start the default installation

Requirements: PostgreSQL 16+, Redis 7+, Python 3.12–3.14, uv, and (for the dashboard)
Node 24/pnpm 10. PostgreSQL must exist before startup. `scripts/bootstrap.py` generates
the local token and preserves an existing `.env`.

```sh
python3 scripts/bootstrap.py
createdb applyr  # only on first installation
./scripts/dev.py
```

The development launcher installs dependencies, starts API/dashboard, starts a local Redis
process if a local server is configured but unavailable and `redis-server` is installed,
and starts the ingestion worker and Beat. It stops only its own processes on exit.
On macOS it selects Celery's solo pool; Linux uses two worker processes. PostgreSQL and
an existing Redis service are not stopped by the launcher. A custom Redis host must already
be available. Redis authentication/TLS remain deployment responsibilities.

For Docker (backend services, with persistent PostgreSQL/Redis volumes):

```sh
python3 scripts/bootstrap.py
docker compose --env-file .env -f infra/compose.yaml up --build -d
```

Run the existing frontend separately with its server API token and `API_BASE_URL`.
The migration service finishes before API/workers start. Source registration and first
sync requests are automatic. Do not seed example boards or click Sync to bootstrap.

For separately managed services, migrate before restarting workers, then start one Beat
and one or more workers subscribing to `ingestion`:

```sh
uv sync --project apps/api --frozen
uv run --project apps/api --frozen python -m app.cli init-db
uv run --project apps/api --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run --project apps/api --frozen celery -A app.workers.celery_app:celery worker -Q ingestion --concurrency=2 --loglevel=INFO
uv run --project apps/api --frozen celery -A app.workers.celery_app:celery beat --loglevel=INFO
```

Use separate terminals or a service manager. On macOS use `--pool=solo --concurrency=1`
for the worker. API-only installations serve stored data but cannot execute background
work. Web refresh always reads the catalog; it does not scrape or spend search credits.
Expect the first dispatch within a minute of Beat startup, then gradual results as boards
finish. Large boards and throttled providers take longer. Users only need job preferences.

## Upgrade and data preservation

Revision `d45ab901` extends the existing tables; it does not replace the ORM or catalog.
It adds indexed eligibility status/version fields, evidence/reason/method/confidence/time,
source seed ownership/override metadata, source verification timestamps, and a durable
maintenance lease table. Downgrade removes only these additions. API startup serializes
migrations with a PostgreSQL advisory lock. Compose also uses an ordered migration service.

Restart API, worker, and Beat after upgrading: existing Celery processes retain old Python
modules and Beat schedules. On startup, source configuration is reconciled and missing
boards are queued. A minute maintenance tick normalizes up to 250 legacy postings at a
time. Existing NULL boolean values become evaluated `CONFIRMED`, `NOT_ELIGIBLE`, or
`UNCERTAIN`; legitimate uncertainty remains NULL in the compatibility boolean.
The historical 1,462 postings take six batches with the default size once maintenance gets
worker time. Search pages are excluded, preserved as `SEARCH_RESULT`, and never matched.

Backfill uses stored location labels, structured normalized data when present, and existing
descriptions. It does not invent eligibility or blindly re-fetch arbitrary old URLs.
Scheduled provider sync supplies fresh metadata for still-published records; unsupported or
unavailable old sources remain evaluated as uncertain. A normalization version makes the
backfill idempotent, including for unchanged uncertain records. Future extraction changes
increment the version. Legacy manual feed writes also normalize new/changed postings.

## Bootstrap and verified sources

Production registry: `apps/api/app/ingestion/seed/companies_india.json`. The 71 boards were
verified through public listing endpoints during implementation. Each enabled entry includes
provider/token, employer name, India focus, careers URL, six-hour interval, and timestamped
HTTP 200 evidence with an observed Indian location/job URL. No full job descriptions or
applicant data are bundled. Validation tried 413 candidate configurations; failed, empty,
and non-India boards were excluded. Coverage is deliberately below the aspirational
100–200 target rather than including unverified identifiers. Endpoint availability and
current openings can change after verification.

The registry includes Indian companies such as Groww, CRED, Paytm, Sarvam AI and Zeta,
and global engineering employers with observed Indian jobs. It covers Greenhouse, Lever,
Ashby and SmartRecruiters. Broad employer feeds include senior/non-software jobs too:
local role, seniority, experience and geography normalization determines their relevance.
No title needs the word "junior" to enter the catalog.

API initialization performs only offline, transactional registration. An advisory
transaction lock serializes competing initializers; the existing provider/board unique
constraint is the final duplicate guard. Initial runs are committed in the same transaction
as new sources. Scheduler startup also bootstraps, so an API request is not needed.
The durable queue survives Redis downtime. An unavailable board fails only its own run.

Reconciliation uses previous bundle defaults, current database values, and new defaults.
Unmodified settings follow the bundle; changed fields and nested configuration keys remain
local overrides. API PATCH explicitly records override ownership, even if the chosen value
equals the old default. Existing manually registered sources are entirely locally owned.
Sources removed from a later bundle are retained. Nothing deletes a user's sources.

## Scheduling, locking and recovery

| Work | Default cadence | Persistent state |
| --- | --- | --- |
| Greenhouse, Lever, Ashby, SmartRecruiters | 6 hours | Source next fetch, run lease, cached validators/details |
| Arbeitnow | 6 hours | Source cooldown and rolling page checkpoint |
| Jobicy | 6 hours | Source cooldown and opaque cursor checkpoint |
| Remotive | 12 hours | Source cooldown; complete active feed snapshots |
| Himalayas | 24 hours | India search page or optional browse cursor checkpoint |
| Eligibility backfill | Check every minute, 250 rows per batch | Job normalization version; maintenance due time |
| Source discovery | Daily, checked by minute tick | Global maintenance lease and next run time |
| Freshness | Daily, checked by minute tick | Global maintenance lease and next run time |
| Profile matching | Every minute when dirty | Existing profile locks, dirty flag and persisted matches |

Beat scans sources and republishes pending durable run IDs every minute. A source row lock
and 12-minute lease prevent overlapping ownership; duplicate broker deliveries atomically
claim a queued run once. Expired queued/running leases are replaced even when an older
`next_fetch_at` is in the future. Task work is bounded by the existing nine-minute execution
deadline, page limit and HTTP limits. Redis redelivery and Beat republication are safe.
Use one Beat instance; database locks still protect accidental duplicate dispatch.

HTTP requests have fixed public API hosts, no redirects, bounded bodies/timeouts, three
attempts, source-local pacing, jitter and conditional requests where supported. HTTP 429
with `Retry-After` (seconds or date) defers long waits; a missing value defers at least a
minute. Run failures persist capped exponential backoff, respecting provider minimum feed
intervals and longer Retry-After values. No infinite retry loop is used. Manual legacy
feed requests and scheduled requests share the same `source_states` reservation, preventing
a refresh button from bypassing a feed's cooldown.

Rolling feeds are not full employer snapshots. Their checkpoints commit after each page,
including before a later failure, and bounded traversals continue at the next allowed sync.
A large feed can take several polling passes to cover fully. A finished traversal starts
again at the front on the next pass. Jobicy cursors expire after 24 hours; an invalid cursor
is cleared on HTTP 400 so the next allowed pass can recover. Board snapshots reconcile
absences only after a complete, error-free traversal, using the existing two-observation
closure rule. Failed or partial fetches never imply a job disappeared.

Maintenance tasks use independent PostgreSQL leases, persistent next-run times, success
records and exponential backoff. Restarts do not reset daily discovery/freshness limits.
Workers do not run a full ingestion pass in each process's startup hook.

## Provider formats and policies

Provider documentation reviewed during implementation; operators should recheck it when
upgrading or changing the use case. Preserve source attribution and original listing links.
Do not syndicate aggregator data to unrelated third-party job boards/search engines.

- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html): keyless published
  jobs; `content=true` returns descriptions in one request. The existing detail/cache
  fallback handles payloads that omit content. Do not use private Harvest/applicant APIs.
- [Lever public postings](https://github.com/lever/postings-api): `mode=json`, `skip`,
  `limit=100`; global and EU hosts. Lists include description sections and original Apply
  links. No candidate or application endpoints are called.
- [Ashby public job postings](https://developers.ashbyhq.com/docs/public-job-posting-api):
  published listed jobs, primary/secondary locations, public Apply links. `isListed=false`
  records are skipped. No authenticated organization API is used.
- [SmartRecruiters Posting API](https://developers.smartrecruiters.com/docs/posting-api):
  public company postings, offset/limit pagination with total validation, bounded detail
  requests and caching. Authentication for internal postings is outside this integration.
- [Arbeitnow](https://www.arbeitnow.com/blog/job-board-api): fixed keyless endpoint and
  numeric pages, mostly European coverage. A remote flag alone does not imply India access.
- [Jobicy](https://jobicy.com/jobs-rss-feed): 100 records per page, opaque cursor, seven-day
  discovery window; no more than one new pass per hour (default six hours). Keep Jobicy
  credit and its returned application URL. Direct ATS URLs are an optional commercial
  product and are not required or requested. No hardcoded `geo=india` is sent: the live
  taxonomy rejected that slug. Explicit configured filters must use current taxonomy values.
- [Remotive](https://github.com/remotive-com/remote-jobs-api): default two requests/day,
  within the recommended maximum four; public data is delayed. Preserve source credit and
  the Remotive listing URL. Do not gate these listings behind email/signup collection or
  redistribute them to third-party boards. The current local administrator token is an
  application access control, not a signup collection flow.
- [Himalayas API](https://himalayas.app/docs/remote-jobs-api) and
  [API terms](https://himalayas.app/terms): keyless, daily cached job data. Default
  `/jobs/api/search?country=IN` includes provider-selected India/worldwide candidates;
  normalize each job independently. Search uses `page`; browse uses opaque `nextCursor`,
  maximum 20 records/page. Responses can contain country names or country objects.
  Empty explicit country restrictions plus no timezone restrictions establish worldwide
  scope. Missing restrictions or ambiguous timezone restrictions remain uncertain. Keep
  `applicationLink` as every Apply destination and visible Himalayas credit. Do not replace
  the source link with a scraped employer URL or emit onward feeds/JobPosting JSON-LD.
  `guid` provides stable identity across employer slugs. `pubDate` is an update timestamp,
  so it is retained as source metadata and not asserted as an employer publication date.

Source request pacing is per source, not a global provider quota. Reduce worker concurrency
when adding many boards on one ATS host. No restricted-platform scraping, CAPTCHA bypass,
proxies, credentials, or authenticated applicant data access is introduced. Browser and
JobSpy remain optional, disabled by default, and require their existing access permissions.

## India geographic eligibility

`india_status` explicitly stores `CONFIRMED`, `NOT_ELIGIBLE`, or `UNCERTAIN`, with:

- `eligibility_reason`, structured `eligibility_evidence`, `eligibility_evaluated_at`;
- `eligibility_method=deterministic`, confidence when evidence supports it;
- `normalization_version`, plus derived enrichment in `normalized_json`;
- the original nullable `india_eligible` boolean for API/client compatibility.

| Evidence | Result |
| --- | --- |
| Bengaluru/India workplace, including an Indian secondary location | CONFIRMED |
| Remote — India, or explicit India applicant countries | CONFIRMED |
| Explicit worldwide remote without contrary country/timezone restrictions | CONFIRMED |
| Remote — US only; explicit applicant countries excluding India | NOT_ELIGIBLE |
| Hybrid — London with no Indian alternative | NOT_ELIGIBLE |
| Remote without applicant geography; APAC alone | UNCERTAIN |
| A company has an Indian office, but the remote job's eligibility is unspecified | UNCERTAIN |

Description rules require applicant/work-location language, not a passing mention of India.
Explicit exclusions/restrictions take priority. No LLM is required and no candidate's visa,
work authorization, degree, graduation year, or individual suitability is inferred from a
geographic result. Those requirements remain visible in the original description.

## Filtering, matching and identity

Broad shared ingestion retains source jobs before profile matching. Enrichment extracts
experience ranges, senior titles, software/backend/full-stack/developer role families and
technical skills. Ambiguous experience stays unknown; jobs are not rejected merely for
omitting junior keywords. All matching profiles consume this same catalog.

The default dashboard/API `sort=india` prioritizes real software job postings, confirmed
India geography, early-career/uncertain seniority, authoritative ATS data, then recency.
The dashboard requests active jobs. Newest/title/oldest/profile-score sorts remain available.
Existing India and experience filters can include or exclude uncertain records; new API
filters include `india_status=CONFIRMED` and `target_role=true`.

Identity uses verified ATS provider/board/external ID, canonical job/application URLs, and
requisition ID scoped to a verified employer. Feed providers are not employers: the feed's
registry company ID is never assigned to every listed employer or used to merge requisitions.
Different verified openings sharing a generic application form remain separate. Similar
company/title/location records are review candidates, not automatic merges.
Himalayas fallback IDs hash the full stable guid, preventing identical role slugs at two
employers from merging. Legacy feed occurrences are adopted without changing first-seen time.

Occurrences preserve source URL, external ID, first/last seen, last verified, active status,
and ATS identity. Normalized JSON keeps original application links; canonical keys strip
tracking parameters only for identity. Authoritative ATS content wins over aggregator data.
Repeated unchanged ingestion updates seen/verified times without duplicating jobs or
unnecessarily reranking profiles.

Explicit expiry closes an occurrence; another live source keeps the canonical job active.
Jobicy status checks run during its regular sync no more than daily, in batches of 100,
checking up to 1,000 oldest-verification occurrences. Only explicit active/closed results
change availability; unknown and failed checks do not invent closure. Other rolling feeds
cannot prove early closure from absence alone; explicit source expiry and employer
snapshots remain authoritative. No uptime or exhaustive coverage guarantee is made.

The existing `matching_profiles`/`job_matches` tables separate per-user preferences/results
from the shared catalog. No Google OAuth, user identity service, AI reranker, or application
submission is implemented. These can reference stable jobs and provenance later; application
actions should remain human approved in that future feature.

## Continuous keyless discovery and contributions

Daily discovery reads registered sources, observed canonical application URLs, existing
connector `discovered_boards` hints, and `seed/discovery_candidates.json`. It detects exact
known ATS URL patterns, validates the corresponding fixed public listing endpoint, registers
missing boards, and queues initial sync. Empty boards stay candidates: some providers return an empty HTTP 200 even for
unknown board names. The enabled India seed additionally requires observed Indian jobs.

Career-page inspection is allowed only for explicitly permitted pages, using the existing
robots-aware, public-IP-pinned, HTTPS-only fetcher. It reads one bounded page and extracts
ATS links; redirects can supply candidates but never grant arbitrary cross-host HTML crawl
permission. A candidate can set `inspect_page=true` and `permitted=true` after a contributor
reviews access. Do not add restricted platforms. Community directories can be supplied as
reviewed permitted candidate pages. At most 100 new boards and 10,000 candidate URLs are
examined per bounded daily run. Discovery cannot guarantee finding every employer.

To contribute, open a PR adding a real company and observed ATS careers URL to
`discovery_candidates.json` using fields `company` and `source_url`, or submit timestamped
validation evidence in `companies_india.json`. For bulk validation:

```sh
uv run --project apps/api --frozen python scripts/check_public_boards.py --candidates candidates.json --output verified.json
```

Input entries use `company`, `ats_provider`, `board_token`, `source_url`. The script validates
fixed public endpoints, paces each provider, and emits only configurations with observed
Indian locations. Review company identity, India/software coverage, evidence and terms before
merging the verified output. A separate `.report.json` records failures/empty boards; do not
copy those into enabled seed data. Never commit API keys or full third-party job datasets.

Optional Tavily discovery remains an explicit CLI capability when configured; it is never
necessary for the daily keyless process. Existing source-management APIs/UI and generic
permitted connectors remain usable for local additions.

## Operations and validation

`GET /api/v1/ingestion/stats` includes source health, run outcomes, eligibility counts,
maintenance last/next times and failures, catalog/occurrence counts, and last source success.
`/sources/registry` exposes managed-by-bundle and local override information.
`/ingestion/runs` retains per-source fetched/inserted/updated/deduplicated/failed metrics and
bounded error codes. Logs include run/source IDs, status/counters, bootstrap registration
counts, and maintenance outcomes. No secrets or job descriptions are logged.

| Symptom | Check |
| --- | --- |
| Empty catalog | API/worker/Beat use the same migrated PostgreSQL database; worker listens on `ingestion` |
| Queued work persists | Redis, Beat and worker availability; broker dispatch failure leaves the run durable |
| One board fails | Its run error, health, next fetch/backoff; other boards continue |
| Legacy records still unprocessed | `backfill` maintenance due time and worker capacity; normalization version |
| India results sparse | Confirmed vs uncertain filter, actual board locations, source freshness; no blanket remote assumption |
| Discovered URL not registered | Exact ATS pattern, endpoint validation, source permission, daily budget |
| Expired worker lease | Wait for the next scheduler tick after 12 minutes; expired ownership is replaced |
| Provider cursor rejected | Rolling cursor resets after HTTP 400; next sync honors cooldown |

```sh
uv run --project apps/api --frozen ruff check apps/api
uv run --project apps/api --frozen pytest apps/api/tests -q
pnpm --dir apps/web typecheck
pnpm --dir apps/web build
uv run --project apps/api --frozen python scripts/check_public_boards.py
uv run --project apps/api --frozen python scripts/check_public_boards.py --feeds
```

Tests use a dedicated PostgreSQL database ending in `_test`, synthetic HTTP fixtures and the
existing embedded Celery worker. They cover concurrency, idempotency, override ownership,
legacy migration/backfill, all four ATS formats, both Himalayas pagination formats,
keyless feed normalization, cooldowns, 429 handling, explicit closure, discovery validation,
provenance, identity collisions, filtering, matching and lease recovery. Tests never ingest
live feeds or truncate the configured production database. Live probes are separate.
