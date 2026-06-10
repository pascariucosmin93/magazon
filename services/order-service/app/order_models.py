from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from shared.db import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String(120), nullable=True)
    customer_email = Column(String(255), nullable=True)
    shipping_address = Column(String(255), nullable=True)
    guest_token = Column(String(120), nullable=True, unique=True, index=True)
    status = Column(String(50), default="created", nullable=False)
    total = Column(Numeric(12, 2), default=0, nullable=False)
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False, default="Unknown product")
    product_sku = Column(String(80), nullable=False, default="UNKNOWN")
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    order = relationship("Order", back_populates="items")


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    topic = Column(String(255), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)
    published = Column(Boolean, nullable=False, default=False)
    publish_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)
