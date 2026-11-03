from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.normalization import canonical_url


class Location(BaseModel):
    label: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    city: str | None = Field(default=None, max_length=200)
    remote_type: Literal["remote", "hybrid", "onsite", "unknown"] = "unknown"
    eligible_countries: list[str] | None = None
    globally_remote: bool | None = None
    india_eligible: bool | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: str | None = None


class Experience(BaseModel):
    min_years: int | None = Field(default=None, ge=0, le=100)
    max_years: int | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: str | None = None


class NormalizedJob(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: str
    external_id: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=100000)
    location: Location = Field(default_factory=Location)
    additional_locations: list[Location] = Field(default_factory=list)
    employment_type: str | None = Field(default=None, max_length=80)
    experience: Experience = Field(default_factory=Experience)
    skills: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100
    )
    job_url: str = Field(max_length=2000)
    apply_url: str | None = Field(default=None, max_length=2000)
    salary_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    salary_max: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: str | None = Field(default=None, max_length=20)
    salary_text: str | None = Field(default=None, max_length=500)
    experience_level: str | None = Field(default=None, max_length=80)
    requisition_id: str | None = Field(default=None, max_length=200)
    posted_at: datetime | None = None
    valid_through: datetime | None = None
    status: Literal["active", "closed"] = "active"
    raw: dict | None = None
    source_fields: list[str] = Field(default_factory=list)
    derived: dict = Field(default_factory=dict)

    @field_validator("job_url", "apply_url")
    @classmethod
    def public_urls(cls, value):
        if value is not None:
            canonical_url(value)
        return value  # Keep original URLs; canonicalize only identity keys.


class SourceConfig(BaseModel):
    provider: str
    board_id: str
    company: str
    career_url: str | None = None
    configuration: dict = Field(default_factory=dict)
    state: dict = Field(default_factory=dict)


class FetchError(BaseModel):
    code: str
    recoverable: bool = True
    external_id: str | None = None
    retry_after: float | None = None


class FetchResult(BaseModel):
    jobs: list[NormalizedJob] = Field(default_factory=list)
    next_cursor: str | None = None
    metadata: dict = Field(default_factory=dict)
    statistics: dict = Field(default_factory=dict)
    errors: list[FetchError] = Field(default_factory=list)
    not_modified: bool = False
    complete_snapshot: bool = False


class JobConnector(Protocol):
    async def fetch_jobs(
        self, configuration: SourceConfig, cursor: str | None = None
    ) -> FetchResult: ...


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company_name: str = Field(min_length=1, max_length=300)
    website: str | None = Field(default=None, max_length=2000)
    career_url: str | None = Field(default=None, max_length=2000)
    provider: str = Field(default="auto", max_length=30)
    board_id: str | None = Field(default=None, max_length=200)
    configuration: dict = Field(default_factory=dict)
    enabled: bool = True
    access_policy: Literal["public_api", "permitted", "pending", "denied"] = "pending"
    permission_notes: str | None = Field(default=None, max_length=4000)
    fetch_interval_seconds: int = Field(default=21600, ge=3600, le=2592000)

    @field_validator("website", "career_url")
    @classmethod
    def url(cls, value):
        return canonical_url(value) if value else None

    @model_validator(mode="after")
    def bounded_configuration(self):
        import json

        if len(json.dumps(self.configuration)) > 32000:
            raise ValueError("Source configuration exceeds 32KB")
        return self


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: bool | None = None
    access_policy: Literal["public_api", "permitted", "pending", "denied"] | None = None
    permission_notes: str | None = Field(default=None, max_length=4000)
    fetch_interval_seconds: int | None = Field(default=None, ge=3600, le=2592000)
