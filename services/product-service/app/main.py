import os
import json
from datetime import datetime
from decimal import Decimal

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Session

from shared.auth import current_user_claims
from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.money import as_money, money_json
from shared.redis_client import redis_client
from shared.service_app import create_base_app


PRODUCT_CACHE_KEY = "products:all"


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    price: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    category_id: int | None = None


class CategoryRequest(BaseModel):
    name: str
    description: str


def _run_migrations() -> None:
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")


async def startup():
    _run_migrations()
    with SessionLocal() as db:
        if db.query(Category).count() == 0:
            db.add_all(
                [
                    Category(name="Keyboards", description="Mechanical and productivity keyboards"),
                    Category(name="Mice", description="Gaming and office mice"),
                    Category(name="Accessories", description="Docks, cables and desk accessories"),
                ]
            )
            db.commit()

        categories = {category.name: category.id for category in db.query(Category).all()}
        if db.query(Product).count() == 0:
            db.add_all(
                [
                    Product(
                        name="Mechanical Keyboard",
                        description="Tactile RGB keyboard",
                        price=119.0,
                        category_id=categories.get("Keyboards"),
                    ),
                    Product(
                        name="Gaming Mouse",
                        description="Lightweight wireless mouse",
                        price=79.0,
                        category_id=categories.get("Mice"),
                    ),
                    Product(
                        name="USB-C Dock",
                        description="Dock with HDMI and ethernet",
                        price=149.0,
                        category_id=categories.get("Accessories"),
                    ),
                ]
            )
            db.commit()


app = create_base_app("product-service", startup_hook=startup, check_db=True, check_redis=True)


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


def serialize_product(product: Product, categories_by_id: dict[int, Category]) -> dict:
    category = categories_by_id.get(product.category_id)
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": money_json(product.price),
        "category_id": product.category_id,
        "category_name": category.name if category else None,
    }


def serialize_category(category: Category) -> dict:
    return {"id": category.id, "name": category.name, "description": category.description}


@app.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    return {"items": [serialize_category(category) for category in db.query(Category).order_by(Category.name).all()]}


@app.get("/products")
def list_products(db: Session = Depends(get_db)):
    cached = redis_client.get(PRODUCT_CACHE_KEY)
    if cached:
        return {"source": "cache", "items": json.loads(cached)}

    categories_by_id = {category.id: category for category in db.query(Category).all()}
    products = [serialize_product(product, categories_by_id) for product in db.query(Product).all()]
    redis_client.setex(PRODUCT_CACHE_KEY, 120, json.dumps(products))
    return {"source": "database", "items": products}


@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    return serialize_product(product, categories_by_id)


@app.post("/products")
def create_product(
    payload: ProductRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if payload.category_id is not None:
        category = db.query(Category).filter(Category.id == payload.category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
    values = payload.model_dump()
    values["price"] = as_money(values["price"])
    product = Product(**values)
    db.add(product)
    db.commit()
    db.refresh(product)
    redis_client.delete(PRODUCT_CACHE_KEY)
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    return serialize_product(product, categories_by_id)


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.category_id is not None:
        category = db.query(Category).filter(Category.id == payload.category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

    values = payload.model_dump()
    values["price"] = as_money(values["price"])
    for field, value in values.items():
        setattr(product, field, value)
    db.add(product)
    db.commit()
    db.refresh(product)
    redis_client.delete(PRODUCT_CACHE_KEY)
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    return serialize_product(product, categories_by_id)


@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    redis_client.delete(PRODUCT_CACHE_KEY)
    return {"message": "Product deleted", "id": product_id}


@app.post("/categories")
def create_category(
    payload: CategoryRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    existing = db.query(Category).filter(Category.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    redis_client.delete(PRODUCT_CACHE_KEY)
    return serialize_category(category)
