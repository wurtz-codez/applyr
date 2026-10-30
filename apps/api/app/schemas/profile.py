from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=80)
    category: Literal["skill", "project", "experience", "education"]
    statement: str = Field(min_length=1, max_length=2000)
    evidence_source: str = Field(min_length=1, max_length=500)
    is_verified: Literal[True]


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[str] = Field(
        default_factory=lambda: ["Software Engineer", "Backend Engineer", "Full Stack Developer"],
        min_length=1, max_length=20,
    )
    country_codes: list[Literal["IN"]] = Field(default_factory=lambda: ["IN"], min_length=1)
    max_experience_years: int = Field(default=2, ge=0, le=2)
    india_eligible_remote: bool = True
    internships: bool = False


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str = Field(min_length=1, max_length=200)
    preferences: Preferences = Field(default_factory=Preferences)
    facts: list[Fact] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_fact_ids(self):
        if len({fact.id for fact in self.facts}) != len(self.facts):
            raise ValueError("Fact IDs must be unique")
        return self


class ProfileResponse(ProfileInput):
    id: UUID
    current_version: int
    updated_at: datetime
