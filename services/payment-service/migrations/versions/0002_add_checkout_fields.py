"""add checkout fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {col["name"] for col in inspector.get_columns("payments")}

    if "currency" not in existing:
        op.add_column("payments", sa.Column("currency", sa.String(length=10), nullable=False, server_default="eur"))
    if "provider" not in existing:
        op.add_column("payments", sa.Column("provider", sa.String(length=50), nullable=False, server_default="stripe"))
    if "checkout_session_id" not in existing:
        op.add_column("payments", sa.Column("checkout_session_id", sa.String(length=255), nullable=True))
    if "checkout_url" not in existing:
        op.add_column("payments", sa.Column("checkout_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "checkout_url")
    op.drop_column("payments", "checkout_session_id")
    op.drop_column("payments", "provider")
    op.drop_column("payments", "currency")
