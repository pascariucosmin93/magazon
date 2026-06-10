"""add user address book

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_addresses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("recipient_name", sa.String(length=120), nullable=False),
        sa.Column("line1", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=2), nullable=False, server_default="RO"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_addresses_id"), "user_addresses", ["id"])
    op.create_index(op.f("ix_user_addresses_user_id"), "user_addresses", ["user_id"])
    op.execute(
        """
        INSERT INTO user_addresses
            (user_id, label, recipient_name, line1, city, postal_code, country, is_default, created_at)
        SELECT
            id, 'Acasă', username, address, 'Nespecificat', '', 'RO', TRUE, CURRENT_TIMESTAMP
        FROM users
        WHERE address IS NOT NULL AND BTRIM(address) <> ''
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_addresses_user_id"), table_name="user_addresses")
    op.drop_index(op.f("ix_user_addresses_id"), table_name="user_addresses")
    op.drop_table("user_addresses")
