"""Profile-specific deterministic matching stays separate from the global catalog."""

import sqlalchemy as sa

from alembic import op

revision = "b812c730"
down_revision = "f19d7a21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "matching_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_key", sa.String(200), nullable=False, unique=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("needs_refresh", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_matching_profiles_needs_refresh", "matching_profiles", ["needs_refresh"])
    op.create_table(
        "job_matches",
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("matching_profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_matches_score", "job_matches", ["score"])


def downgrade():
    op.drop_table("job_matches")
    op.drop_table("matching_profiles")
