# Job ingestion setup

Run commands from the repository root unless a working directory is specified. Python 3.12–3.14, uv, PostgreSQL 16+, and Redis 7+ are required for scheduled ingestion. Node 24 and pnpm 10 are used for the existing Next.js dashboard. Docker Compose provides PostgreSQL/Redis/backend services as an alternative. No Tavily or model API key is needed.

## Local installation and environment

```sh
python3 scripts/bootstrap.py
uv sync --project apps/api --frozen
pnpm --dir apps/web install --frozen-lockfile
```

Bootstrap preserves an existing `.env`; add new settings from `.env.example` manually if necessary. Set the root `.env`:

```dotenv
API_TOKEN=<a-generated-secret-at-least-32-characters>
JOBS_DATABASE_URL=postgresql+psycopg://localhost/applyr
REDIS_URL=redis://localhost:6379/0
INGESTION_MAX_PAGES=100
INGESTION_MAX_STATE_MB=32
JOBSPY_ENABLED=false
BROWSER_ENABLED=false
```

Bootstrap generates the API token. Keep it private. `TAVILY_API_KEY` can remain empty. Never put actual credentials in seed JSON or commit `.env`.

Start your PostgreSQL and Redis services using your operating system's service manager. On macOS with Homebrew, for example:

```sh
brew services start postgresql@16
brew services start redis
createdb applyr
```

Use your installed PostgreSQL version's service name if different. If credentials are required, include them in `JOBS_DATABASE_URL`. `postgres://` and `postgresql://` URLs are normalized to the installed psycopg driver.

## Database initialization and migrations

```sh
uv run --project apps/api --frozen python -m app.cli init-db
(cd apps/api && uv run --frozen alembic current)
(cd apps/api && uv run --frozen alembic check)
```

Alternatively `(cd apps/api && uv run --frozen alembic upgrade head)` runs migrations directly. API startup also invokes the existing migration function. The preserving ingestion migration is `f19d7a21`; profile matching is `b812c730`; indexed alternate occurrence identity is `c32ef819`. Use one migration deployment step before scaling application instances. Production downgrades to the legacy schema can collapse source occurrences; back up first.

## Start API, worker, scheduler and frontend

Use four terminals, each at the repository root:

```sh
# Terminal 1
uv run --project apps/api --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```sh
# Terminal 2: regular ingestion and matching; never runs a browser
uv run --project apps/api --frozen celery -A app.workers.celery_app:celery worker -Q ingestion --concurrency=2 --loglevel=INFO
```

For local macOS/Python 3.14 development, use this worker command instead:

```sh
uv run --project apps/api --frozen celery -A app.workers.celery_app:celery worker -Q ingestion --pool=solo --concurrency=1 --loglevel=INFO
```

The default process pool failed task execution on the verified macOS installation; the solo pool successfully executed Redis-backed scheduler and matching tasks. Solo is a local development mode; use Linux process-pool workers for Celery process time limits.

```sh
# Terminal 3: only one Beat instance
uv run --project apps/api --frozen celery -A app.workers.celery_app:celery beat --loglevel=INFO
```

```sh
# Terminal 4
pnpm --dir apps/web dev
```

The dashboard uses server-side `API_BASE_URL` (default `http://127.0.0.1:8000`) and the same `API_TOKEN`. It can read the root `.env` in local development. For a separately deployed web service, set these server variables explicitly; do not use `NEXT_PUBLIC_API_TOKEN`.

Open `http://127.0.0.1:3000/jobs` and `/jobs/sources`. Read operations use the existing server configuration. Management operations require entering the administrator token in the Sources page; it remains in page memory. Queued/running status is refreshed every five seconds. The UI never substitutes a successful scrape message for a queued operation.

## Register and synchronize a company board

You can use the UI, authenticated API, or seed CLI. Example configuration is disabled initially so operators can review access first:

```sh
uv run --project apps/api --frozen python -m app.ingestion.cli seed config/job_sources.example.json
uv run --project apps/api --frozen python -m app.ingestion.cli sources
```

The seed command is idempotent and does not overwrite existing source policy/configuration. To register one enabled board through the API, make the token available to curl in your shell (do not paste it into shell history):

```sh
read -r -s API_TOKEN
export API_TOKEN
```

Paste your root `.env` token at the prompt, then press Enter. On shells without silent `read`, use the shell's secret input mechanism or your secret manager. The following Bash/zsh commands use that variable:

```sh
curl -sS http://127.0.0.1:8000/api/v1/sources \
  -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"company_name":"Ashby","website":"https://www.ashbyhq.com/","career_url":"https://jobs.ashbyhq.com/Ashby","provider":"auto","access_policy":"public_api"}'
```

Copy the returned source UUID. The example declares access to the documented public ATS API; review current provider/employer terms for your use. If you seeded this board first, use its existing ID instead of registering it again.

