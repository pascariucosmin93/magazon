import asyncio
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request
import requests
import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    for module_name in (
        "payment_outbox",
        "payment_repository",
        "payment_service",
        "payment_serializers",
        "payment_schemas",
        "payment_models",
    ):
        sys.modules.pop(module_name, None)

from payment_models import Payment, PaymentOutboxEvent, PaymentTransaction, ProcessedMessage  # noqa: E402
from payment_outbox import enqueue as enqueue_outbox_event  # noqa: E402
from payment_outbox import publish_pending_once as publish_outbox_once  # noqa: E402
from payment_outbox import serialize_payload as serialize_outbox_payload  # noqa: E402
from payment_repository import find_payment_for_stripe_object, get_payment_by_order  # noqa: E402
from payment_repository import list_payments as repository_list_payments  # noqa: E402
from payment_repository import list_transactions  # noqa: E402
from payment_schemas import CheckoutSessionRequest  # noqa: E402
from payment_service import finalize as finalize_payment_state  # noqa: E402
from payment_service import record_transaction  # noqa: E402
from payment_service import refresh_from_stripe  # noqa: E402
from payment_service import refund as refund_payment_state  # noqa: E402
from payment_serializers import serialize_payment, serialize_transaction  # noqa: E402
from shared.auth import current_user_claims, optional_user_claims, require_user_id  # noqa: E402
from shared.config import settings  # noqa: E402
from shared.db import Base, SessionLocal, get_db  # noqa: E402
from shared.kafka import consume_topics, get_current_event, publish_event  # noqa: E402
from shared.money import as_money, money_json, money_minor_units  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

__all__ = ["Base"]

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stripe")
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "eur")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = STRIPE_SECRET_KEY or None
logger = logging.getLogger(__name__)


