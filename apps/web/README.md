# Applyr web

The Applyr landing page and job feed. The feed is server-rendered and reads from
the FastAPI backend without exposing `API_TOKEN` to the browser.

## Run

Start the API from the repository root first:

```sh
cd apps/api
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then install and start the web app:

```sh
cd apps/web
pnpm install
pnpm dev
```

Open http://127.0.0.1:3000.

The web server reads `API_TOKEN` from the repository root `.env` automatically.
For a deployment without that file, provide `API_TOKEN` and optionally
`API_BASE_URL` through the environment. See `.env.example`.

## Routes

- `/` — landing page
- `/jobs` — filterable job feed
- `/jobs/[id]` — job detail and original-listing link
