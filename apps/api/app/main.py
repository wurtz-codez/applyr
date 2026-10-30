from fastapi import FastAPI

from app.api.v1.router import router
from app.core.config import get_settings


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(title="JobPilot AI", version="0.1.0", description="Phase 0 foundation API")
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Liveness only; does not imply database or broker readiness.
        return {"status": "ok"}

    return app


app = create_app()
