from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from inventory_logic import upsert_inventory_item
from inventory_models import Inventory
from inventory_schemas import BulkInventorySeedRequest, InventorySeedRequest
from shared.auth import current_user_claims, require_internal_api_token
from shared.db import get_db


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


router = APIRouter()


@router.get("/inventory")
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


@router.get("/inventory/{product_id}")
def get_inventory(product_id: int, db: Session = Depends(get_db)):
    record = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return {"product_id": product_id, "stock": record.stock}


@router.post("/inventory/seed")
def seed_inventory(
    payload: InventorySeedRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if payload.stock < 0:
        raise HTTPException(status_code=400, detail="Stock must be >= 0")
    upsert_inventory_item(db, payload.product_id, payload.stock)
    db.commit()
    return {"message": "Inventory updated"}


@router.post("/inventory/bulk-seed")
def bulk_seed_inventory(
    payload: BulkInventorySeedRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    updated = 0
    for item in payload.items:
        upsert_inventory_item(db, item.product_id, item.stock)
        updated += 1
    db.commit()
    return {"message": "Inventory updated", "updated": updated}


@router.post("/inventory/internal/bulk-seed")
def internal_bulk_seed_inventory(
    payload: BulkInventorySeedRequest,
    db: Session = Depends(get_db),
    _internal=Depends(require_internal_api_token),
):
    updated = 0
    for item in payload.items:
        upsert_inventory_item(db, item.product_id, item.stock)
        updated += 1
    db.commit()
    return {"message": "Inventory updated", "updated": updated}
