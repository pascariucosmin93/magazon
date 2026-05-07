import asyncio
from datetime import datetime

from fastapi import Depends
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import Session

from shared.db import Base, SessionLocal, get_db
from shared.kafka import consume_topics, publish_event
from shared.service_app import create_base_app


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False, unique=True, index=True)
    amount = Column(Float, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)


consumer_task = None


async def handle_inventory(topic: str, payload: dict):
    if payload.get("status") != "reserved":
        return

    db = SessionLocal()
    try:
        existing = db.query(Payment).filter(Payment.order_id == payload["order_id"]).first()
        if existing:
            await publish_event(
                "payment.completed",
                {
                    "order_id": payload["order_id"],
                    "status": existing.status,
                    "amount": existing.amount,
                },
            )
            return
        amount = sum(item["price"] * item["quantity"] for item in payload.get("items", []))
        payment = Payment(order_id=payload["order_id"], amount=amount, status="completed")
        db.add(payment)
        db.commit()
        await publish_event(
            "payment.completed",
            {"order_id": payload["order_id"], "status": "completed", "amount": amount},
        )
    finally:
        db.close()


async def startup():
    global consumer_task
    consumer_task = asyncio.create_task(
        consume_topics("payment-service", ["inventory.reserved"], handle_inventory)
    )


async def shutdown():
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = create_base_app(
    "payment-service",
    startup_hook=startup,
    shutdown_hook=shutdown,
    enable_kafka=True,
    check_db=True,
)


@app.get("/payments")
def list_payments(db: Session = Depends(get_db)):
    items = db.query(Payment).all()
    return [
        {"order_id": item.order_id, "status": item.status, "amount": item.amount}
        for item in items
    ]
