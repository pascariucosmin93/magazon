import asyncio
import os
from datetime import datetime

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import consume_topics, publish_event
from shared.service_app import create_base_app


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, unique=True, nullable=False, index=True)
    stock = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InventorySeedRequest(BaseModel):
    product_id: int
    stock: int


consumer_task = None


async def handle_order_created(topic: str, payload: dict):
    db = SessionLocal()
    try:
        ok = True
        for item in payload.get("items", []):
            record = db.query(Inventory).filter(Inventory.product_id == item["product_id"]).first()
            if not record or record.stock < item["quantity"]:
                ok = False
                break

        if ok:
            for item in payload.get("items", []):
                record = db.query(Inventory).filter(Inventory.product_id == item["product_id"]).first()
                record.stock -= item["quantity"]
            db.commit()
            await publish_event(
                "inventory.reserved",
                {"order_id": payload["order_id"], "status": "reserved", "items": payload["items"]},
            )
        else:
            await publish_event(
                "inventory.reserved",
                {"order_id": payload["order_id"], "status": "failed", "items": payload["items"]},
            )
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
        consume_topics("inventory-service", ["order.created"], handle_order_created)
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


@app.get("/inventory/{product_id}")
def get_inventory(product_id: int, db: Session = Depends(get_db)):
    record = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return {"product_id": product_id, "stock": record.stock}


@app.post("/inventory/seed")
def seed_inventory(payload: InventorySeedRequest, db: Session = Depends(get_db)):
    record = db.query(Inventory).filter(Inventory.product_id == payload.product_id).first()
    if record:
        record.stock = payload.stock
    else:
        db.add(Inventory(product_id=payload.product_id, stock=payload.stock))
    db.commit()
    return {"message": "Inventory updated"}
