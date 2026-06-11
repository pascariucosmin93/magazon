import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
import requests
from fastapi import Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    for module_name in (
        "order_outbox",
        "order_repository",
        "order_routes",
        "order_serializers",
        "order_schemas",
        "order_models",
    ):
        sys.modules.pop(module_name, None)

from order_models import Order, OrderItem, OutboxEvent, ProcessedMessage  # noqa: E402
from order_outbox import enqueue as enqueue_outbox_event  # noqa: E402
from order_outbox import publish_pending_once as publish_outbox_once  # noqa: E402
from order_outbox import serialize_payload as serialize_outbox_payload  # noqa: E402
from order_repository import get_order as repository_get_order  # noqa: E402
from order_routes import register_routes  # noqa: E402
from order_schemas import (  # noqa: E402
    OrderCancellationRequest,
    OrderItemRequest,
    OrderRequest,
    OrderStatusRequest,
)
from order_serializers import serialize_order  # noqa: E402
from shared.auth import current_user_claims, require_user_id  # noqa: E402
from shared.config import settings  # noqa: E402
from shared.db import Base, SessionLocal  # noqa: E402
from shared.kafka import consume_topics, get_current_event, publish_event  # noqa: E402
from shared.money import money_json  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

__all__ = [
    "Order",
    "Base",
    "OrderCancellationRequest",
    "OrderItem",
    "OrderItemRequest",
    "OrderRequest",
    "OrderStatusRequest",
    "OutboxEvent",
    "ProcessedMessage",
    "serialize_order",
]

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")
logger = logging.getLogger(__name__)
ADMIN_STATUS_TRANSITIONS = {
    "created": {"cancelled"},
    "inventory_reserved": {"cancelled"},
    "inventory_failed": {"cancelled"},
    "payment_failed": {"cancelled"},
    "paid": {"processing", "cancelled"},
    "processing": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}
consumer_task = None
outbox_task = None


def _mark_event_processed(db: Session, topic: str) -> bool:
    event = get_current_event()
    if not event:
        return False

    event_id = event["event_id"]
    existing = db.query(ProcessedMessage).filter(ProcessedMessage.event_id == event_id).first()
    if existing:
        return True

    db.add(ProcessedMessage(event_id=event_id, topic=topic))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return True
    return False


async def handle_event(topic: str, payload: dict):
    db = SessionLocal()
    try:
        if _mark_event_processed(db, topic):
            return

        order = repository_get_order(db, payload.get("order_id"))
        if not order:
            db.commit()
            return
        if topic == "inventory.reserved" and order.status == "created":
            order.status = (
                "inventory_reserved" if payload.get("status") == "reserved" else "inventory_failed"
            )
        elif topic == "payment.completed" and order.status == "inventory_reserved":
            order.status = "paid" if payload.get("status") == "completed" else "payment_failed"
        db.commit()
    finally:
        db.close()


def _serialize_outbox_payload(payload: dict) -> str:
    return serialize_outbox_payload(payload)


async def publish_pending_outbox_events_once(limit: int = 20) -> None:
    await publish_outbox_once(SessionLocal, publish_event, logger, limit)


async def outbox_publisher_loop() -> None:
    while True:
        await publish_pending_outbox_events_once()
        await asyncio.sleep(1)


def _run_migrations() -> None:
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")


async def startup():
    global consumer_task, outbox_task
    _run_migrations()
    consumer_task = asyncio.create_task(
        consume_topics("order-service", ["inventory.reserved", "payment.completed"], handle_event)
    )
    outbox_task = asyncio.create_task(outbox_publisher_loop())


async def shutdown():
    if outbox_task:
        outbox_task.cancel()
        try:
            await outbox_task
        except asyncio.CancelledError:
            pass
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = create_base_app(
    "order-service",
    startup_hook=startup,
    shutdown_hook=shutdown,
    enable_kafka=True,
    check_db=True,
)


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


def _fetch_product_sync(product_id: int) -> dict:
    try:
        response = requests.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}", timeout=3)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Product service unavailable") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Product service returned an error")
    return response.json()


async def fetch_product(product_id: int) -> dict:
    return await asyncio.to_thread(_fetch_product_sync, product_id)


def _claims_user_id(claims: dict) -> int:
    subject = claims.get("sub")
    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _ensure_order_access(order: Order, claims: dict | None, guest_token: str | None) -> None:
    if claims and claims.get("role") == "admin":
        return
    if order.user_id is not None:
        if not claims:
            raise HTTPException(status_code=401, detail="Authorization required")
        require_user_id(order.user_id, claims)
        return
    if not guest_token or guest_token != order.guest_token:
        raise HTTPException(status_code=401, detail="Guest token required")


def _cancel_order(order: Order, reason: str | None, db: Session) -> None:
    if order.status == "cancelled":
        return
    if order.status in {"shipped", "delivered"}:
        raise HTTPException(status_code=409, detail="Order can no longer be cancelled")

    previous_status = order.status
    order.status = "cancelled"
    order.cancelled_at = datetime.utcnow()
    order.cancellation_reason = reason.strip() if reason and reason.strip() else None
    db.add(order)
    enqueue_outbox_event(
        db,
        "order.cancelled",
        {
            "order_id": order.id,
            "user_id": order.user_id,
            "previous_status": previous_status,
            "reason": order.cancellation_reason,
            "total": money_json(order.total),
            "items": [
                {
                    "product_id": item.product_id,
                    "product_name": item.product_name or f"Produs #{item.product_id}",
                    "product_sku": item.product_sku or f"PRODUCT-{item.product_id}",
                    "quantity": item.quantity,
                    "price": money_json(item.price),
                }
                for item in order.items
            ],
        },
    )


globals().update(register_routes(app, lambda: globals()))
