from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from shared.db import Base


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
    archived_at = Column(DateTime, nullable=True)


class ProductImportJob(Base):
    __tablename__ = "product_import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    summary_json = Column(Text, nullable=False)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
