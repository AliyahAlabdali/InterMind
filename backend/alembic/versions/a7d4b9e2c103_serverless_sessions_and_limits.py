"""Add durable recruiter sessions and rolling-window admission events.

Revision ID: a7d4b9e2c103
Revises: f3a821d9c604
"""

import sqlalchemy as sa

from alembic import op

revision = "a7d4b9e2c103"
down_revision = "f3a821d9c604"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recruiter_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("recruiter_id", sa.String(32), sa.ForeignKey("recruiters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recruiter_sessions_recruiter_id", "recruiter_sessions", ["recruiter_id"])
    op.create_index("ix_recruiter_sessions_expires_at", "recruiter_sessions", ["expires_at"])
    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bucket", sa.String(64), nullable=False),
        sa.Column("identity", sa.String(64), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limit_events_lookup", "rate_limit_events", ["bucket", "identity", "window_seconds", "admitted_at"])
    op.create_index("ix_rate_limit_events_expiry", "rate_limit_events", ["admitted_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_events_expiry", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_lookup", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
    op.drop_index("ix_recruiter_sessions_expires_at", table_name="recruiter_sessions")
    op.drop_index("ix_recruiter_sessions_recruiter_id", table_name="recruiter_sessions")
    op.drop_table("recruiter_sessions")
