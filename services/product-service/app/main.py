import os
import json
import re
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Session

from shared.auth import current_user_claims
from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.money import as_money, money_json
from shared.redis_client import redis_client
from shared.service_app import create_base_app


PRODUCT_CACHE_KEY = "products:all"
CATEGORY_ALIASES = {
    "accessories": "Accesorii",
    "accesories": "Accesorii",
    "accesorii": "Accesorii",
    "keyboards": "Periferice",
    "mice": "Periferice",
    "periferice": "Periferice",
}


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=80)
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
                    Category(
                        name="Periferice",
                        description="Tastaturi, mouse-uri, căști și camere web",
                    ),
                    Category(
                        name="Accesorii",
                        description="Dock-uri, cabluri, suporturi și accesorii pentru birou",
                    ),
                ]
            )
            db.commit()

        categories = {category.name: category.id for category in db.query(Category).all()}
        if db.query(Product).count() == 0:
            db.add_all(
                [
                    Product(
                        sku="KEYBOARD-MECH-001",
                        name="Mechanical Keyboard",
                        description="Tactile RGB keyboard",
                        price=119.0,
                        category_id=categories.get("Periferice"),
                    ),
                    Product(
                        sku="MOUSE-GAMING-001",
                        name="Gaming Mouse",
                        description="Lightweight wireless mouse",
                        price=79.0,
                        category_id=categories.get("Periferice"),
                    ),
                    Product(
                        sku="DOCK-USBC-001",
                        name="USB-C Dock",
                        description="Dock with HDMI and ethernet",
                        price=149.0,
                        category_id=categories.get("Accesorii"),
                    ),
                ]
            )
            db.commit()
    redis_client.delete(PRODUCT_CACHE_KEY)


app = create_base_app("product-service", startup_hook=startup, check_db=True, check_redis=True)


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


def serialize_product(product: Product, categories_by_id: dict[int, Category]) -> dict:
    category = categories_by_id.get(product.category_id)
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "price": money_json(product.price),
        "category_id": product.category_id,
        "category_name": category.name if category else None,
    }


def serialize_category(category: Category) -> dict:
    return {"id": category.id, "name": category.name, "description": category.description}


def normalize_sku(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "-", value.strip().upper()).strip("-")
    if not normalized:
        raise HTTPException(status_code=400, detail="SKU must contain letters or digits")
    return normalized[:80]


def generate_sku(name: str, product_id: int) -> str:
    base = normalize_sku(name)[:64]
    return f"{base}-{product_id}"


def canonical_category_name(value: str) -> str:
    name = " ".join(value.split())
    return CATEGORY_ALIASES.get(name.casefold(), name)


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
    requested_sku = values.pop("sku", None)
    if requested_sku:
        requested_sku = normalize_sku(requested_sku)
        if db.query(Product).filter(Product.sku == requested_sku).first():
            raise HTTPException(status_code=409, detail="SKU already exists")
    values["sku"] = requested_sku or f"TEMP-{uuid4()}"
    product = Product(**values)
    db.add(product)
    db.flush()
    if not requested_sku:
        product.sku = generate_sku(product.name, product.id)
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
    requested_sku = values.pop("sku", None)
    if requested_sku:
        requested_sku = normalize_sku(requested_sku)
        existing = db.query(Product).filter(
            Product.sku == requested_sku,
            Product.id != product_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="SKU already exists")
        values["sku"] = requested_sku
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
    name = canonical_category_name(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    existing = db.query(Category).filter(func.lower(Category.name) == name.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(name=name, description=payload.description.strip())
    db.add(category)
    db.commit()
    db.refresh(category)
    redis_client.delete(PRODUCT_CACHE_KEY)
    return serialize_category(category)
