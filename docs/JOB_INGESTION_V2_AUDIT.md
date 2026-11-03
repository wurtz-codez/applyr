# Job Ingestion v2: pre-change audit

Verified against the local PostgreSQL database on 2026-11-03, before implementation:

| Source | Job postings | Search-result pages |
| --- | ---: | ---: |
| Arbeitnow | 1,080 | 0 |
| Jobicy | 370 | 0 |
| Remotive | 12 | 0 |
| Tavily | 0 | 3 |

Total: 1,462 postings and 3 search pages. All 1,465 records have NULL
`india_eligible`. The database is at revision `c32ef819`. `job_sources` and
`ingestion_runs` are empty. Live smoke probes returned HTTP 200 with expected
payloads for all four ATS APIs. Baseline connector integration tests: 33 passed.

## Root causes

1. The registry is exclusively manual (`ingestion.service.register_source` and
   CLI `seed`). No registry ships with the application; Beat therefore has no
   sources to schedule.
2. Legacy feeds use `discovery.execute_run` and `store_jobs`, bypassing the
   connector normalizer entirely. Beat only schedules `job_sources`. Cooldowns
   in `source_states` reserve requests but do not initiate them.
3. Arbeitnow supplies primarily European jobs; remote feed availability is not
   evidence of India eligibility. No India-first default ranking is applied.
4. The normalizer stores only a nullable boolean, ignores description evidence,
   and has no evaluation version or background backfill.
5. Tavily results ARE already labelled `SEARCH_RESULT`; they are not confirmed
   job postings. Keep these distinct, out of matching and normal job results.
6. Dashboard refresh reads PostgreSQL. This is appropriate for a shared catalog;
   ingestion must be independently driven by Beat and workers.
7. All four ATS connectors exist; JobSpy and browser extraction are disabled by
   default. No existing AI matching integration was found: matching is an
   explicit deterministic baseline with a future reranking hook. Reuse it;
   do not introduce a mandatory LLM dependency.
8. `scripts/dev.py` starts only API and dashboard; Compose already includes
   Redis, worker, Beat, and an ordered migration service. Local startup needs
   worker/Beat management as well.

## Existing components retained

PostgreSQL/SQLAlchemy/Alembic, FastAPI, Celery/Redis/Beat, connector interface,
source row locks and leases, durable ingestion runs, HTTP pacing and bounded
retries, source occurrence provenance, conservative ATS/URL/requisition identity,
freshness reconciliation, per-profile shared-catalog matching, and frontend
filters/attribution. No restricted-platform scraping is required.

## Implementation verification

- Added registry: 71 enabled ATS boards with timestamped live HTTP 200 and India-location
  evidence, selected from 413 probed candidate configurations. No failed/empty candidates
  enter the enabled registry.
- Live keyless responses checked for all four ATS providers, Jobicy, and both Himalayas
  browse and India-filtered search. Himalayas country restrictions were observed as country
  name strings, in addition to the documented object representation supported by the parser.
- Backend: 98 tests passed against real dedicated PostgreSQL, including migration
  downgrade/upgrade/metadata checks and an embedded Celery worker. Ruff passes.
- Frontend: TypeScript check passes. Production build was attempted but could not fetch
  the existing IBM Plex Mono, Instrument Serif and Schibsted Grotesk Google Fonts in the
  network-restricted execution environment. No font/system-wide workaround was introduced.
- The configured live database and already-running worker/Beat processes were not replaced
  during verification. Restart upgraded API, worker and Beat to apply the migration, seed
  sources and run the automated backfill. All integration-test writes used `applyr_test`.
