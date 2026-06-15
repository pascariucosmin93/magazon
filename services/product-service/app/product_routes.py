import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from product_import import (
    PRODUCT_CACHE_KEY,
    _apply_import,
    _build_import_preview,
    _enforce_import_upload,
    _load_import_rows,
    build_import_template,
    build_products_export,
    canonical_category_name,
    generate_sku,
    normalize_sku,
)
from product_models import Category, Product, ProductImportJob
from product_schemas import CategoryRequest, ProductRequest
from product_serializers import (
    _product_id,
    _product_name,
    _set_product_archived_at,
    _set_product_sku,
    serialize_category,
    serialize_import_job,
    serialize_product,
)
from shared.auth import current_user_claims
from shared.db import get_db
from shared.money import as_money
from shared.rate_limit import enforce_rate_limit
from shared.redis_client import redis_client


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


router = APIRouter()


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    return {"items": [serialize_category(category) for category in db.query(Category).order_by(Category.name).all()]}


@router.get("/products")
def list_products(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    cached = redis_client.get(PRODUCT_CACHE_KEY)
    if cached and not include_archived:
        return {"source": "cache", "items": json.loads(cached)}

    categories_by_id = {category.id: category for category in db.query(Category).all()}
    query = db.query(Product)
    if not include_archived:
        query = query.filter(Product.archived_at.is_(None))
    products = [serialize_product(product, categories_by_id) for product in query.all()]
    if not include_archived:
        redis_client.setex(PRODUCT_CACHE_KEY, 120, json.dumps(products))
    return {"source": "database", "items": products}


@router.get("/products/export")
def export_products_excel(
    include_archived: bool = Query(default=True),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    query = db.query(Product)
    if not include_archived:
        query = query.filter(Product.archived_at.is_(None))

    payload = build_products_export(query.order_by(Product.id).all(), categories_by_id)
    return StreamingResponse(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="magazon-products.xlsx"'},
    )


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or product.archived_at is not None:
        raise HTTPException(status_code=404, detail="Product not found")
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    return serialize_product(product, categories_by_id)


@router.post("/products")
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
        _set_product_sku(product, generate_sku(_product_name(product), _product_id(product)))
    db.commit()
    db.refresh(product)
    redis_client.delete(PRODUCT_CACHE_KEY)
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    return serialize_product(product, categories_by_id)


@router.put("/products/{product_id}")
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
        existing = db.query(Product).filter(Product.sku == requested_sku, Product.id != product_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="SKU already exists")
        values["sku"] = requested_sku
    for field, value in values.items():
        setattr(product, field, value)
    _set_product_archived_at(product, None)
    db.add(product)
    db.commit()
    db.refresh(product)
    redis_client.delete(PRODUCT_CACHE_KEY)
    categories_by_id = {category.id: category for category in db.query(Category).all()}
    return serialize_product(product, categories_by_id)


@router.delete("/products/{product_id}")
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


@router.post("/categories")
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


@router.get("/products/import/template")
def download_import_template(_admin=Depends(require_admin)):
    payload = build_import_template()
    return StreamingResponse(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="magazon-import-template.xlsx"'},
    )


@router.get("/products/import/jobs")
def list_product_import_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    jobs = (
        db.query(ProductImportJob)
        .order_by(ProductImportJob.created_at.desc(), ProductImportJob.id.desc())
        .limit(limit)
        .all()
    )
    return {"items": [serialize_import_job(job) for job in jobs], "total": len(jobs)}


@router.post("/products/import/preview")
async def preview_product_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin_claims: dict = Depends(require_admin),
):
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"product:import-preview:{client_ip}", limit=20, window_seconds=900)
    file_bytes = await file.read()
    _enforce_import_upload(file, file_bytes)
    preview = _build_import_preview(_load_import_rows(file_bytes), db)
    return {"message": "Preview generated", **preview}


@router.post("/products/import/apply")
async def apply_product_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin_claims: dict = Depends(require_admin),
):
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"product:import-apply:{client_ip}", limit=10, window_seconds=900)
    file_bytes = await file.read()
    _enforce_import_upload(file, file_bytes)
    preview = _build_import_preview(_load_import_rows(file_bytes), db)
    created_by = admin_claims.get("email") or admin_claims.get("sub") or "admin"
    return _apply_import(preview, db, filename=file.filename or "upload.xlsx", created_by=created_by)
