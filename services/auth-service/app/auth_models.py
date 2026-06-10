from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from shared.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    address = Column(String(255), nullable=False, default="")
    reset_token_hash = Column(String(64), nullable=True)
    reset_token_expires_at = Column(DateTime, nullable=True)
    role = Column(String(50), nullable=False, default="customer")
    created_at = Column(DateTime, default=datetime.utcnow)


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(80), nullable=False, default="Acasă")
    recipient_name = Column(String(120), nullable=False)
    line1 = Column(String(255), nullable=False)
    city = Column(String(120), nullable=False)
    postal_code = Column(String(20), nullable=False, default="")
    country = Column(String(2), nullable=False, default="RO")
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
