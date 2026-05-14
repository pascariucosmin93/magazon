"""add outbox events

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "outbox_events" not in tables:
        op.create_table(
            "outbox_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("topic", sa.String(length=255), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_outbox_events_id"), "outbox_events", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_outbox_events_id"), table_name="outbox_events")
    op.drop_table("outbox_events")
