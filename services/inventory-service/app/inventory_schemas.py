from pydantic import BaseModel


class InventorySeedRequest(BaseModel):
    product_id: int
    stock: int


class BulkInventorySeedItem(BaseModel):
    product_id: int
    stock: int


class BulkInventorySeedRequest(BaseModel):
    items: list[BulkInventorySeedItem]
