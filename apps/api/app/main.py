import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.v1.router import router
from app.core.config import get_settings


async def local_scheduler():
    from app.services.discovery import scheduled_discovery

    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(scheduled_discovery)
        except Exception:
            logging.getLogger(__name__).error("Scheduled discovery failed; retrying next check")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    task = None
    if settings.discovery_executor == "local" and settings.discovery_schedule_enabled:
        task = asyncio.create_task(local_scheduler())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(
        title="JobPilot AI",
        version="0.2.0",
        description="Job discovery, evidence-based matching and resume uploads",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Liveness only; does not imply database or broker readiness.
        return {"status": "ok"}

    return app


app = create_app()
