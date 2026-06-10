import os
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel
import requests

from shared.auth import current_user_claims, require_user_id
from shared.money import as_money, money_json
from shared.redis_client import redis_client
from shared.service_app import create_base_app


app = create_base_app("cart-service", check_redis=True)
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
def get_cart(user_id: int, claims: dict = Depends(current_user_claims)):
    require_user_id(user_id, claims)
    items = redis_client.hgetall(cart_key(user_id))
    result = []
    total = as_money(0)

    for product_id, quantity in items.items():
        product_id_int = int(product_id)
        quantity_int = int(quantity)
        product = fetch_product(product_id_int)
        price = as_money(product["price"]) if product else as_money(0)
        subtotal = price * quantity_int
        total += subtotal
        result.append(
            {
                "product_id": product_id_int,
                "name": product["name"] if product else f"Product {product_id_int}",
                "price": money_json(price),
                "quantity": quantity_int,
                "subtotal": money_json(subtotal),
            }
        )

    return {"user_id": user_id, "items": result, "total": money_json(total)}


@app.post("/cart/add")
def add_to_cart(payload: CartItemRequest, claims: dict = Depends(current_user_claims)):
    require_user_id(payload.user_id, claims)
    if payload.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be >= 1")

    redis_client.hincrby(cart_key(payload.user_id), payload.product_id, payload.quantity)
    redis_client.expire(cart_key(payload.user_id), 86400)
    return {"message": "Item added to cart"}


@app.delete("/cart/{user_id}")
def clear_cart(user_id: int, claims: dict = Depends(current_user_claims)):
    require_user_id(user_id, claims)
    redis_client.delete(cart_key(user_id))
    return {"message": "Cart cleared"}


@app.post("/cart/replace")
def replace_cart(payload: CartItemRequest, claims: dict = Depends(current_user_claims)):
    require_user_id(payload.user_id, claims)
    if payload.quantity < 1:
        redis_client.hdel(cart_key(payload.user_id), payload.product_id)
        redis_client.expire(cart_key(payload.user_id), 86400)
        return {"message": "Item removed from cart"}
    redis_client.hset(cart_key(payload.user_id), payload.product_id, payload.quantity)
    redis_client.expire(cart_key(payload.user_id), 86400)
    return {"message": "Cart updated"}


@app.delete("/cart/{user_id}/items/{product_id}")
def remove_cart_item(user_id: int, product_id: int, claims: dict = Depends(current_user_claims)):
    require_user_id(user_id, claims)
    redis_client.hdel(cart_key(user_id), product_id)
    redis_client.expire(cart_key(user_id), 86400)
    return {"message": "Item removed from cart"}
