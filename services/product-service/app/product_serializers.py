import json
from datetime import datetime
from typing import Any, cast

from shared.money import money_json

from product_models import Category, Product, ProductImportJob


def _product_id(product: Product) -> int:
    return cast(int, product.id)


def _product_sku(product: Product) -> str:
    return cast(str, product.sku)


def _product_name(product: Product) -> str:
    return cast(str, product.name)


def _product_description(product: Product) -> str:
    return cast(str, product.description)


def _product_category_id(product: Product) -> int | None:
    return cast(int | None, product.category_id)


def _product_archived_at(product: Product) -> datetime | None:
    return cast(datetime | None, product.archived_at)


def _set_product_sku(product: Product, value: str) -> None:
    cast(Any, product).sku = value


def _set_product_archived_at(product: Product, value: datetime | None) -> None:
    cast(Any, product).archived_at = value


def serialize_product(product: Product, categories_by_id: dict[int, Category]) -> dict:
    category = categories_by_id.get(_product_category_id(product))
    archived_at = _product_archived_at(product)
    return {
        "id": _product_id(product),
        "sku": _product_sku(product),
        "name": _product_name(product),
        "description": _product_description(product),
        "price": money_json(product.price),
        "category_id": _product_category_id(product),
        "category_name": category.name if category else None,
        "archived": archived_at is not None,
        "archived_at": archived_at.isoformat() if archived_at else None,
    }


def serialize_category(category: Category) -> dict:
    return {"id": category.id, "name": category.name, "description": category.description}


def serialize_import_job(job: ProductImportJob) -> dict:
    return {
        "id": job.id,
        "filename": job.filename,
        "summary": json.loads(cast(str, job.summary_json)),
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
