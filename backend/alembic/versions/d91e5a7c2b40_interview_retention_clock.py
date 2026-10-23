"""Track the last durable interview update for retention.

Revision ID: d91e5a7c2b40
Revises: a7d4b9e2c103
"""

import sqlalchemy as sa

from alembic import op

revision = "d91e5a7c2b40"
down_revision = "a7d4b9e2c103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing interviews retain their most recent known activity/report timestamp. This
    # never deletes or rewrites interview content, and avoids expiring a recent report based
    # only on the session's original creation time.
    op.execute("""
        UPDATE interview_sessions AS s
        SET last_activity_at = GREATEST(
            s.created_at,
            COALESCE((SELECT MAX(a.created_at) FROM activity_events AS a
                      WHERE a.interview_id = s.id), s.created_at),
            COALESCE((SELECT r.created_at FROM interview_reports AS r
                      WHERE r.interview_id = s.id), s.created_at)
        )
    """)
    op.alter_column("interview_sessions", "last_activity_at", nullable=False)
    op.create_index(
        "ix_interview_sessions_last_activity_at", "interview_sessions", ["last_activity_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_interview_sessions_last_activity_at", table_name="interview_sessions")
    op.drop_column("interview_sessions", "last_activity_at")
