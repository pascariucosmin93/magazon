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

    if "inventory" not in tables:
        op.create_table(
            "inventory",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("product_id"),
        )
        op.create_index(op.f("ix_inventory_id"), "inventory", ["id"])
        op.create_index(op.f("ix_inventory_product_id"), "inventory", ["product_id"])
    else:
        existing = {col["name"] for col in inspector.get_columns("inventory")}
        if "stock" not in existing:
            op.add_column("inventory", sa.Column("stock", sa.Integer(), nullable=False, server_default="0"))
        if "updated_at" not in existing:
            op.add_column("inventory", sa.Column("updated_at", sa.DateTime(), nullable=True))
        _ensure_indexes(inspector, "inventory", [
            (op.f("ix_inventory_id"), ["id"]),
            (op.f("ix_inventory_product_id"), ["product_id"]),
        ])


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_product_id"), table_name="inventory")
    op.drop_index(op.f("ix_inventory_id"), table_name="inventory")
    op.drop_table("inventory")
