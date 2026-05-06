"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_indexes(inspector, table: str, indexes: list[tuple[str, list[str]]]) -> None:
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    for name, columns in indexes:
        if name not in existing:
            op.create_index(name, table, columns)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "orders" not in tables:
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(50), nullable=False, server_default="created"),
            sa.Column("total", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_orders_id"), "orders", ["id"])
        op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])
    else:
        existing = {col["name"] for col in inspector.get_columns("orders")}
        if "status" not in existing:
            op.add_column("orders", sa.Column("status", sa.String(50), nullable=False, server_default="created"))
        if "total" not in existing:
            op.add_column("orders", sa.Column("total", sa.Float(), nullable=False, server_default="0"))
        _ensure_indexes(inspector, "orders", [
            (op.f("ix_orders_id"), ["id"]),
            (op.f("ix_orders_user_id"), ["user_id"]),
        ])

    if "order_items" not in tables:
        op.create_table(
            "order_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        existing = {col["name"] for col in inspector.get_columns("order_items")}
        if "product_id" not in existing:
            op.add_column("order_items", sa.Column("product_id", sa.Integer(), nullable=False, server_default="0"))
        if "quantity" not in existing:
            op.add_column("order_items", sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"))
        if "price" not in existing:
            op.add_column("order_items", sa.Column("price", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_id"), table_name="orders")
    op.drop_table("orders")
