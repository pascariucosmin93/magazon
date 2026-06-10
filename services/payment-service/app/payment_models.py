import os
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from shared.db import Base

PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stripe")
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "eur")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False, unique=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    currency = Column(String(10), nullable=False, default=PAYMENT_CURRENCY)
    provider = Column(String(50), nullable=False, default=PAYMENT_PROVIDER)
    status = Column(String(50), nullable=False, default="awaiting_payment")
    checkout_session_id = Column(String(255), nullable=True)
    checkout_url = Column(Text, nullable=True)
    payment_intent_id = Column(String(255), nullable=True, index=True)
    refunded_amount = Column(Numeric(12, 2), nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(
        Integer,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_event_id = Column(String(255), nullable=True, unique=True, index=True)
    transaction_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    currency = Column(String(10), nullable=False, default=PAYMENT_CURRENCY)
    provider_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaymentOutboxEvent(Base):
    __tablename__ = "payment_outbox_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    topic = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)
    published = Column(Boolean, nullable=False, default=False)
    publish_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    topic = Column(String(255), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
