from order_models import Order
from shared.money import money_json


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
                "product_name": item.product_name or f"Produs #{item.product_id}",
                "product_sku": item.product_sku or f"PRODUCT-{item.product_id}",
                "quantity": item.quantity,
                "price": money_json(item.price),
            }
            for item in order.items
        ],
    }
    if include_guest_token and order.user_id is None and order.guest_token:
        payload["guest_token"] = order.guest_token
    return payload
