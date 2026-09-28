"""Persist accepted interview evidence and the pending turn.

Revision ID: f3a821d9c604
Revises: c6505f42e5f3
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f3a821d9c604"
down_revision = "c6505f42e5f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable for pre-existing sessions whose evidence may already be unavailable.
    # Never fabricate completion or an active turn for those rows.
    op.add_column(
        "interview_sessions",
        sa.Column(
            "runtime_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "runtime_snapshot")
