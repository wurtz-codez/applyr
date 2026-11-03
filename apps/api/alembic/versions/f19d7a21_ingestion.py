"""Persistent source registry and global catalog provenance; preserve legacy occurrences."""

import sqlalchemy as sa

from alembic import op

revision = "f19d7a21"
down_revision = "dda5755cd4ae"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("job_sources", "job_source_occurrences")
    op.drop_constraint("uq_job_sources_job_id", "job_source_occurrences", type_="unique")
    op.execute(
        "ALTER TABLE job_source_occurrences RENAME CONSTRAINT "
        "pk_job_sources TO pk_job_source_occurrences"
    )
    op.execute(
        "ALTER TABLE job_source_occurrences RENAME CONSTRAINT "
        "fk_job_sources_job_id_jobs TO fk_job_source_occurrences_job_id_jobs"
    )
    for column in ("job_id", "provider"):
        op.execute(
            f"ALTER INDEX ix_job_sources_{column} RENAME TO ix_job_source_occurrences_{column}"
        )
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("website", sa.String(2000), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("company_name", sa.String(300), nullable=False),
        sa.Column("career_url", sa.String(2000)),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("board_id", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("access_policy", sa.String(30), nullable=False),
        sa.Column("permission_notes", sa.Text()),
        sa.Column("fetch_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_fetch_at", sa.DateTime(timezone=True)),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("health", sa.String(30), nullable=False),
        sa.Column("sync_state", sa.JSON(), nullable=False),
        sa.Column("active_run_id", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "board_id"),
    )
    for column in ("company_id", "provider", "next_fetch_at"):
        op.create_index(f"ix_job_sources_{column}", "job_sources", [column])
    for column in [
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id")),
        sa.Column("apply_url", sa.String(2000)),
        sa.Column("original_job_url", sa.String(2000)),
        sa.Column("normalized_json", sa.JSON()),
        sa.Column("experience_min", sa.Integer()),
        sa.Column("experience_max", sa.Integer()),
        sa.Column("india_eligible", sa.Boolean()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("valid_through", sa.DateTime(timezone=True)),
        sa.Column("ats_identity", sa.String(500)),
        sa.Column("requisition_id", sa.String(200)),
    ]:
        op.add_column("jobs", column)
    for column in ("company_id", "apply_url", "experience_min", "india_eligible", "requisition_id"):
        op.create_index(f"ix_jobs_{column}", "jobs", [column])
    op.create_unique_constraint("uq_jobs_ats_identity", "jobs", ["ats_identity"])
    for column in [
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("job_sources.id")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("raw_json", sa.JSON()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    ]:
        op.add_column("job_source_occurrences", column)
    op.execute("UPDATE job_source_occurrences SET first_seen_at=last_seen_at")
    op.alter_column("job_source_occurrences", "first_seen_at", nullable=False)
    op.alter_column("job_source_occurrences", "active", server_default=None)
    op.create_unique_constraint(
        "uq_job_source_occurrences_source_id",
        "job_source_occurrences",
        ["source_id", "external_id"],
    )
    op.create_index("ix_job_source_occurrences_source_id", "job_source_occurrences", ["source_id"])
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("job_sources.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *[
            sa.Column(c, sa.Integer(), nullable=False)
            for c in ("fetched", "inserted", "updated", "deduplicated", "failed")
        ],
        sa.Column("errors", sa.JSON(), nullable=False),
    )
    for column in ("source_id", "status"):
        op.create_index(f"ix_ingestion_runs_{column}", "ingestion_runs", [column])


def downgrade():
    op.drop_table("ingestion_runs")
    op.drop_constraint(
        "uq_job_source_occurrences_source_id", "job_source_occurrences", type_="unique"
    )
    op.drop_index("ix_job_source_occurrences_source_id", "job_source_occurrences")
    for column in ("source_id", "first_seen_at", "metadata_json", "raw_json", "active"):
        op.drop_column("job_source_occurrences", column)
    for column in ("company_id", "apply_url", "experience_min", "india_eligible", "requisition_id"):
        op.drop_index(f"ix_jobs_{column}", "jobs")
    op.drop_constraint("uq_jobs_ats_identity", "jobs", type_="unique")
    for column in (
        "company_id",
        "apply_url",
        "original_job_url",
        "normalized_json",
        "experience_min",
        "experience_max",
        "india_eligible",
        "status",
        "valid_through",
        "ats_identity",
        "requisition_id",
    ):
        op.drop_column("jobs", column)
    op.drop_table("job_sources")
    op.drop_table("companies")
    # A legacy schema can retain only one occurrence per job/provider.
    op.execute(
        "DELETE FROM job_source_occurrences a USING job_source_occurrences b "
        "WHERE a.job_id=b.job_id AND a.provider=b.provider AND a.id>b.id"
    )
    op.execute(
        "ALTER TABLE job_source_occurrences RENAME CONSTRAINT "
        "pk_job_source_occurrences TO pk_job_sources"
    )
    op.execute(
        "ALTER TABLE job_source_occurrences RENAME CONSTRAINT "
        "fk_job_source_occurrences_job_id_jobs TO fk_job_sources_job_id_jobs"
    )
    for column in ("job_id", "provider"):
        op.execute(
            f"ALTER INDEX ix_job_source_occurrences_{column} RENAME TO ix_job_sources_{column}"
        )
    op.rename_table("job_source_occurrences", "job_sources")
    op.create_unique_constraint("uq_job_sources_job_id", "job_sources", ["job_id", "provider"])
