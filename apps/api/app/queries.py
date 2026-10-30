import math
from datetime import timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select

from app.models import Job, JobSource, JobTag, now
from app.schemas import JobResponse, JobsPage, JobSummary, Provider, SourceRef, WorkMode


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=200)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    work_mode: WorkMode | None = None
    employment_type: str | None = Field(default=None, max_length=80)
    experience_level: str | None = Field(default=None, max_length=80)
    listing_type: Literal["JOB_POSTING", "SEARCH_RESULT"] | None = None
    source: list[Provider] = Field(default_factory=list, max_length=4)
    tag: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=10
    )
    posted_within_days: int | None = Field(default=None, ge=1, le=3650)
    seen_within_days: int | None = Field(default=None, ge=1, le=3650)
    min_salary: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: Literal["hourly", "daily", "weekly", "monthly", "yearly"] | None = None
    sort: Literal["newest", "oldest", "salary_desc", "title"] = "newest"
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def salary_units(self):
        if (self.min_salary is not None or self.sort == "salary_desc") and not (
            self.currency and self.salary_period
        ):
            raise ValueError("Salary filtering/sorting requires currency and salary_period")
        return self


def pattern(value):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def filtered(filters: Filters):
    query = select(Job)
    if filters.q:
        term = pattern(filters.q)
        query = query.where(
            or_(
                Job.title.ilike(term, escape="\\"),
                Job.company.ilike(term, escape="\\"),
                Job.description.ilike(term, escape="\\"),
            )
        )
    if filters.company:
        query = query.where(func.lower(Job.company) == filters.company.lower())
    if filters.location:
        query = query.where(Job.location.ilike(pattern(filters.location), escape="\\"))
    for name in ["work_mode", "listing_type", "currency", "salary_period"]:
        value = getattr(filters, name)
        if value:
            column = Job.salary_currency if name == "currency" else getattr(Job, name)
            query = query.where(column == value)
    for name in ["employment_type", "experience_level"]:
        value = getattr(filters, name)
        if value:
            query = query.where(func.lower(getattr(Job, name)) == value.lower())
    if filters.source:
        query = query.where(
            select(JobSource.id)
            .where(JobSource.job_id == Job.id, JobSource.provider.in_(filters.source))
            .exists()
        )
    for tag in set(filters.tag):
        query = query.where(
            select(JobTag.job_id)
            .where(JobTag.job_id == Job.id, JobTag.tag == tag.strip().casefold())
            .exists()
        )
    if filters.posted_within_days:
        query = query.where(Job.published_at >= now() - timedelta(days=filters.posted_within_days))
    if filters.seen_within_days:
        query = query.where(Job.last_seen_at >= now() - timedelta(days=filters.seen_within_days))
    if filters.min_salary is not None:
        query = query.where(Job.salary_min >= filters.min_salary)
    return query


def total(session, query):
    return session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def serialize_many(session, rows, detail=False):
    ids = [row.id for row in rows]
    tags, sources = {}, {}
    if ids:
        for item in session.scalars(
            select(JobTag).where(JobTag.job_id.in_(ids)).order_by(JobTag.tag)
        ):
            tags.setdefault(item.job_id, []).append(item.tag)
        for item in session.scalars(
            select(JobSource).where(JobSource.job_id.in_(ids)).order_by(JobSource.provider)
        ):
            sources.setdefault(item.job_id, []).append(
                SourceRef(
                    provider=item.provider,
                    source_url=item.source_url,
                    last_seen_at=item.last_seen_at,
                )
            )
    result = []
    schema = JobResponse if detail else JobSummary
    fields = set(schema.model_fields) - {"tags", "sources", "description_excerpt"}
    for row in rows:
        values = {name: getattr(row, name) for name in fields}
        result.append(
            schema(
                **values,
                description_excerpt=row.description[:400],
                tags=tags.get(row.id, []),
                sources=sources.get(row.id, []),
            )
        )
    return result


def list_jobs(session, filters):
    query = filtered(filters)
    count = total(session, query)
    posted = func.coalesce(Job.published_at, Job.first_seen_at)
    order = {
        "newest": posted.desc(),
        "oldest": posted.asc(),
        "title": func.lower(Job.title).asc(),
        "salary_desc": func.coalesce(Job.salary_max, Job.salary_min).desc().nulls_last(),
    }[filters.sort]
    rows = session.scalars(
        query.order_by(order, Job.id)
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    return JobsPage(
        items=serialize_many(session, rows),
        total=count,
        page=filters.page,
        page_size=filters.page_size,
        total_pages=math.ceil(count / filters.page_size),
    )


def facets(session, filters):
    ids = filtered(filters).with_only_columns(Job.id).subquery()
    result = {}
    for name in [
        "company",
        "location",
        "work_mode",
        "employment_type",
        "experience_level",
        "salary_currency",
        "salary_period",
        "listing_type",
    ]:
        column = getattr(Job, name)
        rows = session.execute(
            select(column, func.count())
            .where(Job.id.in_(select(ids.c.id)), column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc(), column)
        )
        result[name] = [{"value": value, "count": count} for value, count in rows]
    for name, model, column in [
        ("tags", JobTag, JobTag.tag),
        ("sources", JobSource, JobSource.provider),
    ]:
        rows = session.execute(
            select(column, func.count())
            .where(model.job_id.in_(select(ids.c.id)))
            .group_by(column)
            .order_by(func.count().desc(), column)
            .limit(200)
        )
        result[name] = [{"value": value, "count": count} for value, count in rows]
    return result
