"""add import jobs

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12 00:00:04.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "product_import_jobs" not in tables:
        op.create_table(
            "product_import_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("summary_json", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_product_import_jobs_id"), "product_import_jobs", ["id"])
        op.create_index(
            op.f("ix_product_import_jobs_created_at"),
            "product_import_jobs",
            ["created_at"],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_import_jobs_created_at"), table_name="product_import_jobs")
    op.drop_index(op.f("ix_product_import_jobs_id"), table_name="product_import_jobs")
    op.drop_table("product_import_jobs")
