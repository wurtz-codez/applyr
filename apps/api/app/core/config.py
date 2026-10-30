from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_env: Literal["development", "test"] = "development"
    app_timezone: str = "Asia/Kolkata"
    api_token: SecretStr
    database_url: str
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    llm_provider: Literal["none", "gemini"] = "none"
    gemini_api_key: SecretStr | None = None
    llm_model: str = Field(default="", pattern=r"^[a-zA-Z0-9_.-]{0,150}$")
    ai_max_jobs_per_run: int = Field(default=5, ge=0, le=10)
    storage_dir: Path = ROOT / "storage"
    discovery_executor: Literal["local", "celery"] = "local"
    discovery_schedule_enabled: bool = False
    application_mode: Literal["approval"] = "approval"
    auto_submit_enabled: bool = False
    discovery_interval_hours: int = Field(default=6, ge=1, le=24)

    @field_validator("auto_submit_enabled")
    @classmethod
    def prohibit_auto_submission(cls, value: bool) -> bool:
        if value:
            raise ValueError("Automatic submission is not implemented and must remain disabled")
        return value

    @field_validator("api_token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if len(token) < 32 or token.startswith("replace_"):
            raise ValueError("API_TOKEN must be a generated secret of at least 32 characters")
        return value

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
