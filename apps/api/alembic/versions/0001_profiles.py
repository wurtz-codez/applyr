"""Local user and verified profile foundation."""
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    users = op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("preferences_json", json_type, nullable=False),
        sa.Column("facts_json", json_type, nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.bulk_insert(users, [{
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "email": "local@localhost", "created_at": datetime.now(UTC),
    }])


def downgrade():
    op.drop_table("profiles")
    op.drop_table("users")
