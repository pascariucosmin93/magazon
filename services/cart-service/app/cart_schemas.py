from pydantic import BaseModel


class CartItemRequest(BaseModel):
    user_id: int
    product_id: int
    quantity: int = 1
