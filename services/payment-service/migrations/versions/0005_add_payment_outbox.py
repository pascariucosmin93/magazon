"""add payment outbox

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-10 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_outbox_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        op.f("ix_payment_outbox_events_id"),
        "payment_outbox_events",
        ["id"],
    )
    op.create_index(
        op.f("ix_payment_outbox_events_event_id"),
        "payment_outbox_events",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_outbox_events_event_id"),
        table_name="payment_outbox_events",
    )
    op.drop_index(
        op.f("ix_payment_outbox_events_id"),
        table_name="payment_outbox_events",
    )
    op.drop_table("payment_outbox_events")
