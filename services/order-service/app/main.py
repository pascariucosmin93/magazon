import asyncio
from datetime import datetime

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Session, relationship

from shared.db import Base, SessionLocal, engine, get_db
from shared.kafka import consume_topics, publish_event
from shared.service_app import create_base_app


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
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
    price: float


class OrderRequest(BaseModel):
    user_id: int
    items: list[OrderItemRequest]


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


async def startup():
    global consumer_task
    Base.metadata.create_all(bind=engine)
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
)


@app.post("/orders")
async def create_order(payload: OrderRequest, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order requires at least one item")

    order = Order(
        user_id=payload.user_id,
        status="created",
        total=sum(item.price * item.quantity for item in payload.items),
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.price,
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
            "items": [item.model_dump() for item in payload.items],
        },
    )
    return {"order_id": order.id, "status": order.status, "total": order.total}


@app.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order.id,
        "user_id": order.user_id,
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
