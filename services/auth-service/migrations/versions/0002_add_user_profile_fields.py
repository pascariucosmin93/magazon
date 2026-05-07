"""add username and address to users

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    existing_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("users")
        if constraint.get("name")
    }

    if "username" not in existing_columns:
        op.add_column("users", sa.Column("username", sa.String(length=100), nullable=True))
        op.execute("UPDATE users SET username = email WHERE username IS NULL")
        op.alter_column("users", "username", nullable=False)

    if "address" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("address", sa.String(length=255), nullable=False, server_default=""),
        )

    if "uq_users_username" not in existing_unique_constraints:
        op.create_unique_constraint("uq_users_username", "users", ["username"])

    if "ix_users_username" not in existing_indexes:
        op.create_index(op.f("ix_users_username"), "users", ["username"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
    existing_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("users")
        if constraint.get("name")
    }

    if "ix_users_username" in existing_indexes:
        op.drop_index(op.f("ix_users_username"), table_name="users")

    if "uq_users_username" in existing_unique_constraints:
        op.drop_constraint("uq_users_username", "users", type_="unique")

    if "address" in existing_columns:
        op.drop_column("users", "address")

    if "username" in existing_columns:
        op.drop_column("users", "username")
