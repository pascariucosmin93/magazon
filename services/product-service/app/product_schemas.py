from decimal import Decimal

from pydantic import BaseModel, Field


class ProductRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    price: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    category_id: int | None = None


class CategoryRequest(BaseModel):
    name: str
    description: str
