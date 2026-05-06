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

    if "payments" not in tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_payments_id"), "payments", ["id"])
        op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"])
    else:
        existing = {col["name"] for col in inspector.get_columns("payments")}
        if "order_id" not in existing:
            op.add_column("payments", sa.Column("order_id", sa.Integer(), nullable=False, server_default="0"))
        if "amount" not in existing:
            op.add_column("payments", sa.Column("amount", sa.Float(), nullable=False, server_default="0"))
        if "status" not in existing:
            op.add_column("payments", sa.Column("status", sa.String(50), nullable=False, server_default="completed"))
        if "created_at" not in existing:
            op.add_column("payments", sa.Column("created_at", sa.DateTime(), nullable=True))
        _ensure_indexes(
            inspector,
            "payments",
            [
                (op.f("ix_payments_id"), ["id"]),
                (op.f("ix_payments_order_id"), ["order_id"]),
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_id"), table_name="payments")
    op.drop_table("payments")
