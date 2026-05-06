import json

from fastapi import HTTPException
from pydantic import BaseModel

from shared.redis_client import redis_client
from shared.service_app import create_base_app


app = create_base_app("cart-service")


class CartItemRequest(BaseModel):
    user_id: int
    product_id: int
    quantity: int = 1


def cart_key(user_id: int) -> str:
    return f"cart:{user_id}"


@app.get("/cart/{user_id}")
def get_cart(user_id: int):
    items = redis_client.hgetall(cart_key(user_id))
    result = [
        {"product_id": int(product_id), "quantity": int(quantity)}
        for product_id, quantity in items.items()
    ]
    return {"user_id": user_id, "items": result}


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
