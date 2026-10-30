# Optional Docker workflow

Docker installation and execution are deferred. The default development workflow runs
Next.js and FastAPI on the host with SQLite (single process, no workers).

When Docker is available, copy `.env.compose.example` to `.env.compose`, generate fresh
credentials, and keep POSTGRES_PASSWORD consistent with the password in DATABASE_URL.
Hex passwords avoid URL escaping problems. Run from the repository root:

```sh
docker compose --env-file .env.compose -f infra/compose.yaml up -d --build
```

The migration service must succeed before the API and workers start. PostgreSQL and
Redis have no published host ports. The API binds to localhost:8000. Run `pnpm dev`
on the host and sign in using API_TOKEN from `.env.compose`. Run only one Beat instance.
Discovery schedules remain disabled until Phase 1 implements the discovery task.

Use PostgreSQL before concurrency or background workflows. SQLite data is local
prototype data; no automatic SQLite-to-PostgreSQL data transfer is provided.
