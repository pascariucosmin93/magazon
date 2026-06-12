import asyncio
import os
from datetime import datetime

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.auth import current_user_claims, require_internal_api_token
from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import consume_topics, get_current_event, publish_event
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


class BulkInventorySeedItem(BaseModel):
    product_id: int
    stock: int


class BulkInventorySeedRequest(BaseModel):
    items: list[BulkInventorySeedItem]


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, unique=True, nullable=False, index=True)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    topic = Column(String(255), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


consumer_task = None


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


async def handle_order_event(topic: str, payload: dict):
    db = SessionLocal()
    try:
        if _mark_event_processed(db, topic):
            return

        if topic == "order.cancelled":
            existing = (
                db.query(InventoryReservation)
                .filter(InventoryReservation.order_id == payload["order_id"])
                .first()
            )
            if not existing:
                db.add(InventoryReservation(order_id=payload["order_id"], status="cancelled"))
                db.commit()
                await publish_event(
                    "inventory.released",
                    {"order_id": payload["order_id"], "status": "cancelled_before_reservation"},
                )
                return
            if existing.status == "reserved":
                for item in payload.get("items", []):
                    record = (
                        db.query(Inventory)
                        .filter(Inventory.product_id == item["product_id"])
                        .with_for_update()
                        .first()
                    )
                    if record:
                        record.stock += int(item["quantity"])
                existing.status = "released"
                existing.released_at = datetime.utcnow()
            elif existing.status == "failed":
                existing.status = "cancelled"
                existing.released_at = datetime.utcnow()
            db.commit()
            await publish_event(
                "inventory.released",
                {"order_id": payload["order_id"], "status": existing.status},
            )
            return

        existing = (
            db.query(InventoryReservation)
            .filter(InventoryReservation.order_id == payload["order_id"])
            .first()
        )
        if existing:
            db.commit()
            await publish_event(
                "inventory.reserved",
                {"order_id": payload["order_id"], "status": existing.status, "items": payload["items"]},
            )
            return

        ok = True
        for item in payload.get("items", []):
            record = db.query(Inventory).filter(Inventory.product_id == item["product_id"]).with_for_update().first()
            if not record or record.stock < item["quantity"]:
                ok = False
                break

        if ok:
            for item in payload.get("items", []):
                record = db.query(Inventory).filter(Inventory.product_id == item["product_id"]).with_for_update().first()
                record.stock -= item["quantity"]
            db.add(InventoryReservation(order_id=payload["order_id"], status="reserved"))
            db.commit()
            await publish_event(
                "inventory.reserved",
                {"order_id": payload["order_id"], "status": "reserved", "items": payload["items"]},
            )
        else:
            db.add(InventoryReservation(order_id=payload["order_id"], status="failed"))
            db.commit()
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


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


@app.get("/inventory")
def list_inventory(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    records = db.query(Inventory).order_by(Inventory.product_id).all()
    return {
        "items": [
            {
                "product_id": record.product_id,
                "stock": record.stock,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for record in records
        ],
        "total": len(records),
    }


@app.get("/inventory/{product_id}")
def get_inventory(product_id: int, db: Session = Depends(get_db)):
    record = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return {"product_id": product_id, "stock": record.stock}


@app.post("/inventory/seed")
def seed_inventory(
    payload: InventorySeedRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if payload.stock < 0:
        raise HTTPException(status_code=400, detail="Stock must be >= 0")
    record = db.query(Inventory).filter(Inventory.product_id == payload.product_id).first()
    if record:
        record.stock = payload.stock
    else:
        db.add(Inventory(product_id=payload.product_id, stock=payload.stock))
    db.commit()
    return {"message": "Inventory updated"}


@app.post("/inventory/bulk-seed")
def bulk_seed_inventory(
    payload: BulkInventorySeedRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    updated = 0
    for item in payload.items:
        if item.stock < 0:
            raise HTTPException(status_code=400, detail=f"Stock must be >= 0 for product_id {item.product_id}")
        record = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
        if record:
            record.stock = item.stock
        else:
            db.add(Inventory(product_id=item.product_id, stock=item.stock))
        updated += 1
    db.commit()
    return {"message": "Inventory updated", "updated": updated}


@app.post("/inventory/internal/bulk-seed")
def internal_bulk_seed_inventory(
    payload: BulkInventorySeedRequest,
    db: Session = Depends(get_db),
    _internal=Depends(require_internal_api_token),
):
    updated = 0
    for item in payload.items:
        if item.stock < 0:
            raise HTTPException(status_code=400, detail=f"Stock must be >= 0 for product_id {item.product_id}")
        record = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
        if record:
            record.stock = item.stock
        else:
            db.add(Inventory(product_id=item.product_id, stock=item.stock))
        updated += 1
    db.commit()
    return {"message": "Inventory updated", "updated": updated}
