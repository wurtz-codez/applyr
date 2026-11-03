"""Index alternate ATS identities retained across source occurrences."""

import sqlalchemy as sa

from alembic import op

revision = "c32ef819"
down_revision = "b812c730"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_source_occurrences", sa.Column("ats_identity", sa.String(500)))
    op.execute("UPDATE job_source_occurrences SET ats_identity=metadata_json ->> 'ats_identity'")
    op.create_index(
        "ix_job_source_occurrences_ats_identity", "job_source_occurrences", ["ats_identity"]
    )


def downgrade():
    op.drop_index("ix_job_source_occurrences_ats_identity", "job_source_occurrences")
    op.drop_column("job_source_occurrences", "ats_identity")
