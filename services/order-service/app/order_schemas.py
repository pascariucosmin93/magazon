from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)


class OrderRequest(BaseModel):
    items: list[OrderItemRequest]
    customer_name: str | None = None
    customer_email: str | None = None
    shipping_address: str | None = None


class OrderStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=50)


class OrderCancellationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)
