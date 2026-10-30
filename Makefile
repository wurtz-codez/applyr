export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv

UV := $(if $(wildcard .tools/python/bin/uv),$(abspath .tools/python/bin/uv),uv)

.PHONY: install dev refresh jobs check

install:
	$(UV) sync --project apps/api --frozen

dev:
	$(UV) run --project apps/api --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir apps/api/app

refresh:
	$(UV) run --project apps/api --frozen python -m app.cli refresh

jobs:
	$(UV) run --project apps/api --frozen python -m app.cli jobs

check:
	$(UV) run --project apps/api --frozen ruff check apps/api
	$(UV) run --project apps/api --frozen pytest apps/api/tests -q
	cd apps/api && $(UV) run --frozen alembic check
