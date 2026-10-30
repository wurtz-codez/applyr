# JobPilot AI · Applyr

A self-hosted job discovery and application-tracking MVP for early-career software engineers.
Discover openings from configured Greenhouse boards, review eligibility and match evidence,
upload an existing resume, and track applications you submit yourself.

**Implemented:** discovery, deduplication, job search/detail, eligibility gates, deterministic
matching, optional Gemini matching, shortlists, private PDF uploads and defaults, application
tracking, run history, and optional scheduling. Resume tailoring and automated submission
are not implemented.

## Use the app

1. Open http://127.0.0.1:3000 and sign in with `API_TOKEN` from your private root `.env`.
2. In **Profile**, add your name and accurate skills, projects, education and experience.
   Include an evidence source and confirm the facts. Matching uses these verified statements.
3. In **Resumes**, upload a PDF up to 5 MiB. The first upload becomes the default. Additional
   versions remain separate; select **Set as default** when you want to change it.
4. In **Settings**, add public Greenhouse company boards. For a URL such as
   `https://job-boards.greenhouse.io/company-slug`, use `company-slug` as the board token.
   Discovery needs at least one enabled board; this provider does not offer a global job search.
5. Select **Discover jobs** from Dashboard or Jobs. The **Runs** screen shows progress,
   new/changed counts and source errors. Manual scans run locally without Redis.
6. Browse **Jobs**, search/filter, save promising roles, and open a job for eligibility reasons,
   score components, missing skills and supporting profile facts. Refresh a match after editing
   your profile. AI results are identified as Gemini; rule-based results are labeled separately.
7. Open the original listing and apply manually. Then choose **Record manual application**
   on its job detail page. The current default resume version is recorded for reference.
8. In **Applications**, update status to Applied, Interview, Offer, Rejected or Withdrawn,
   and save notes. Changing your default resume never changes an existing tracking record.

Uploaded PDFs stay unchanged. Uploads do not rewrite your profile or tailor a resume.
Recording an application only updates your tracker; it never submits anything to an employer.

## Gemini configuration

Gemini is optional. Without credentials, discovery and deterministic matching still work.
Add the following to your local root `.env` and restart the API:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_private_key
LLM_MODEL=your_available_model_id
AI_MAX_JOBS_PER_RUN=5
```

Use a model ID available to your Gemini account. The Settings screen reports whether a
provider, key and model are configured; this does not prove that the key or model is valid.
A provider failure falls back to deterministic matching and leaves a visible warning.
No live Gemini call has been verified without operator credentials; structured responses,
invalid evidence, caching and failure paths are tested using fixtures.

Only bounded job text and selected verified fact statements are sent to Gemini. The profile
name field, evidence-source fields, API credentials and uploaded PDF are not included in the
prompt. Facts themselves are user supplied, so avoid adding unrelated personal information.
The adapter accepts structured output, rejects invented fact IDs and unsupported skills,
and computes the weighted total on the server. AI cannot override an eligibility gate.

A discovery run makes at most `AI_MAX_JOBS_PER_RUN` new AI requests (0–10). Cached analyses
are reused; later scans can analyze additional eligible jobs. Manually clicking **Match with
Gemini** requests that job's analysis separately. AI requests may incur provider charges.

## Eligibility and matching

Defaults target software/backend/full-stack roles, 0–2 years, India or explicitly India-eligible
remote jobs. Rules reject obvious senior roles and explicit incompatible experience/location
requirements. Ambiguous geography, missing experience evidence, truncated descriptions and
unverified hard education/work-authorization requirements need review and are not ranked.
These conservative heuristics can miss or misread requirements; always read the source listing.

Scores are relative fit estimates, not hiring probabilities. Deterministic scores use keyword
coverage and verified evidence; Gemini returns scored components and evidence references.
Weights: skills 40%, role 25%, experience 20%, projects 15%. Editing your profile invalidates
old scores rather than displaying them as current. Refresh individual jobs or run discovery
again to rescore. A successful full scan must miss a job three times before it is marked closed;
failed or partially invalid feeds never count as closure evidence.

## Local development

Prerequisites: Node.js 24 LTS, pnpm 10.24.0, Python 3.12–3.14, and
[uv](https://docs.astral.sh/uv/getting-started/installation/). Docker remains optional.

From the repository root:

```sh
python3 scripts/bootstrap.py
pnpm install --frozen-lockfile
cd apps/api
uv sync --frozen --python 3.14
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal, from the repository root:

```sh
pnpm dev
```

If Turbopack cannot use macOS file events in your environment:

```sh
WATCHPACK_POLLING=true pnpm dev --webpack
```

