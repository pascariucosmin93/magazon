import json
from datetime import datetime

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Session

from shared.db import Base, SessionLocal, engine, get_db
from shared.redis_client import redis_client
from shared.service_app import create_base_app


PRODUCT_CACHE_KEY = "products:all"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductRequest(BaseModel):
    name: str
    description: str
    price: float


async def startup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(Product).count() == 0:
            db.add_all(
                [
                    Product(name="Mechanical Keyboard", description="Tactile RGB keyboard", price=119.0),
                    Product(name="Gaming Mouse", description="Lightweight wireless mouse", price=79.0),
                    Product(name="USB-C Dock", description="Dock with HDMI and ethernet", price=149.0),
                ]
            )
            db.commit()


app = create_base_app("product-service", startup_hook=startup)


def serialize_product(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
    }


@app.get("/products")
def list_products(db: Session = Depends(get_db)):
    cached = redis_client.get(PRODUCT_CACHE_KEY)
    if cached:
        return {"source": "cache", "items": json.loads(cached)}

    products = [serialize_product(product) for product in db.query(Product).all()]
    redis_client.setex(PRODUCT_CACHE_KEY, 120, json.dumps(products))
    return {"source": "database", "items": products}


@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize_product(product)


@app.post("/products")
def create_product(payload: ProductRequest, db: Session = Depends(get_db)):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    redis_client.delete(PRODUCT_CACHE_KEY)
    return serialize_product(product)
