"""merge legacy English categories

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-10 00:00:02.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_CATEGORIES = {
    "Accessories": (
        "Accesorii",
        "Dock-uri, cabluri, suporturi și accesorii pentru birou",
    ),
    "Keyboards": (
        "Periferice",
        "Tastaturi, mouse-uri, căști și camere web",
    ),
    "Mice": (
        "Periferice",
        "Tastaturi, mouse-uri, căști și camere web",
    ),
}


def upgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    categories = sa.Table("categories", metadata, autoload_with=connection)
    products = sa.Table("products", metadata, autoload_with=connection)

    for legacy_name, (canonical_name, canonical_description) in LEGACY_CATEGORIES.items():
        legacy = connection.execute(
            sa.select(categories.c.id).where(categories.c.name == legacy_name)
        ).first()
        if legacy is None:
            continue

        canonical = connection.execute(
            sa.select(categories.c.id).where(categories.c.name == canonical_name)
        ).first()
        if canonical is None:
            connection.execute(
                categories.update()
                .where(categories.c.id == legacy.id)
                .values(name=canonical_name, description=canonical_description)
            )
            continue

        connection.execute(
            products.update()
            .where(products.c.category_id == legacy.id)
            .values(category_id=canonical.id)
        )
        connection.execute(categories.delete().where(categories.c.id == legacy.id))


def downgrade() -> None:
    # Merging categories is intentionally irreversible because the original
    # product-to-category split cannot be reconstructed reliably.
    pass
