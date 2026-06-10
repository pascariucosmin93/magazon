"""use numeric money and add cancellation fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "orders",
        "total",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
        postgresql_using="ROUND(total::numeric, 2)",
    )
    op.alter_column(
        "order_items",
        "price",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
        postgresql_using="ROUND(price::numeric, 2)",
    )
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("cancellation_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "cancellation_reason")
    op.drop_column("orders", "cancelled_at")
    op.alter_column(
        "order_items",
        "price",
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="price::double precision",
    )
    op.alter_column(
        "orders",
        "total",
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="total::double precision",
    )
