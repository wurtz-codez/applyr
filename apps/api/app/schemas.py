from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UTCResponse(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def utc_datetimes(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


Provider = Literal["arbeitnow", "remotive", "jobicy", "tavily"]
WorkMode = Literal["REMOTE", "HYBRID", "ONSITE", "UNKNOWN"]
ListingType = Literal["JOB_POSTING", "SEARCH_RESULT"]


class JobData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    canonical_url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=500)
    description: str = Field(default="", max_length=100000)
    work_mode: WorkMode = "UNKNOWN"
    employment_type: str | None = Field(default=None, max_length=80)
    experience_level: str | None = Field(default=None, max_length=80)
    salary_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    salary_max: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: str | None = Field(default=None, max_length=20)
    salary_text: str | None = Field(default=None, max_length=500)
    listing_type: ListingType = "JOB_POSTING"
    enrichment_status: str = "NOT_NEEDED"
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    external_id: str | None = None
    source_url: str


class SourceRef(UTCResponse):
    provider: str
    source_url: str
    last_seen_at: datetime


class JobSummary(UTCResponse):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    canonical_url: str
    title: str
    company: str | None
    location: str | None
    description_excerpt: str
    work_mode: WorkMode
    employment_type: str | None
    experience_level: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    salary_text: str | None
    listing_type: ListingType
    enrichment_status: str
    primary_source: str
    published_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    tags: list[str]
    sources: list[SourceRef]


class JobResponse(JobSummary):
    description: str


class JobsPage(BaseModel):
    items: list[JobSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class DiscoveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=500)
    providers: list[Provider] | None = Field(default=None, min_length=1, max_length=4)


class SourceResult(UTCResponse):
    provider: Provider
    status: str
    fetched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    invalid: int = 0
    partial: bool = False
    enriched: int = 0
    error_code: str | None = None
    next_refresh_at: datetime | None = None


class RunResponse(UTCResponse):
    id: UUID
    status: str
    query: str
    providers: list[str]
    results: list[SourceResult]
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
