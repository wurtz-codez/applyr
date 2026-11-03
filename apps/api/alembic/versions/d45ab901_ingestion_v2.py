"""India eligibility evidence, seed ownership, verification and durable maintenance."""

import sqlalchemy as sa

from alembic import op

revision = "d45ab901"
down_revision = "c32ef819"
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column("india_status", sa.String(20), nullable=False, server_default="UNCERTAIN"),
        sa.Column("eligibility_reason", sa.String(200)),
        sa.Column("eligibility_evidence", sa.JSON()),
        sa.Column("eligibility_evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("eligibility_method", sa.String(80)),
        sa.Column("eligibility_confidence", sa.Float()),
        sa.Column("normalization_version", sa.Integer(), nullable=False, server_default="0"),
    ]
    for column in columns:
        op.add_column("jobs", column)
    for field in ("india_status", "normalization_version"):
        op.create_index(f"ix_jobs_{field}", "jobs", [field])
    op.create_check_constraint(
        "ck_jobs_india_status", "jobs", "india_status IN ('CONFIRMED', 'NOT_ELIGIBLE', 'UNCERTAIN')"
    )
    op.add_column("job_sources", sa.Column("seed_defaults", sa.JSON()))
    op.add_column(
        "job_sources", sa.Column("local_overrides", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "job_source_occurrences", sa.Column("last_verified_at", sa.DateTime(timezone=True))
    )
    op.create_table(
        "ingestion_maintenance",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("ingestion_maintenance")
    op.drop_column("job_source_occurrences", "last_verified_at")
    op.drop_column("job_sources", "local_overrides")
    op.drop_column("job_sources", "seed_defaults")
    op.drop_constraint("ck_jobs_india_status", "jobs", type_="check")
    for field in ("india_status", "normalization_version"):
        op.drop_index(f"ix_jobs_{field}", "jobs")
    for field in (
        "india_status",
        "eligibility_reason",
        "eligibility_evidence",
        "eligibility_evaluated_at",
        "eligibility_method",
        "eligibility_confidence",
        "normalization_version",
    ):
        op.drop_column("jobs", field)
