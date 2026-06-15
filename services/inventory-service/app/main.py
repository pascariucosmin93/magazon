import asyncio
import os
import sys
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    for module_name in (
        "inventory_logic",
        "inventory_models",
        "inventory_routes",
        "inventory_schemas",
    ):
        sys.modules.pop(module_name, None)

import inventory_logic as inventory_logic_module  # noqa: E402
import inventory_models as inventory_models_module  # noqa: E402
import inventory_routes as inventory_routes_module  # noqa: E402
import inventory_schemas as inventory_schemas_module  # noqa: E402
from shared.config import settings  # noqa: E402
from shared.db import Base, SessionLocal  # noqa: E402
from shared.kafka import consume_topics, publish_event  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

Inventory = inventory_models_module.Inventory
InventoryReservation = inventory_models_module.InventoryReservation
ProcessedMessage = inventory_models_module.ProcessedMessage
InventorySeedRequest = inventory_schemas_module.InventorySeedRequest
BulkInventorySeedItem = inventory_schemas_module.BulkInventorySeedItem
BulkInventorySeedRequest = inventory_schemas_module.BulkInventorySeedRequest
_set_inventory_stock = inventory_logic_module._set_inventory_stock
_mark_event_processed = inventory_logic_module._mark_event_processed
upsert_inventory_item = inventory_logic_module.upsert_inventory_item
require_admin = inventory_routes_module.require_admin
list_inventory = inventory_routes_module.list_inventory
get_inventory = inventory_routes_module.get_inventory
seed_inventory = inventory_routes_module.seed_inventory
bulk_seed_inventory = inventory_routes_module.bulk_seed_inventory
internal_bulk_seed_inventory = inventory_routes_module.internal_bulk_seed_inventory
router = inventory_routes_module.router

__all__ = [
    "Base",
    "BulkInventorySeedItem",
    "BulkInventorySeedRequest",
    "Inventory",
    "InventoryReservation",
    "InventorySeedRequest",
    "ProcessedMessage",
]

consumer_task = None


def _run_migrations() -> None:
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")


async def handle_order_event(topic: str, payload: dict):
    original_session_local = inventory_logic_module.SessionLocal
    original_publish_event = inventory_logic_module.publish_event
    inventory_logic_module.SessionLocal = SessionLocal
    inventory_logic_module.publish_event = publish_event
    try:
        await inventory_logic_module.handle_order_event(topic, payload)
    finally:
        inventory_logic_module.SessionLocal = original_session_local
        inventory_logic_module.publish_event = original_publish_event


async def startup():
    global consumer_task
    _run_migrations()
    with SessionLocal() as db:
        if db.query(Inventory).count() == 0:
            db.add_all(
                [
                    Inventory(product_id=1, stock=25),
                    Inventory(product_id=2, stock=40),
                    Inventory(product_id=3, stock=15),
                ]
            )
            db.commit()
    consumer_task = asyncio.create_task(
        consume_topics("inventory-service", ["order.created", "order.cancelled"], handle_order_event)
    )


async def shutdown():
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = create_base_app(
    "inventory-service",
    startup_hook=startup,
    shutdown_hook=shutdown,
    enable_kafka=True,
    check_db=True,
)
app.include_router(router)
