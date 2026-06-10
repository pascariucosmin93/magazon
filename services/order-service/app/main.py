import asyncio
import json
import logging
import os
import secrets
from datetime import datetime
from decimal import Decimal

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
import requests
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, relationship

from shared.auth import current_user_claims, optional_user_claims, require_user_id
from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import consume_topics, get_current_event, publish_event
from shared.money import as_money, money_json
from shared.service_app import create_base_app

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


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String(120), nullable=True)
    customer_email = Column(String(255), nullable=True)
    shipping_address = Column(String(255), nullable=True)
    guest_token = Column(String(120), nullable=True, unique=True, index=True)
    status = Column(String(50), default="created", nullable=False)
    total = Column(Numeric(12, 2), default=0, nullable=False)
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    order = relationship("Order", back_populates="items")


class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)


class OrderRequest(BaseModel):
    items: list[OrderItemRequest]
    customer_name: str | None = None
    customer_email: str | None = None
    shipping_address: str | None = None


class OrderStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=50)


class OrderCancellationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    topic = Column(String(255), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)
    published = Column(Boolean, nullable=False, default=False)
    publish_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)


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

        order = db.query(Order).filter(Order.id == payload.get("order_id")).first()
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
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


async def publish_pending_outbox_events_once(limit: int = 20) -> None:
    db = SessionLocal()
    try:
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.published.is_(False))
            .order_by(OutboxEvent.id.asc())
            .limit(limit)
            .all()
        )
        for event in events:
            event.publish_attempts += 1
            try:
                await publish_event(event.topic, json.loads(event.payload))
                event.published = True
                event.published_at = datetime.utcnow()
                event.last_error = None
            except Exception as exc:
                event.last_error = str(exc)
                logger.warning("Outbox publish failed id=%s topic=%s error=%s", event.id, event.topic, exc)
                db.add(event)
                db.commit()
                continue
            db.add(event)
            db.commit()
    finally:
        db.close()


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


def fetch_product(product_id: int) -> dict:
    try:
        response = requests.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}", timeout=3)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Product service unavailable") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Product service returned an error")
    return response.json()


def serialize_order(order: Order, include_guest_token: bool = True) -> dict:
    payload = {
        "order_id": order.id,
        "user_id": order.user_id,
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "shipping_address": order.shipping_address,
        "guest": order.user_id is None,
        "status": order.status,
        "total": money_json(order.total),
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": money_json(item.price),
            }
            for item in order.items
        ],
    }
    if include_guest_token and order.user_id is None and order.guest_token:
        payload["guest_token"] = order.guest_token
    return payload


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
    db.add(
        OutboxEvent(
            topic="order.cancelled",
            payload=_serialize_outbox_payload(
                {
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "previous_status": previous_status,
                    "reason": order.cancellation_reason,
                    "total": money_json(order.total),
                    "items": [
                        {
                            "product_id": item.product_id,
                            "quantity": item.quantity,
                            "price": money_json(item.price),
                        }
                        for item in order.items
                    ],
                }
            ),
        )
    )


@app.post("/orders")
async def create_order(
    payload: OrderRequest,
    db: Session = Depends(get_db),
    claims: dict | None = Depends(optional_user_claims),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order requires at least one item")

    user_id = None
    guest_token = None
    customer_name = payload.customer_name.strip() if payload.customer_name else None
    customer_email = payload.customer_email.strip().lower() if payload.customer_email else None
    shipping_address = payload.shipping_address.strip() if payload.shipping_address else None

    if claims:
        subject = claims.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid token")
        try:
            user_id = int(subject)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc
    else:
        if not customer_name or not customer_email or not shipping_address:
            raise HTTPException(
                status_code=400,
                detail="Guest checkout requires customer_name, customer_email and shipping_address",
            )
        guest_token = secrets.token_urlsafe(24)

    normalized_items = []
    for item in payload.items:
        if item.quantity < 1:
            raise HTTPException(status_code=400, detail="Quantity must be >= 1")
        product = fetch_product(item.product_id)
        normalized_items.append(
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": money_json(product["price"]),
            }
        )

    order = Order(
        user_id=user_id,
        customer_name=customer_name,
        customer_email=customer_email,
        shipping_address=shipping_address,
        guest_token=guest_token,
        status="created",
        total=sum((as_money(item["price"]) * item["quantity"] for item in normalized_items), Decimal("0.00")),
    )
    db.add(order)
    db.flush()

    for item in normalized_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                price=as_money(item["price"]),
            )
        )

    outbox_payload = {
        "order_id": order.id,
        "user_id": order.user_id,
        "total": money_json(order.total),
        "items": normalized_items,
    }
    db.add(
        OutboxEvent(
            topic="order.created",
            payload=_serialize_outbox_payload(outbox_payload),
        )
    )
    db.commit()
    db.refresh(order)

    try:
        await publish_pending_outbox_events_once(limit=5)
    except Exception as exc:
        logger.warning("Immediate outbox publish failed for order_id=%s: %s", order.id, exc)
    db.refresh(order)
    return serialize_order(order)


@app.get("/orders/mine")
def list_my_orders(
    db: Session = Depends(get_db),
    claims: dict = Depends(current_user_claims),
):
    user_id = _claims_user_id(claims)
    orders = (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    return {
        "items": [serialize_order(order, include_guest_token=False) for order in orders],
        "total": len(orders),
    }


@app.get("/orders")
def list_orders(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    orders = db.query(Order).order_by(Order.created_at.desc(), Order.id.desc()).all()
    return {
        "items": [serialize_order(order, include_guest_token=False) for order in orders],
        "total": len(orders),
    }


@app.put("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    payload: OrderStatusRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    next_status = payload.status.strip().lower()
    allowed_statuses = ADMIN_STATUS_TRANSITIONS.get(order.status, set())
    if next_status not in allowed_statuses:
        allowed = ", ".join(sorted(allowed_statuses)) or "none"
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change order from {order.status} to {next_status}. Allowed: {allowed}",
        )

    if next_status == "cancelled":
        _cancel_order(order, "Cancelled by administrator", db)
    else:
        order.status = next_status
        db.add(order)
    db.commit()
    db.refresh(order)
    return serialize_order(order, include_guest_token=False)


@app.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    payload: OrderCancellationRequest | None = None,
    x_guest_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    claims: dict | None = Depends(optional_user_claims),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    _ensure_order_access(order, claims, x_guest_token)
    _cancel_order(order, payload.reason if payload else None, db)
    db.commit()
    db.refresh(order)
    try:
        await publish_pending_outbox_events_once(limit=5)
    except Exception as exc:
        logger.warning("Immediate cancellation publish failed for order_id=%s: %s", order.id, exc)
    return serialize_order(order)


@app.get("/orders/{order_id}")
def get_order(
    order_id: int,
    x_guest_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    claims: dict | None = Depends(optional_user_claims),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    _ensure_order_access(order, claims, x_guest_token)
    return serialize_order(order)
