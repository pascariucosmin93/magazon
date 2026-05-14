"""add processed messages

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "processed_messages" not in tables:
        op.create_table(
            "processed_messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("topic", sa.String(length=255), nullable=False),
            sa.Column("processed_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id"),
        )
        op.create_index(op.f("ix_processed_messages_id"), "processed_messages", ["id"])
        op.create_index(op.f("ix_processed_messages_event_id"), "processed_messages", ["event_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_processed_messages_event_id"), table_name="processed_messages")
    op.drop_index(op.f("ix_processed_messages_id"), table_name="processed_messages")
    op.drop_table("processed_messages")
