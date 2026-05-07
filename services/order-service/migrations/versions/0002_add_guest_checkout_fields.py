"""add guest checkout fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = _column_names(inspector, "orders")

    if "customer_name" not in columns:
        op.add_column("orders", sa.Column("customer_name", sa.String(length=120), nullable=True))
    if "customer_email" not in columns:
        op.add_column("orders", sa.Column("customer_email", sa.String(length=255), nullable=True))
    if "shipping_address" not in columns:
        op.add_column("orders", sa.Column("shipping_address", sa.String(length=255), nullable=True))
    if "guest_token" not in columns:
        op.add_column("orders", sa.Column("guest_token", sa.String(length=120), nullable=True))

    op.alter_column("orders", "user_id", existing_type=sa.Integer(), nullable=True)

    indexes = {index["name"] for index in inspector.get_indexes("orders")}
    guest_index = op.f("ix_orders_guest_token")
    if guest_index not in indexes:
        op.create_index(guest_index, "orders", ["guest_token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_guest_token"), table_name="orders")
    op.alter_column("orders", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("orders", "guest_token")
    op.drop_column("orders", "shipping_address")
    op.drop_column("orders", "customer_email")
    op.drop_column("orders", "customer_name")
