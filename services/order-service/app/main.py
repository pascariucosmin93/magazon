import asyncio
import os
import secrets
from datetime import datetime

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
import requests
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Session, relationship

from shared.auth import optional_user_claims, require_user_id
from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import consume_topics, publish_event
from shared.service_app import create_base_app

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String(120), nullable=True)
    customer_email = Column(String(255), nullable=True)
    shipping_address = Column(String(255), nullable=True)
    guest_token = Column(String(120), nullable=True, unique=True, index=True)
    status = Column(String(50), default="created", nullable=False)
    total = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")


class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int


class OrderRequest(BaseModel):
    items: list[OrderItemRequest]
    customer_name: str | None = None
    customer_email: str | None = None
    shipping_address: str | None = None


consumer_task = None


async def handle_event(topic: str, payload: dict):
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == payload.get("order_id")).first()
        if not order:
            return
        if topic == "inventory.reserved":
            order.status = (
                "inventory_reserved" if payload.get("status") == "reserved" else "inventory_failed"
            )
        elif topic == "payment.completed":
            order.status = "paid" if payload.get("status") == "completed" else "payment_failed"
        db.commit()
    finally:
        db.close()


def _run_migrations() -> None:
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")


async def startup():
    global consumer_task
    _run_migrations()
    consumer_task = asyncio.create_task(
        consume_topics("order-service", ["inventory.reserved", "payment.completed"], handle_event)
    )


async def shutdown():
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


def serialize_order(order: Order) -> dict:
    payload = {
        "order_id": order.id,
        "user_id": order.user_id,
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "shipping_address": order.shipping_address,
        "guest": order.user_id is None,
        "status": order.status,
        "total": order.total,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price": item.price,
            }
            for item in order.items
        ],
    }
    if order.user_id is None and order.guest_token:
        payload["guest_token"] = order.guest_token
    return payload


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
                "price": float(product["price"]),
            }
        )

    order = Order(
        user_id=user_id,
        customer_name=customer_name,
        customer_email=customer_email,
        shipping_address=shipping_address,
        guest_token=guest_token,
        status="created",
        total=sum(item["price"] * item["quantity"] for item in normalized_items),
    )
    db.add(order)
    db.flush()

    for item in normalized_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                price=item["price"],
            )
        )

    db.commit()
    db.refresh(order)

    await publish_event(
        "order.created",
        {
            "order_id": order.id,
            "user_id": order.user_id,
            "total": order.total,
            "items": normalized_items,
        },
    )
    db.refresh(order)
    return serialize_order(order)


@app.get("/orders/{order_id}")
def get_order(
    order_id: int,
    guest_token: str | None = Query(default=None),
    db: Session = Depends(get_db),
    claims: dict | None = Depends(optional_user_claims),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id is not None:
        if not claims:
            raise HTTPException(status_code=401, detail="Authorization required")
        require_user_id(order.user_id, claims)
    else:
        if not guest_token or guest_token != order.guest_token:
            raise HTTPException(status_code=401, detail="Guest token required")
    return serialize_order(order)
