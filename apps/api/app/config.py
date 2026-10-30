from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )
    api_token: SecretStr
    jobs_database_url: str = f"sqlite:///{ROOT / 'storage' / 'jobs.sqlite3'}"
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


@lru_cache
def get_settings():
    return Settings()
