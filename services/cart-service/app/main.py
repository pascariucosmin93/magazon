import os
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
import requests

from shared.redis_client import redis_client
from shared.service_app import create_base_app


app = create_base_app("cart-service")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")


class CartItemRequest(BaseModel):
    user_id: int
    product_id: int
    quantity: int = 1


def cart_key(user_id: int) -> str:
    return f"cart:{user_id}"


def fetch_product(product_id: int) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=3,
        )
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        return None
    return None


@app.get("/cart/{user_id}")
def get_cart(user_id: int):
    items = redis_client.hgetall(cart_key(user_id))
    result = []
    total = 0.0

    for product_id, quantity in items.items():
        product_id_int = int(product_id)
        quantity_int = int(quantity)
        product = fetch_product(product_id_int)
        price = float(product["price"]) if product else 0.0
        subtotal = price * quantity_int
        total += subtotal
        result.append(
            {
                "product_id": product_id_int,
                "name": product["name"] if product else f"Product {product_id_int}",
                "price": price,
                "quantity": quantity_int,
                "subtotal": subtotal,
            }
        )

    return {"user_id": user_id, "items": result, "total": total}


@app.post("/cart/add")
def add_to_cart(payload: CartItemRequest):
    if payload.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be >= 1")

    redis_client.hincrby(cart_key(payload.user_id), payload.product_id, payload.quantity)
    redis_client.expire(cart_key(payload.user_id), 86400)
    return {"message": "Item added to cart"}


@app.delete("/cart/{user_id}")
def clear_cart(user_id: int):
    redis_client.delete(cart_key(user_id))
    return {"message": "Cart cleared"}


@app.post("/cart/replace")
def replace_cart(payload: CartItemRequest):
    redis_client.hset(cart_key(payload.user_id), payload.product_id, payload.quantity)
    redis_client.expire(cart_key(payload.user_id), 86400)
    return {"message": "Cart updated"}
