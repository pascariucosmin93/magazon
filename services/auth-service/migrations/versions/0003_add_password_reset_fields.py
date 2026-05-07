"""add password reset fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}

    if "reset_token_hash" not in existing_columns:
        op.add_column("users", sa.Column("reset_token_hash", sa.String(length=64), nullable=True))
    if "reset_token_expires_at" not in existing_columns:
        op.add_column("users", sa.Column("reset_token_expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("users")}

    if "reset_token_expires_at" in existing_columns:
        op.drop_column("users", "reset_token_expires_at")
    if "reset_token_hash" in existing_columns:
        op.drop_column("users", "reset_token_hash")
