import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
RENDER_ENV_MARKERS = ("RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )
    api_token: SecretStr
    jobs_database_url: str = "postgresql+psycopg://localhost/applyr"
    tavily_api_key: SecretStr | None = None
    search_results_per_query: int = Field(default=10, ge=1, le=20)
    max_search_requests_per_day: int = Field(default=10, ge=1, le=100)
    default_search_query: str = Field(default="software engineer jobs India", max_length=500)
    enrich_web_results: bool = True

    @field_validator("api_token")
    @classmethod
    def strong_token(cls, value):
        if len(value.get_secret_value()) < 32 or value.get_secret_value().startswith("replace_"):
            raise ValueError("Generate an API_TOKEN with at least 32 characters")
        return value

    @field_validator("jobs_database_url")
    @classmethod
    def postgresql_driver(cls, value):
        value = value.strip()
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
        if not value.startswith("postgresql"):
            raise ValueError("JOBS_DATABASE_URL must be a PostgreSQL URL.")
        return value

    @model_validator(mode="after")
    def render_database(self):
        on_render = any(os.environ.get(marker) for marker in RENDER_ENV_MARKERS)
        if on_render:
            host = urlsplit(self.jobs_database_url).hostname
            if host in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError(
                    "Set JOBS_DATABASE_URL to the Internal Database URL from Render PostgreSQL. "
                    "Render's filesystem is ephemeral and localhost is not reachable."
                )
        return self


@lru_cache
def get_settings():
    return Settings()
