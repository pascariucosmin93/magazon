"""add product sku

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-10 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("sku", sa.String(length=80), nullable=True))
    op.execute(
        "UPDATE products SET sku = 'SKU-' || CAST(id AS VARCHAR) WHERE sku IS NULL"
    )
    op.alter_column("products", "sku", existing_type=sa.String(length=80), nullable=False)
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_column("products", "sku")
