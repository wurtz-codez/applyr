from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    board_token: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    ats_provider: Literal["greenhouse"] = "greenhouse"


class CompanyResponse(CompanyInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    enabled: bool


class CompanyUpdate(BaseModel):
    enabled: bool


class DiscoverInput(BaseModel):
    use_ai: bool = True


class Components(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skills: int = Field(ge=0, le=100, strict=True)
    role: int = Field(ge=0, le=100, strict=True)
    experience: int = Field(ge=0, le=100, strict=True)
    projects: int = Field(ge=0, le=100, strict=True)


class AIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_skills: list[str] = Field(max_length=50)
    matched_profile_fact_ids: list[str] = Field(max_length=200)
    missing_skills: list[str] = Field(max_length=50)
    component_scores: Components
    confidence: Literal["low", "medium", "high"]
    reason: str = Field(min_length=1, max_length=2000)


class MatchResult(BaseModel):
    eligibility_status: Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_REVIEW"]
    eligibility_reasons: list[str]
    score: int | None = None
    component_scores: Components | None = None
    matched_profile_fact_ids: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    reason: str
    provider: str = "deterministic"
    model_id: str = "rules-v1"
    warning: str | None = None


class JobSummary(BaseModel):
    id: UUID
    company: str
    title: str
    location_text: str
    source_url: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    shortlisted: bool
    match: MatchResult | None
    needs_rematch: bool


class JobDetail(JobSummary):
    description_text: str
    evidence: list[dict]


class JobsResponse(BaseModel):
    items: list[JobSummary]
    total: int
    offset: int
    limit: int


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    agent_type: str
    status: str
    result_json: dict
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None


class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    original_filename: str
    size_bytes: int
    sha256: str
    version: int
    is_default: bool
    created_at: datetime


class SettingsSummary(BaseModel):
    llm_provider: str
    llm_model: str
    ai_configured: bool
    ai_max_jobs_per_run: int
    discovery_executor: str
    discovery_schedule_enabled: bool
    discovery_interval_hours: int
    resume_max_bytes: int


class DashboardStats(BaseModel):
    active_jobs: int
    eligible_jobs: int
    strong_matches: int
    new_today: int
    shortlisted: int
    profile_version: int | None
    latest_run: RunResponse | None