def _request_headers(authorization: str | None = None, x_guest_token: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if x_guest_token:
        headers["X-Guest-Token"] = x_guest_token
    return headers


def _fetch_order_sync(
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


async def fetch_order(
    order_id: int,
    authorization: str | None = None,
    x_guest_token: str | None = None,
) -> dict:
    return await asyncio.to_thread(
        _fetch_order_sync,
        order_id,
        authorization,
        x_guest_token,
    )


def ensure_order_access(order: dict, claims: dict | None, x_guest_token: str | None) -> None:
    if order.get("guest"):
        if not x_guest_token:
            raise HTTPException(status_code=401, detail="Guest token required")
        return
    if not claims:
        raise HTTPException(status_code=401, detail="Authentication required")
    require_user_id(int(order["user_id"]), claims)


def ensure_payment_record(db: Session, order: dict) -> Payment:
    payment = get_payment_by_order(db, order["order_id"])
    if payment:
        return payment
    payment = Payment(
        order_id=order["order_id"],
        amount=as_money(order["total"]),
        currency=PAYMENT_CURRENCY,
        provider=PAYMENT_PROVIDER,
        status="awaiting_payment",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def _record_transaction(
    db: Session,
    payment: Payment,
    transaction_type: str,
    status: str,
    amount: Decimal,
    provider_reference: str | None = None,
    provider_event_id: str | None = None,
) -> PaymentTransaction:
    return record_transaction(
        db,
        payment,
        transaction_type,
        status,
        amount,
        provider_reference,
        provider_event_id,
    )


def _serialize_outbox_payload(payload: dict) -> str:
    return serialize_outbox_payload(payload)


def _enqueue_payment_event(db: Session, topic: str, payload: dict) -> PaymentOutboxEvent:
    return enqueue_outbox_event(db, topic, payload)


async def publish_pending_payment_events_once(limit: int = 20) -> None:
    await publish_outbox_once(SessionLocal, publish_event, logger, limit)


async def payment_outbox_publisher_loop() -> None:
    while True:
        await publish_pending_payment_events_once()
        await asyncio.sleep(1)


async def _publish_payment_outbox_best_effort() -> None:
    try:
        await publish_pending_payment_events_once(limit=5)
    except Exception as exc:
        logger.warning("Immediate payment outbox publish failed: %s", exc)


async def finalize_payment(
    payment: Payment,
    db: Session,
    provider_reference: str | None = None,
    provider_event_id: str | None = None,
) -> None:
    await finalize_payment_state(
        payment,
        db,
        provider_reference,
        provider_event_id,
        enqueue_event=_enqueue_payment_event,
        publish_best_effort=_publish_payment_outbox_best_effort,
        refund_payment=refund_payment,
    )


async def refund_payment(
    payment: Payment,
    db: Session,
    provider_event_id: str | None = None,
) -> None:
    await refund_payment_state(
        payment,
        db,
        provider_event_id,
        stripe_client=stripe,
        stripe_secret_key=STRIPE_SECRET_KEY,
        enqueue_event=_enqueue_payment_event,
        publish_best_effort=_publish_payment_outbox_best_effort,
    )


async def refresh_payment_from_stripe(payment: Payment, db: Session) -> None:
    await refresh_from_stripe(
        payment,
        db,
        stripe_client=stripe,
        stripe_secret_key=STRIPE_SECRET_KEY,
        finalize_payment=finalize_payment,
    )


def _normalize_base_url(value: str, *, setting_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail=f"Invalid {setting_name}")
    if parsed.params or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise HTTPException(status_code=400, detail=f"Invalid {setting_name}")
    return f"{parsed.scheme}://{parsed.netloc}"


def validate_return_base_url(return_base_url: str) -> str:
    if not settings.public_base_url:
        raise HTTPException(status_code=503, detail="PUBLIC_BASE_URL is not configured")
    normalized_configured = _normalize_base_url(
        settings.public_base_url,
        setting_name="PUBLIC_BASE_URL",
    )
    normalized_requested = _normalize_base_url(
        return_base_url,
        setting_name="return_base_url",
    )
    if normalized_requested != normalized_configured:
        raise HTTPException(status_code=400, detail="return_base_url must match PUBLIC_BASE_URL")
    return normalized_requested


def _payment_from_stripe_object(db: Session, stripe_object: dict) -> Payment | None:
    return find_payment_for_stripe_object(db, stripe_object)


consumer_task = None
payment_outbox_task = None


def _mark_event_processed(db: Session, topic: str) -> bool:
    event = get_current_event()
    if not event:
        return False

    event_id = event["event_id"]
    existing = db.query(ProcessedMessage).filter(ProcessedMessage.event_id == event_id).first()
    if existing:
        return True

    db.add(ProcessedMessage(event_id=event_id, topic=topic))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return True
    return False


async def handle_payment_event(topic: str, payload: dict):
    db = SessionLocal()
    try:
        if _mark_event_processed(db, topic):
            return

        if topic == "order.cancelled":
            payment = db.query(Payment).filter(Payment.order_id == payload["order_id"]).first()
            if not payment:
                db.commit()
                return
            if payment.status in {"completed", "refund_pending"}:
                await refund_payment(payment, db)
            elif payment.status not in {"refunded", "partially_refunded"}:
                payment.status = "cancelled"
                db.add(payment)
                _record_transaction(db, payment, "cancellation", "cancelled", Decimal("0.00"))
                db.commit()
            return

        if payload.get("status") != "reserved":
            db.commit()
            return

        existing = db.query(Payment).filter(Payment.order_id == payload["order_id"]).first()
        if existing:
            db.commit()
            return
        amount = sum(
            (as_money(item["price"]) * int(item["quantity"]) for item in payload.get("items", [])),
            Decimal("0.00"),
        )
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
    global consumer_task, payment_outbox_task
    consumer_task = asyncio.create_task(
        consume_topics(
            "payment-service", ["inventory.reserved", "order.cancelled"], handle_payment_event
        )
    )
    payment_outbox_task = asyncio.create_task(payment_outbox_publisher_loop())


async def shutdown():
    if payment_outbox_task:
        payment_outbox_task.cancel()
        try:
            await payment_outbox_task
        except asyncio.CancelledError:
            pass
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


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


@app.get("/payments")
def list_payments(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    items = repository_list_payments(db)
    return [serialize_payment(item) for item in items]


@app.get("/payments/orders/{order_id}")
async def get_payment_for_order(
    order_id: int,
    authorization: str | None = Header(default=None),
    x_guest_token: str | None = Header(default=None),
    claims: dict | None = Depends(optional_user_claims),
    db: Session = Depends(get_db),
):
    order = await fetch_order(order_id, authorization, x_guest_token)
    ensure_order_access(order, claims, x_guest_token)

    payment = get_payment_by_order(db, order_id)
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

    await refresh_payment_from_stripe(payment, db)
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

    order = await fetch_order(order_id, authorization, x_guest_token)
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
                    "product_data": {
                        "name": item.get("product_name") or f"Produs #{item['product_id']}",
                        "metadata": {
                            "product_id": str(item["product_id"]),
                            "sku": item.get("product_sku") or f"PRODUCT-{item['product_id']}",
                        },
                    },
                    "unit_amount": money_minor_units(item["price"]),
                },
                "quantity": int(item["quantity"]),
            }
        )

    checkout_session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        mode="payment",
        success_url=f"{return_base_url}/payment.html?order_id={order_id}&checkout=success",
        cancel_url=f"{return_base_url}/payment.html?order_id={order_id}&checkout=cancel",
        customer_email=order.get("customer_email") or None,
        metadata={"order_id": str(order_id)},
        payment_intent_data={"metadata": {"order_id": str(order_id)}},
        line_items=cast(Any, line_items),
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

    order = await fetch_order(order_id, authorization, x_guest_token)
    ensure_order_access(order, claims, x_guest_token)
    payment = get_payment_by_order(db, order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if not payment.checkout_session_id:
        raise HTTPException(status_code=409, detail="Checkout session not created yet")

    session = await asyncio.to_thread(
        stripe.checkout.Session.retrieve,
        payment.checkout_session_id,
    )
    if session.get("payment_status") == "paid":
        await finalize_payment(payment, db, session.get("payment_intent"))
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


@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Stripe signature is required")

    try:
        event = stripe.Webhook.construct_event(
            await request.body(), stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    event_id = event["id"]
    duplicate = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.provider_event_id == event_id)
        .first()
    )
    if duplicate:
        await _publish_payment_outbox_best_effort()
        return {"received": True, "duplicate": True}

    event_type = event["type"]
    stripe_object = event["data"]["object"]
    payment = _payment_from_stripe_object(db, stripe_object)
    if not payment:
        return {"received": True, "ignored": True}

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        if stripe_object.get("payment_status") == "paid":
            if payment.status == "completed":
                _record_transaction(
                    db,
                    payment,
                    "webhook",
                    "acknowledged",
                    Decimal("0.00"),
                    stripe_object.get("payment_intent"),
                    event_id,
                )
                db.commit()
            else:
                await finalize_payment(
                    payment, db, stripe_object.get("payment_intent"), event_id
                )
    elif event_type in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
        payment.status = "payment_failed"
        db.add(payment)
        _record_transaction(
            db,
            payment,
            "payment",
            "failed",
            payment.amount,
            stripe_object.get("payment_intent"),
            event_id,
        )
        _enqueue_payment_event(
            db,
            "payment.completed",
            {
                "order_id": payment.order_id,
                "status": "failed",
                "amount": money_json(payment.amount),
            },
        )
        db.commit()
        await _publish_payment_outbox_best_effort()
    elif event_type == "charge.refunded":
        previous_refunded = as_money(payment.refunded_amount)
        refunded = as_money(
            Decimal(str(stripe_object.get("amount_refunded", 0))) / Decimal("100")
        )
        payment.refunded_amount = max(as_money(payment.refunded_amount), refunded)
        payment.status = (
            "refunded" if payment.refunded_amount >= payment.amount else "partially_refunded"
        )
        db.add(payment)
        _record_transaction(
            db,
            payment,
            "refund_webhook",
            payment.status,
            refunded,
            stripe_object.get("id"),
            event_id,
        )
        if refunded > previous_refunded:
            _enqueue_payment_event(
                db,
                "payment.refunded",
                {
                    "order_id": payment.order_id,
                    "status": payment.status,
                    "amount": money_json(refunded - previous_refunded),
                },
            )
        db.commit()
        await _publish_payment_outbox_best_effort()

    return {"received": True}


@app.post("/payments/orders/{order_id}/refund")
async def refund_order_payment(
    order_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    payment = get_payment_by_order(db, order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status not in {"completed", "refund_pending", "partially_refunded"}:
        raise HTTPException(status_code=409, detail="Payment is not refundable")
    await refund_payment(payment, db)
    db.refresh(payment)
    return serialize_payment(payment)


@app.get("/payments/orders/{order_id}/transactions")
def list_payment_transactions(
    order_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    payment = get_payment_by_order(db, order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    transactions = list_transactions(db, payment.id)
    return {"items": [serialize_transaction(item) for item in transactions], "total": len(transactions)}
