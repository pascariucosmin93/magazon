import asyncio
import os
from datetime import datetime
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel
import requests
import stripe
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Session

from shared.auth import optional_user_claims, require_user_id
from shared.db import Base, SessionLocal, get_db
from shared.kafka import consume_topics, publish_event
from shared.service_app import create_base_app

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stripe")
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "eur")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
stripe.api_key = STRIPE_SECRET_KEY or None


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False, unique=True, index=True)
    amount = Column(Float, nullable=False, default=0)
    currency = Column(String(10), nullable=False, default=PAYMENT_CURRENCY)
    provider = Column(String(50), nullable=False, default=PAYMENT_PROVIDER)
    status = Column(String(50), nullable=False, default="awaiting_payment")
    checkout_session_id = Column(String(255), nullable=True)
    checkout_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CheckoutSessionRequest(BaseModel):
    return_base_url: str


def _request_headers(authorization: str | None = None, x_guest_token: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if x_guest_token:
        headers["X-Guest-Token"] = x_guest_token
    return headers


def fetch_order(
    order_id: int,
    authorization: str | None = None,
    x_guest_token: str | None = None,
) -> dict:
    try:
        response = requests.get(
            f"{ORDER_SERVICE_URL}/orders/{order_id}",
            headers=_request_headers(authorization, x_guest_token),
            timeout=5,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Order service unavailable") from exc

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Authentication required for payment")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Order not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Order service returned an error")
    return response.json()


def ensure_order_access(order: dict, claims: dict | None, x_guest_token: str | None) -> None:
    if order.get("guest"):
        if not x_guest_token:
            raise HTTPException(status_code=401, detail="Guest token required")
        return
    if not claims:
        raise HTTPException(status_code=401, detail="Authentication required")
    require_user_id(int(order["user_id"]), claims)


def ensure_payment_record(db: Session, order: dict) -> Payment:
    payment = db.query(Payment).filter(Payment.order_id == order["order_id"]).first()
    if payment:
        return payment
    payment = Payment(
        order_id=order["order_id"],
        amount=float(order["total"]),
        currency=PAYMENT_CURRENCY,
        provider=PAYMENT_PROVIDER,
        status="awaiting_payment",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


async def finalize_payment(payment: Payment) -> None:
    if payment.status == "completed":
        return
    payment.status = "completed"
    await publish_event(
        "payment.completed",
        {"order_id": payment.order_id, "status": "completed", "amount": payment.amount},
    )


async def refresh_payment_from_stripe(payment: Payment) -> None:
    if not payment.checkout_session_id or payment.status == "completed" or not STRIPE_SECRET_KEY:
        return
    session = stripe.checkout.Session.retrieve(payment.checkout_session_id)
    if session.get("payment_status") == "paid":
        await finalize_payment(payment)


def validate_return_base_url(return_base_url: str) -> str:
    parsed = urlparse(return_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid return_base_url")
    return return_base_url.rstrip("/")


def serialize_payment(payment: Payment) -> dict:
    return {
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": payment.amount,
        "currency": payment.currency,
        "provider": payment.provider,
        "checkout_session_id": payment.checkout_session_id,
        "checkout_url": payment.checkout_url,
    }


consumer_task = None


async def handle_inventory(topic: str, payload: dict):
    if payload.get("status") != "reserved":
        return

    db = SessionLocal()
    try:
        existing = db.query(Payment).filter(Payment.order_id == payload["order_id"]).first()
        if existing:
            return
        amount = sum(item["price"] * item["quantity"] for item in payload.get("items", []))
        payment = Payment(
            order_id=payload["order_id"],
            amount=amount,
            currency=PAYMENT_CURRENCY,
            provider=PAYMENT_PROVIDER,
            status="awaiting_payment",
        )
        db.add(payment)
        db.commit()
    finally:
        db.close()


async def startup():
    global consumer_task
    consumer_task = asyncio.create_task(
        consume_topics("payment-service", ["inventory.reserved"], handle_inventory)
    )


async def shutdown():
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = create_base_app(
    "payment-service",
    startup_hook=startup,
    shutdown_hook=shutdown,
    enable_kafka=True,
    check_db=True,
)


@app.get("/payments")
def list_payments(db: Session = Depends(get_db)):
    items = db.query(Payment).all()
    return [serialize_payment(item) for item in items]


@app.get("/payments/orders/{order_id}")
async def get_payment_for_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    x_guest_token: str | None = Header(default=None),
    claims: dict | None = Depends(optional_user_claims),
    db: Session = Depends(get_db),
):
    order = fetch_order(order_id, authorization, x_guest_token)
    ensure_order_access(order, claims, x_guest_token)

    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if not payment:
        if order["status"] == "inventory_failed":
            return {
                "order_id": order_id,
                "status": "inventory_failed",
                "amount": float(order["total"]),
                "currency": PAYMENT_CURRENCY,
                "provider": PAYMENT_PROVIDER,
                "checkout_session_id": None,
                "checkout_url": None,
            }
        return {
            "order_id": order_id,
            "status": "waiting_for_inventory",
            "amount": float(order["total"]),
            "currency": PAYMENT_CURRENCY,
            "provider": PAYMENT_PROVIDER,
            "checkout_session_id": None,
            "checkout_url": None,
        }

    await refresh_payment_from_stripe(payment)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment)


@app.post("/payments/orders/{order_id}/checkout-session")
async def create_checkout_session(
    order_id: int,
    payload: CheckoutSessionRequest,
    authorization: str | None = Header(default=None),
    x_guest_token: str | None = Header(default=None),
    claims: dict | None = Depends(optional_user_claims),
    db: Session = Depends(get_db),
):
    if PAYMENT_PROVIDER != "stripe":
        raise HTTPException(status_code=501, detail="Configured payment provider is not supported")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")

    order = fetch_order(order_id, authorization, x_guest_token)
    ensure_order_access(order, claims, x_guest_token)
    if order["status"] == "paid":
        payment = ensure_payment_record(db, order)
        payment.status = "completed"
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return serialize_payment(payment)
    if order["status"] == "inventory_failed":
        raise HTTPException(status_code=409, detail="Order failed because inventory could not be reserved")
    if order["status"] != "inventory_reserved":
        raise HTTPException(status_code=409, detail="Order is not ready for payment yet")

    payment = ensure_payment_record(db, order)
    if payment.status == "completed":
        return serialize_payment(payment)

    if payment.checkout_session_id and payment.checkout_url:
        return serialize_payment(payment)

    return_base_url = validate_return_base_url(payload.return_base_url)
    line_items = []
    for item in order.get("items", []):
        line_items.append(
            {
                "price_data": {
                    "currency": PAYMENT_CURRENCY,
                    "product_data": {"name": f"Produs #{item['product_id']}"},
                    "unit_amount": int(round(float(item["price"]) * 100)),
                },
                "quantity": int(item["quantity"]),
            }
        )

    checkout_session = stripe.checkout.Session.create(
        mode="payment",
        success_url=f"{return_base_url}/payment.html?order_id={order_id}&checkout=success",
        cancel_url=f"{return_base_url}/payment.html?order_id={order_id}&checkout=cancel",
        customer_email=order.get("customer_email") or None,
        metadata={"order_id": str(order_id)},
        line_items=line_items,
    )

    payment.checkout_session_id = checkout_session["id"]
    payment.checkout_url = checkout_session["url"]
    payment.status = "checkout_created"
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment)


@app.post("/payments/orders/{order_id}/confirm")
async def confirm_checkout_session(
    order_id: int,
    authorization: str | None = Header(default=None),
    x_guest_token: str | None = Header(default=None),
    claims: dict | None = Depends(optional_user_claims),
    db: Session = Depends(get_db),
):
    if PAYMENT_PROVIDER != "stripe":
        raise HTTPException(status_code=501, detail="Configured payment provider is not supported")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")

    order = fetch_order(order_id, authorization, x_guest_token)
    ensure_order_access(order, claims, x_guest_token)
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if not payment.checkout_session_id:
        raise HTTPException(status_code=409, detail="Checkout session not created yet")

    session = stripe.checkout.Session.retrieve(payment.checkout_session_id)
    if session.get("payment_status") == "paid":
        await finalize_payment(payment)
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return serialize_payment(payment)

    if session.get("status") == "expired":
        payment.status = "payment_failed"
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return serialize_payment(payment)

    return {
        **serialize_payment(payment),
        "stripe_status": session.get("status"),
        "stripe_payment_status": session.get("payment_status"),
    }
