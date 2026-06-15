import os
import sys
from pathlib import Path

import requests
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    for module_name in (
        "product_import",
        "product_models",
        "product_routes",
        "product_schemas",
        "product_serializers",
    ):
        sys.modules.pop(module_name, None)

import product_import as product_import_module  # noqa: E402
import product_models as product_models_module  # noqa: E402
import product_routes as product_routes_module  # noqa: E402
import product_schemas as product_schemas_module  # noqa: E402
import product_serializers as product_serializers_module  # noqa: E402
from shared.config import settings  # noqa: E402
from shared.db import Base, SessionLocal  # noqa: E402
from shared.redis_client import redis_client  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

CATEGORY_ALIASES = product_import_module.CATEGORY_ALIASES
IMPORT_HEADER_ALIASES = product_import_module.IMPORT_HEADER_ALIASES
IMPORT_REQUIRED_HEADERS = product_import_module.IMPORT_REQUIRED_HEADERS
INVENTORY_SERVICE_URL = product_import_module.INVENTORY_SERVICE_URL
PRODUCT_CACHE_KEY = product_import_module.PRODUCT_CACHE_KEY
_build_import_preview = product_import_module._build_import_preview
_enforce_import_upload = product_import_module._enforce_import_upload
_load_import_rows = product_import_module._load_import_rows
_parse_import_active = product_import_module._parse_import_active
_parse_import_decimal = product_import_module._parse_import_decimal
_parse_import_operation = product_import_module._parse_import_operation
_parse_import_stock = product_import_module._parse_import_stock
build_import_template = product_import_module.build_import_template
build_products_export = product_import_module.build_products_export
canonical_category_name = product_import_module.canonical_category_name
generate_sku = product_import_module.generate_sku
normalize_sku = product_import_module.normalize_sku
Category = product_models_module.Category
Product = product_models_module.Product
ProductImportJob = product_models_module.ProductImportJob
apply_product_import = product_routes_module.apply_product_import
create_category = product_routes_module.create_category
create_product = product_routes_module.create_product
delete_product = product_routes_module.delete_product
download_import_template = product_routes_module.download_import_template
export_products_excel = product_routes_module.export_products_excel
get_product = product_routes_module.get_product
list_categories = product_routes_module.list_categories
list_product_import_jobs = product_routes_module.list_product_import_jobs
list_products = product_routes_module.list_products
preview_product_import = product_routes_module.preview_product_import
require_admin = product_routes_module.require_admin
update_product = product_routes_module.update_product
router = product_routes_module.router
CategoryRequest = product_schemas_module.CategoryRequest
ProductRequest = product_schemas_module.ProductRequest
_product_archived_at = product_serializers_module._product_archived_at
_product_category_id = product_serializers_module._product_category_id
_product_description = product_serializers_module._product_description
_product_id = product_serializers_module._product_id
_product_name = product_serializers_module._product_name
_product_sku = product_serializers_module._product_sku
_set_product_archived_at = product_serializers_module._set_product_archived_at
_set_product_sku = product_serializers_module._set_product_sku
serialize_category = product_serializers_module.serialize_category
serialize_import_job = product_serializers_module.serialize_import_job
serialize_product = product_serializers_module.serialize_product

__all__ = [
    "Base",
    "Category",
    "CategoryRequest",
    "Product",
    "ProductImportJob",
    "ProductRequest",
]


def _run_migrations() -> None:
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")


def _sync_inventory_bulk(items: list[dict]) -> None:
    original_requests = product_import_module.requests
    product_import_module.requests = requests
    try:
        product_import_module._sync_inventory_bulk(items)
    finally:
        product_import_module.requests = original_requests


def _apply_import(preview: dict, db, *, filename: str, created_by: str) -> dict:
    original_sync = product_import_module._sync_inventory_bulk
    product_import_module._sync_inventory_bulk = _sync_inventory_bulk
    try:
        return product_import_module._apply_import(
            preview,
            db,
            filename=filename,
            created_by=created_by,
        )
    finally:
        product_import_module._sync_inventory_bulk = original_sync


async def startup():
    _run_migrations()
    with SessionLocal() as db:
        if db.query(Category).count() == 0:
            db.add_all(
                [
                    Category(
                        name="Periferice",
                        description="Tastaturi, mouse-uri, căști și camere web",
                    ),
                    Category(
                        name="Accesorii",
                        description="Dock-uri, cabluri, suporturi și accesorii pentru birou",
                    ),
                ]
            )
            db.commit()

        categories = {category.name: category.id for category in db.query(Category).all()}
        if db.query(Product).count() == 0:
            db.add_all(
                [
                    Product(
                        sku="KEYBOARD-MECH-001",
                        name="Mechanical Keyboard",
                        description="Tactile RGB keyboard",
                        price=119.0,
                        category_id=categories.get("Periferice"),
                    ),
                    Product(
                        sku="MOUSE-GAMING-001",
                        name="Gaming Mouse",
                        description="Lightweight wireless mouse",
                        price=79.0,
                        category_id=categories.get("Periferice"),
                    ),
                    Product(
                        sku="DOCK-USBC-001",
                        name="USB-C Dock",
                        description="Dock with HDMI and ethernet",
                        price=149.0,
                        category_id=categories.get("Accesorii"),
                    ),
                ]
            )
            db.commit()
    redis_client.delete(PRODUCT_CACHE_KEY)


app = create_base_app("product-service", startup_hook=startup, check_db=True, check_redis=True)
app.include_router(router)