```sh
SOURCE_ID='paste-the-source-uuid-here'
curl -sS -X PATCH "http://127.0.0.1:8000/api/v1/sources/$SOURCE_ID" \
  -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"enabled":true,"access_policy":"public_api"}'
curl -sS -X POST "http://127.0.0.1:8000/api/v1/sources/$SOURCE_ID/sync" \
  -H "Authorization: Bearer $API_TOKEN"
```

The response is HTTP 202 with a durable `id`/`task_id`, initially `QUEUED`. `dispatched=false` means Beat has not dispatched it yet, not a completed ingestion. Beat checks pending runs every minute, and the regular worker executes them. Repeated requests while one run is active return the same run.

```sh
curl -sS http://127.0.0.1:8000/api/v1/ingestion/runs \
  -H "Authorization: Bearer $API_TOKEN"
curl -sS "http://127.0.0.1:8000/api/v1/sources/$SOURCE_ID" \
  -H "Authorization: Bearer $API_TOKEN"
curl -sS http://127.0.0.1:8000/api/v1/ingestion/stats \
  -H "Authorization: Bearer $API_TOKEN"
```

`GET /api/v1/ingestion/runs/{run_id}` returns one execution. `POST /api/v1/ingestion/sync?limit=100` reserves enabled/authorized sources independently; scheduled polling otherwise follows each source's next-fetch time.

For a local maintenance run **without Redis/Beat**, the same engine can execute inline outside the API process:

```sh
uv run --project apps/api --frozen python -m app.ingestion.cli sync "$SOURCE_ID" --inline
```

Without `--inline`, the CLI publishes the durable run to Redis immediately, while Beat can recover an unsuccessful dispatch. Do not run inline browser jobs in the API server. Large boards can exceed run/request limits and report partial results; inspect counters and errors.

## Inspect jobs and matching

```sh
curl -sS 'http://127.0.0.1:8000/api/v1/jobs?source=ashby&india_eligible=true&experience_max=2&include_uncertain=true&page=1&page_size=25' \
  -H "Authorization: Bearer $API_TOKEN"
uv run --project apps/api --frozen python -m app.cli jobs --limit 10
```

Use `include_uncertain=false` for explicit eligibility/experience only, `work_mode=REMOTE` for fully remote roles, `status=active`, `location=Bengaluru`, `q=backend`, and repeated `source` filters as needed. Unknown experience is not equivalent to zero. `GET /jobs/{id}` includes the description; all paths use `/api/v1`.

Register a matching profile with an opaque identifier for the user in this single-admin installation:

```sh
curl -sS http://127.0.0.1:8000/api/v1/matching/profiles \
  -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"user_key":"local-user-1","skills":["Python","SQL"],"max_experience":2,"india_only":true}'
```

Copy its returned ID into the feed's Matching profile field. After the scheduled matching task completes, choose Match score sorting, or query `/api/v1/jobs?match_profile=PROFILE_UUID&sort=match`. `GET /matching/profiles` reports pending status. Scores are deterministic with explicit uncertainty reasons; no LLM key is required. Shared bearer authentication is administrative, not tenant isolation.

## Permitted generic pages, feeds and browser extraction

Register a career page with `provider=career_page`, `career_url`, `access_policy=permitted` and `permission_notes`. A user-provided permitted job detail URL uses the same mechanism. Set optional configuration via `POST /sources`, for example:

```json
{
  "company_name": "Your employer",
  "provider": "career_page",
  "career_url": "https://careers.example.com/jobs",
  "access_policy": "permitted",
  "permission_notes": "Employer permits this collection; reference the actual policy.",
  "configuration": {
    "sitemap": true,
    "max_pages": 10,
    "retain_raw": false,
    "html": {
      "item": ".job-detail",
      "title": "h1",
      "description": ".description",
      "apply": "a.apply",
      "location": ".location"
    }
  }
}
```

Replace the example domain/selectors with an authorized real page. JSON-LD takes precedence over selectors. Crawls remain on one origin; robots denial, positive delay/rate directives or unavailable robots policy block fetching. `feed` sources follow RSS/Atom detail links; they currently need extractable detail pages. A configured `feed_url` is an alternative starting URL on the same origin. The bounded crawler is not an exhaustive site mirror.

Optional Playwright fallback:

```sh
uv sync --project apps/api --frozen --extra browser
uv run --project apps/api --frozen --extra browser playwright install chromium
```

Set `BROWSER_ENABLED=true`, register an explicitly permitted `provider=browser` source, and start a separate worker with the extra enabled:

```sh
uv run --project apps/api --frozen --extra browser celery -A app.workers.celery_app:celery worker -Q browser --concurrency=1 --loglevel=INFO
```

Keep the regular worker on `-Q ingestion`. Browser extraction is explicit and restrictive; it does not automate form submissions, credentials, CAPTCHA handling or blocked requests. It is not included in the default Docker image. On Linux, install Playwright's documented system dependencies for your deployment.

Optional JobSpy:

```sh
uv sync --project apps/api --frozen --extra jobspy
```

