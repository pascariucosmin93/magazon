from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from inventory_models import Inventory, InventoryReservation, ProcessedMessage
from shared.db import SessionLocal
from shared.kafka import get_current_event, publish_event


def _set_inventory_stock(record: Inventory, stock: int) -> None:
    setattr(record, "stock", stock)


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
            record = (
                db.query(Inventory)
                .filter(Inventory.product_id == item["product_id"])
                .with_for_update()
                .first()
            )
            if not record or record.stock < item["quantity"]:
                ok = False
                break

        if ok:
            for item in payload.get("items", []):
                record = (
                    db.query(Inventory)
                    .filter(Inventory.product_id == item["product_id"])
                    .with_for_update()
                    .first()
                )
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


def upsert_inventory_item(db: Session, product_id: int, stock: int) -> None:
    if stock < 0:
        raise HTTPException(status_code=400, detail=f"Stock must be >= 0 for product_id {product_id}")
    record = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if record:
        _set_inventory_stock(record, stock)
    else:
        db.add(Inventory(product_id=product_id, stock=stock))
