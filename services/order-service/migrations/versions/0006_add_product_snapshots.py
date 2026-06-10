"""add product snapshots to order items

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-10 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("product_name", sa.String(length=255), nullable=True))
    op.add_column("order_items", sa.Column("product_sku", sa.String(length=80), nullable=True))
    op.execute(
        """
        UPDATE order_items
        SET product_name = 'Produs #' || CAST(product_id AS VARCHAR),
            product_sku = 'PRODUCT-' || CAST(product_id AS VARCHAR)
        WHERE product_name IS NULL OR product_sku IS NULL
        """
    )
    op.alter_column(
        "order_items",
        "product_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "order_items",
        "product_sku",
        existing_type=sa.String(length=80),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("order_items", "product_sku")
    op.drop_column("order_items", "product_name")
