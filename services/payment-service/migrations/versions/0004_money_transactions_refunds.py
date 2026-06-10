"""use numeric money and add payment transactions

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
    op.alter_column(
        "payments",
        "amount",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
        postgresql_using="ROUND(amount::numeric, 2)",
    )
    op.add_column("payments", sa.Column("payment_intent_id", sa.String(length=255), nullable=True))
    op.add_column(
        "payments",
        sa.Column(
            "refunded_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        op.f("ix_payments_payment_intent_id"),
        "payments",
        ["payment_intent_id"],
    )
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    op.create_index(op.f("ix_payment_transactions_id"), "payment_transactions", ["id"])
    op.create_index(
        op.f("ix_payment_transactions_payment_id"),
        "payment_transactions",
        ["payment_id"],
    )
    op.create_index(
        op.f("ix_payment_transactions_provider_event_id"),
        "payment_transactions",
        ["provider_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_transactions_provider_event_id"),
        table_name="payment_transactions",
    )
    op.drop_index(
        op.f("ix_payment_transactions_payment_id"),
        table_name="payment_transactions",
    )
    op.drop_index(op.f("ix_payment_transactions_id"), table_name="payment_transactions")
    op.drop_table("payment_transactions")
    op.drop_index(op.f("ix_payments_payment_intent_id"), table_name="payments")
    op.drop_column("payments", "refunded_amount")
    op.drop_column("payments", "payment_intent_id")
    op.alter_column(
        "payments",
        "amount",
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="amount::double precision",
    )
