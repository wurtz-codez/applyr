# JobPilot AI · Applyr

**Discover better-fit software engineering jobs. Prepare stronger applications. Stay in control of every submission.**

Applyr is a self-hosted AI-assisted job search platform. The planned workflow discovers
supported company career-board openings, checks eligibility, ranks jobs against verified
candidate facts, prepares tailored materials, and requires explicit human approval for
any future submission.

**Current status: Phase 0 running locally.** The repository now contains a Next.js dashboard,
local token sign-in, a verified profile form and API, SQLAlchemy models, Alembic migration,
Celery health task, and CI configuration. Dependencies are installed and SQLite migrations, 13 backend tests, Ruff, ESLint
(no errors), TypeScript checks, and local HTTP checks have passed. Production build,
PostgreSQL/Redis and browser interaction tests remain pending. This is the foundation,
not yet the job-discovery MVP.

| Available in source | Planned next |
| --- | --- |
| Authenticated profile read/write, verified facts, version counter | Greenhouse ingestion and deduplication |
| Dashboard and profile editing shell | Eligibility checks, matching, job search and shortlist |
| Local SQLite option and PostgreSQL-compatible models | PostgreSQL concurrency and integration validation |
| Worker configuration and health task | Six-hour discovery schedule and run history |
| Test suite and CI workflow | Generated, consumed frontend API contracts |

AI matching, resume generation, approvals, and browser submission are not implemented.
No application is automatically submitted. There are no fabricated job results.

## Stack and layout

- Frontend: Next.js App Router, React, TypeScript, Tailwind CSS. Add shadcn/ui components as feature screens grow.
- Backend: Python 3.12–3.14, FastAPI, Pydantic, synchronous SQLAlchemy 2, Alembic.
- Persistence: SQLite for single-user, single-process foundation development; PostgreSQL 16 for workers and the MVP.
- Background work: Celery and Redis, with scheduling intentionally idle until discovery exists.
- Tooling: pnpm 10.24.0, uv, pytest, Ruff, ESLint, GitHub Actions.

```text
apps/web/            Next.js dashboard, sign-in and profile form
apps/api/            FastAPI app, migrations, domain modules and tests
packages/contracts/  OpenAPI export and TypeScript generation commands
infra/               Optional Docker configuration for later use
scripts/             Local config bootstrap and OpenAPI export
storage/             Private local database and future artifacts (ignored)
```

The local `IMPLEMENTATION_PLAN.md` is deliberately ignored by Git. This README is the
public setup guide; do not depend on that private file being present in a clone.

## Local development without Docker

Prerequisites: Node.js 24 LTS, pnpm 10.24.0, Python 3.14 (or 3.12/3.13), and
[uv](https://docs.astral.sh/uv/getting-started/installation/). pnpm is installed on the
current development machine. Docker is deferred.

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

Open the dashboard at http://localhost:3000. The API docs are at
http://127.0.0.1:8000/docs and liveness is at http://127.0.0.1:8000/healthz.
Sign in using `API_TOKEN` from your private root `.env`. Swagger's **Authorize** button
accepts that same bearer token. No default password or public registration is provided.

The bootstrap script generates a secret and preserves an existing `.env`. The default
SQLite URL is relative to `apps/api`; run API and migration commands from that directory.
Your database is stored at `storage/jobpilot.db`. Restarting the app preserves it.

The frontend defaults to the local API address. To change it, copy
`apps/web/.env.example` to `apps/web/.env.local` and edit `API_BASE_URL`. API tokens are
never placed in `NEXT_PUBLIC_` variables. The sign-in form stores the token in an
HttpOnly, SameSite cookie; server-side code attaches it to API calls. Next.js Server
Actions provide same-origin checks on form submissions. This is a local development
authentication foundation, not a production account system.

Dependency lockfiles are committed; CI and container installs use frozen resolution.
Package downloads failed inside the agent environment, so initial dependencies were
installed from the user’s terminal. If registry DNS errors recur, install from a
terminal with network access.

If Turbopack cannot start an FSEvent stream in your environment, use the local fallback:

```sh
WATCHPACK_POLLING=true pnpm dev --webpack
```

## Verify the foundation

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
pnpm build
```

Backend tests cover authentication, verified-fact validation, profile persistence and
versioning, migration rollback, configuration restrictions, and the worker health task.
They use temporary SQLite databases and never submit applications. CI additionally
checks migrations against PostgreSQL. A real browser smoke test remains to be added.

Export the API contract after installing dependencies and generating `.env`:

```sh
cd apps/api
uv run python ../../scripts/export_openapi.py
cd ../..
pnpm contracts
```

Commit the generated OpenAPI and TypeScript files. The initial web profile types remain
local until contract generation can run; replacing them is a remaining foundation task.

## PostgreSQL, Redis and Docker later

Use PostgreSQL before enabling multiple writers or background discovery. SQLite is a
convenience for early profile development and does not validate PostgreSQL locking,
JSONB semantics, or concurrent workers.

Docker installation is deferred. Optional Compose files are prepared in `infra/`; see
[the infrastructure guide](infra/README.md) for credentials and startup commands. They
have not been executed locally. Keep Next.js on the host for development. Run exactly
one Beat instance when scheduling is enabled. There is no automatic SQLite-to-PostgreSQL
migration of personal data.

## Product roadmap

1. **Foundation:** run the production build, generate contracts, validate PostgreSQL/Redis, and add a browser smoke test.
2. **Discovery MVP:** allowlisted Greenhouse feeds, normalization, deduplication, conservative eligibility checks, deterministic scoring, dashboard filters, shortlist and run history.
3. **Application preparation:** verified fact library, versioned resumes, answer drafts, exact-payload approval and audit history.
4. **Controlled execution:** local mock ATS first, then individually permitted supported forms, confirmation evidence and recovery.
5. **Later:** more ATS sources, optional email tracking and multi-user support.

Default search preferences are software engineering, backend and full-stack roles,
0–2 years of experience, India or remote jobs explicitly open to India-based applicants.
Ambiguous eligibility must be marked for review. An AI score must never override an
eligibility gate.

## Integrity and privacy

- Use only candidate-verified qualifications and evidence. Never invent application facts.
- Treat job descriptions as untrusted data, not instructions.
- Keep `.env`, applicant artifacts, browser state, cookies and database files out of Git.
- Require explicit approval of the exact document and answers before any future submission.
- Pause for CAPTCHA, MFA, unknown required fields or changed application content.
- Respect source restrictions and rate limits; never retry uncertain submissions blindly.
- A health response proves process liveness only, not database or queue readiness.

## References and license

[Next.js](https://nextjs.org/docs) · [FastAPI](https://fastapi.tiangolo.com/) ·
[SQLAlchemy](https://docs.sqlalchemy.org/en/20/) · [Alembic](https://alembic.sqlalchemy.org/) ·
[Celery](https://docs.celeryq.dev/) · [Greenhouse API](https://docs.greenhouse.io/job-board)

[MIT license](LICENSE), copyright 2026 KOUSTUBH.
