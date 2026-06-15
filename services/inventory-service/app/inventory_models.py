from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from shared.db import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, unique=True, nullable=False, index=True)
    stock = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, unique=True, nullable=False, index=True)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    topic = Column(String(255), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
