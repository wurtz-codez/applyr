# Optional Docker workflow

Docker installation and local execution are deferred. The current local app runs
Next.js and FastAPI on the host with SQLite; manual discovery needs no Redis.

When Docker is available, copy `.env.compose.example` to `.env.compose`, generate fresh
credentials, and keep POSTGRES_PASSWORD consistent with the password in DATABASE_URL.
Hex passwords avoid URL escaping problems. Add these variables for worker execution:

```dotenv
DISCOVERY_EXECUTOR=celery
DISCOVERY_SCHEDULE_ENABLED=true
DISCOVERY_INTERVAL_HOURS=6
LLM_PROVIDER=gemini
GEMINI_API_KEY=
LLM_MODEL=
AI_MAX_JOBS_PER_RUN=5
```

Keep the provider key and model blank for deterministic-only matching. Secrets stay in
`.env.compose`, which is ignored. Run from the repository root:

```sh
docker compose --env-file .env.compose -f infra/compose.yaml up -d --build
```

The migration service must succeed before the API and workers start. PostgreSQL and
Redis have no published host ports. The API binds to localhost:8000. Run `pnpm dev`
on the host and sign in with API_TOKEN from `.env.compose`. Run exactly one Beat instance.
Manual discovery is queued to Celery only when DISCOVERY_EXECUTOR=celery.

The `appstorage` volume is shared by API and workers and preserves original uploaded PDFs.
Do not remove volumes containing your data. Back up both PostgreSQL and the artifact volume.
SQLite development data is not automatically transferred to PostgreSQL.
