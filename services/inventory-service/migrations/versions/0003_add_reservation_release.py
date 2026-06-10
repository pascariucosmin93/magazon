"""add inventory reservations and release timestamp

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-10 00:00:00.000000
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
    if "inventory_reservations" not in inspector.get_table_names():
        op.create_table(
            "inventory_reservations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_id"),
        )
        op.create_index(op.f("ix_inventory_reservations_id"), "inventory_reservations", ["id"])
        op.create_index(op.f("ix_inventory_reservations_order_id"), "inventory_reservations", ["order_id"])
        return

    existing = {column["name"] for column in inspector.get_columns("inventory_reservations")}
    if "released_at" not in existing:
        op.add_column("inventory_reservations", sa.Column("released_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "inventory_reservations" in inspector.get_table_names():
        op.drop_table("inventory_reservations")
