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


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=100), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password", sa.String(255), nullable=False),
            sa.Column("address", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("role", sa.String(50), nullable=False, server_default="customer"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
            sa.UniqueConstraint("email"),
        )
        op.create_index(op.f("ix_users_id"), "users", ["id"])
        op.create_index(op.f("ix_users_username"), "users", ["username"])
        op.create_index(op.f("ix_users_email"), "users", ["email"])
    else:
        # Table existed before Alembic — add any missing columns
        existing = {col["name"] for col in inspector.get_columns("users")}
        if "username" not in existing:
            op.add_column("users", sa.Column("username", sa.String(length=100), nullable=True))
            op.execute("UPDATE users SET username = email WHERE username IS NULL")
            op.alter_column("users", "username", nullable=False)
            op.create_unique_constraint("uq_users_username", "users", ["username"])
        if "address" not in existing:
            op.add_column("users", sa.Column("address", sa.String(length=255), nullable=False, server_default=""))
        if "role" not in existing:
            op.add_column("users", sa.Column("role", sa.String(50), nullable=False, server_default="customer"))
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
        if "ix_users_id" not in existing_indexes:
            op.create_index(op.f("ix_users_id"), "users", ["id"])
        if "ix_users_username" not in existing_indexes:
            op.create_index(op.f("ix_users_username"), "users", ["username"])
        if "ix_users_email" not in existing_indexes:
            op.create_index(op.f("ix_users_email"), "users", ["email"])


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