App: http://127.0.0.1:3000 · API docs: http://127.0.0.1:8000/docs · liveness:
http://127.0.0.1:8000/healthz. Swagger's **Authorize** accepts the same bearer token.

Bootstrap creates a private `.env` and preserves an existing one. SQLite defaults to
`storage/jobpilot.db`; run API commands from `apps/api`. Resumes live in `storage/resumes/`
with generated storage names and private file permissions. `.env`, storage, browser state
and `IMPLEMENTATION_PLAN.md` are ignored. The implementation plan is local engineering
material and is not needed by a fresh clone.

Frontend API credentials remain server-side. Sign-in uses an HttpOnly, SameSite cookie and
Next.js Server Actions' origin checks. To change the API address, copy
`apps/web/.env.example` to `apps/web/.env.local` and edit `API_BASE_URL`.
For a production HTTPS deployment, review authentication and infrastructure separately.

## Scheduling and background execution

Manual scans use a durable run record and a local background thread by default. Duplicate
active scans are blocked by a database lease; repeating an already claimed task does not
re-ingest it. Source failures remain visible. A crashed run's lease expires after 20 minutes;
starting a subsequent run then marks the old one interrupted. In-process work is not a durable
queue, so keep the API running or use Celery for longer-lived background execution.

For local automatic discovery, add and restart the API:

```dotenv
DISCOVERY_EXECUTOR=local
DISCOVERY_SCHEDULE_ENABLED=true
DISCOVERY_INTERVAL_HOURS=6
```

The local scheduler checks every minute and skips discovery when the latest scan is more
recent than the configured interval. It needs a verified profile and at least one source.
Run a single local API process with SQLite. PostgreSQL is the intended worker database.

For PostgreSQL/Redis and Celery, see [infra/README.md](infra/README.md). Use
`DISCOVERY_EXECUTOR=celery`, enable scheduling for Beat when wanted, and run exactly one Beat
instance. Compose includes a shared volume for uploaded resumes. Docker/PostgreSQL/Redis have
not been run locally in this session; PostgreSQL migrations are included in CI validation.

## Verification

From `apps/api`:

```sh
uv run ruff check .
uv run pytest
uv run alembic check
```

From the repository root:

```sh
pnpm lint
pnpm typecheck
pnpm build --webpack
```

The tests cover discovery idempotency, conservative eligibility, expired leases, source
failures and closure rules, AI evidence validation/caching/budgets, profile changes, resume
limits/private downloads/defaults, and application tracking with immutable resume references.
The production build, static checks and an isolated HTTP form workflow have passed locally.
Live feeds and paid Gemini calls depend on external connectivity, configured sources and keys.

The HTTP form smoke test uses temporary SQLite/files and a fixture feed and model. It does not
add demo data to your real workspace or contact employers. Stop any frontend using the same
`.next` directory before running these in separate terminals:

```sh
# Terminal 1, repository root
apps/api/.venv/bin/python scripts/smoke_mvp.py serve

# Terminal 2, repository root
WATCHPACK_POLLING=true API_BASE_URL=http://127.0.0.1:8011 pnpm dev --webpack --port 3001

# Terminal 3, repository root
apps/api/.venv/bin/python scripts/smoke_mvp.py check
```

Restart the isolated fixture API before repeating the complete smoke test. These are HTTP
form tests, not a browser rendering or external integration test. CI runs the same workflow.

## API contracts and layout

```text
apps/web/            Next.js UI, authenticated actions and private download proxy
apps/api/            FastAPI, SQLAlchemy models, migrations, services, providers and tests
packages/contracts/  Generated OpenAPI and TypeScript schema types consumed by the UI
scripts/             Bootstrap, OpenAPI export and isolated form smoke test
infra/               Optional PostgreSQL/Redis/API/worker/Beat Compose setup
storage/             Ignored database and uploaded PDF artifacts
```

After changing schemas, regenerate and commit contracts:

```sh
cd apps/api
uv run python ../../scripts/export_openapi.py
cd ../..
pnpm contracts
```

## Next scope

Resume tailoring, approval of exact application payloads, and controlled browser submission
remain future work. Existing application records are manual tracking records, not confirmation
that an automated submission occurred. Additional ATS adapters and full browser tests can be
added after validating the initial boards and matching against your real search profile.

## References and license

[Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) ·
[Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output) ·
[FastAPI](https://fastapi.tiangolo.com/) · [Next.js](https://nextjs.org/docs) ·
[SQLAlchemy](https://docs.sqlalchemy.org/en/20/) · [Celery](https://docs.celeryq.dev/)

[MIT license](LICENSE), copyright 2026 KOUSTUBH.