Set `JOBSPY_ENABLED=true` and keep the extra on the worker invocation (`uv run ... --extra jobspy celery ...`). A `jobspy` source requires permitted policy, permission notes, a career URL, and configuration containing `authorization_reference`, explicit `site_name` and `authorized_sites` lists. The requested sites must be a subset of the explicitly authorized list. Library options for proxies, credentials or evasion are not exposed. Do not enable a restricted platform without authorization; installation alone grants no access permission. Live JobSpy access has not been verified here.

## Optional company discovery

With `TAVILY_API_KEY` configured, this explicit command returns unverified source candidates:

```sh
uv run --project apps/api --frozen python -m app.ingestion.cli discover 'software companies India careers Ashby Greenhouse'
```

Review and register the candidates manually. The command never ingests jobs. There is no paid discovery task scheduled by default; automatic daily company discovery is planned. Legacy `app.cli refresh --provider tavily` remains an explicit compatibility path.

## Docker Compose

From the repository root, generate `.env`, then:

```sh
docker compose --env-file .env -f infra/compose.yaml up --build -d
```

Services: PostgreSQL, Redis, one-shot migration, API, regular worker and Beat. API binds to host loopback on port 8000. PostgreSQL/Redis persist to named volumes and are not exposed on host ports. Set a deployment-specific `POSTGRES_PASSWORD` in `.env` instead of the development fallback password. Avoid delimiter characters in that example's interpolated database password, or supply an appropriately encoded database URL in a deployment override.

```sh
docker compose --env-file .env -f infra/compose.yaml exec api python -m app.ingestion.cli seed /workspace/config/job_sources.example.json
docker compose --env-file .env -f infra/compose.yaml logs -f worker beat
```

Enable a seeded source through the API/UI before synchronizing. Run the existing frontend locally with `API_BASE_URL=http://127.0.0.1:8000` and the shared server token, or deploy it separately. Optional browser/JobSpy extras need a custom image/worker and are deliberately excluded from this default Compose stack. Docker image execution remains unverified. A subsequent local restart verified PostgreSQL, Redis, the API/frontend and a solo Celery worker executing Beat-dispatched tasks on macOS.

## Tests and checks

The existing test harness requires a dedicated PostgreSQL database name ending in `_test`; it refuses other names and truncates that test database. Do not point it at a production database. The default is `postgresql+psycopg://localhost/applyr_test`; it can create the database through the `postgres` administrative database if your local role has permission. In hosted CI, create the test database/service and provide both URLs.

```sh
TEST_DATABASE_URL=postgresql+psycopg://localhost/applyr_test \
  uv run --project apps/api --frozen pytest apps/api/tests -q
uv run --project apps/api --frozen ruff check apps/api
(cd apps/api && uv run --frozen alembic check)
pnpm --dir apps/web typecheck
pnpm --dir apps/web build
```

The suite covers all four connectors, pagination, timeouts, 429/conditional caching, idempotency, canonical identity and provenance, geography, experience uncertainty, failure preservation, source authorization, leases/task redelivery, snapshots, explicit expiry, profiles, and migrations. External responses are mocked, database integration uses real PostgreSQL, and an embedded real Celery worker exercises scheduled dispatch with an in-memory broker. The implementation verification run passed 62 tests; this does not substitute for validating Redis/Docker in your deployment.

An optional read-only live endpoint probe prints response shapes, not job descriptions:

```sh
uv run --project apps/api --frozen python scripts/check_public_boards.py
```

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `401` | Use the same private token in API and web server; supply it for curl and browser mutations. |
| Source remains pending or sync returns `409` | Review policy, enable the source, and provide permission notes for non-ATS connectors. |
| `QUEUED` persists | Start Redis, one Beat instance, and an `ingestion` worker; inspect Beat/worker logs and wait for the next minute tick. API queueing itself does not contact Redis. |
| Run stays running after worker loss | The lease expires after 12 minutes; the dispatcher can interrupt/replace the expired run. Disabled sources need manual re-enabling/retry. |
| `PARTIAL` / `PAGE_LIMIT_REACHED` | Prior pages are saved. Inspect errors, source scope, request interval and the run budget; do not interpret this as full-board freshness evidence. |
| `HTTP_429` | Honor Retry-After and reduce global concurrency/increase source request interval. Never bypass restrictions. |
| `NO_JOBPOSTINGS_EXTRACTED` | Check JSON-LD/selector configuration, page permission and supported resources; use explicit browser fallback only when permitted. |
| Robots error | Stop fetching; review source policy with its owner. Positive delay/rate directives are conservatively unsupported. |
| Remote India eligibility unknown | A remote office does not prove applicant eligibility. Inspect source data; retain uncertainty or use strict filtering. |
| Profile has no jobs | Keep Beat/worker running, inspect profile pending status, and allow matching to complete. |
| Browser or JobSpy disabled/missing | Install the appropriate extra, set its flag, restart the worker and maintain queue isolation. |
| Migration schema mismatch | Run `alembic upgrade head`, then `alembic check`; verify the database URL and single migration deployment step. |

See [architecture](JOB_INGESTION_ARCHITECTURE.md) for limitations and [connector development](CONNECTOR_DEVELOPMENT.md) to contribute another permitted source.
