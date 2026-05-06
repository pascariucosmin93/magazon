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

    if "categories" not in tables:
        op.create_table(
            "categories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index(op.f("ix_categories_id"), "categories", ["id"])
        op.create_index(op.f("ix_categories_name"), "categories", ["name"])
    else:
        existing = {col["name"] for col in inspector.get_columns("categories")}
        if "description" not in existing:
            op.add_column("categories", sa.Column("description", sa.Text(), nullable=False, server_default=""))
        _ensure_indexes(inspector, "categories", [
            (op.f("ix_categories_id"), ["id"]),
            (op.f("ix_categories_name"), ["name"]),
        ])

    if "products" not in tables:
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_products_id"), "products", ["id"])
    else:
        existing = {col["name"] for col in inspector.get_columns("products")}
        if "category_id" not in existing:
            op.add_column("products", sa.Column("category_id", sa.Integer(), nullable=True))
        _ensure_indexes(inspector, "products", [
            (op.f("ix_products_id"), ["id"]),
        ])


def downgrade() -> None:
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_categories_name"), table_name="categories")
    op.drop_index(op.f("ix_categories_id"), table_name="categories")
    op.drop_table("categories")
