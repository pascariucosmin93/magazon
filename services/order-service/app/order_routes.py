import secrets
from decimal import Decimal

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from order_models import Order, OrderItem
from order_repository import get_order, list_orders, list_orders_for_user
from order_schemas import OrderCancellationRequest, OrderRequest, OrderStatusRequest
from order_serializers import serialize_order
from shared.auth import current_user_claims, optional_user_claims
from shared.db import get_db
from shared.money import as_money, money_json


def register_routes(app, dependencies):
    @app.post("/orders")
    async def create_order(
        payload: OrderRequest,
        db: Session = Depends(get_db),
        claims: dict | None = Depends(optional_user_claims),
    ):
        deps = dependencies()
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
                    detail=(
                        "Guest checkout requires customer_name, customer_email "
                        "and shipping_address"
                    ),
                )
            guest_token = secrets.token_urlsafe(24)

        normalized_items = []
        for item in payload.items:
            product = await deps["fetch_product"](item.product_id)
            normalized_items.append(
                {
                    "product_id": item.product_id,
                    "product_name": product.get("name") or f"Produs #{item.product_id}",
                    "product_sku": product.get("sku") or f"PRODUCT-{item.product_id}",
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
            total=sum(
                (
                    as_money(item["price"]) * item["quantity"]
                    for item in normalized_items
                ),
                Decimal("0.00"),
            ),
        )
        db.add(order)
        db.flush()

        for item in normalized_items:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=item["product_id"],
                    product_name=item["product_name"],
                    product_sku=item["product_sku"],
                    quantity=item["quantity"],
                    price=as_money(item["price"]),
                )
            )

        deps["enqueue_outbox_event"](
            db,
            "order.created",
            {
                "order_id": order.id,
                "user_id": order.user_id,
                "total": money_json(order.total),
                "items": normalized_items,
            },
        )
        db.commit()
        db.refresh(order)

        try:
            await deps["publish_pending_outbox_events_once"](limit=5)
        except Exception as exc:
            deps["logger"].warning(
                "Immediate outbox publish failed for order_id=%s: %s",
                order.id,
                exc,
            )
        db.refresh(order)
        return serialize_order(order)

    @app.get("/orders/mine")
    def list_my_orders(
        db: Session = Depends(get_db),
        claims: dict = Depends(current_user_claims),
    ):
        user_id = dependencies()["_claims_user_id"](claims)
        orders = list_orders_for_user(db, user_id)
        return {
            "items": [
                serialize_order(order, include_guest_token=False) for order in orders
            ],
            "total": len(orders),
        }

    @app.get("/orders")
    def get_orders(
        db: Session = Depends(get_db),
        _admin=Depends(dependencies()["require_admin"]),
    ):
        orders = list_orders(db)
        return {
            "items": [
                serialize_order(order, include_guest_token=False) for order in orders
            ],
            "total": len(orders),
        }

    @app.put("/orders/{order_id}/status")
    def update_order_status(
        order_id: int,
        payload: OrderStatusRequest,
        db: Session = Depends(get_db),
        _admin=Depends(dependencies()["require_admin"]),
    ):
        deps = dependencies()
        order = get_order(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        next_status = payload.status.strip().lower()
        allowed_statuses = deps["ADMIN_STATUS_TRANSITIONS"].get(order.status, set())
        if next_status not in allowed_statuses:
            allowed = ", ".join(sorted(allowed_statuses)) or "none"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot change order from {order.status} to {next_status}. "
                    f"Allowed: {allowed}"
                ),
            )

        if next_status == "cancelled":
            deps["_cancel_order"](order, "Cancelled by administrator", db)
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
        deps = dependencies()
        order = get_order(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        deps["_ensure_order_access"](order, claims, x_guest_token)
        deps["_cancel_order"](order, payload.reason if payload else None, db)
        db.commit()
        db.refresh(order)
        try:
            await deps["publish_pending_outbox_events_once"](limit=5)
        except Exception as exc:
            deps["logger"].warning(
                "Immediate cancellation publish failed for order_id=%s: %s",
                order.id,
                exc,
            )
        return serialize_order(order)

    @app.get("/orders/{order_id}")
    def get_order_by_id(
        order_id: int,
        x_guest_token: str | None = Header(default=None),
        db: Session = Depends(get_db),
        claims: dict | None = Depends(optional_user_claims),
    ):
        order = get_order(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        dependencies()["_ensure_order_access"](order, claims, x_guest_token)
        return serialize_order(order)

    return {
        "create_order": create_order,
        "list_my_orders": list_my_orders,
        "list_orders": get_orders,
        "update_order_status": update_order_status,
        "cancel_order": cancel_order,
        "get_order": get_order_by_id,
    }
