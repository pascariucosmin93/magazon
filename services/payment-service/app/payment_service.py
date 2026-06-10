from decimal import Decimal

from sqlalchemy.orm import Session

from payment_models import Payment, PaymentTransaction
from shared.money import as_money, money_json, money_minor_units


def record_transaction(
    db: Session,
    payment: Payment,
    transaction_type: str,
    status: str,
    amount: Decimal,
    provider_reference: str | None = None,
    provider_event_id: str | None = None,
) -> PaymentTransaction:
    transaction = PaymentTransaction(
        payment_id=payment.id,
        provider_event_id=provider_event_id,
        transaction_type=transaction_type,
        status=status,
        amount=as_money(amount),
        currency=payment.currency,
        provider_reference=provider_reference,
    )
    db.add(transaction)
    return transaction


async def refund(
    payment: Payment,
    db: Session,
    provider_event_id: str | None,
    *,
    stripe_client,
    stripe_secret_key: str,
    enqueue_event,
    publish_best_effort,
) -> None:
    refundable = as_money(payment.amount) - as_money(payment.refunded_amount)
    if refundable <= 0 or payment.status == "refunded":
        return
    if not stripe_secret_key or not payment.payment_intent_id:
        payment.status = "refund_pending"
        db.add(payment)
        db.commit()
        return

    stripe_refund = stripe_client.Refund.create(
        payment_intent=payment.payment_intent_id,
        amount=money_minor_units(refundable),
        metadata={"order_id": str(payment.order_id)},
    )
    payment.refunded_amount = as_money(payment.refunded_amount) + refundable
    payment.status = (
        "refunded"
        if payment.refunded_amount >= payment.amount
        else "partially_refunded"
    )
    db.add(payment)
    record_transaction(
        db,
        payment,
        "refund",
        payment.status,
        refundable,
        stripe_refund.get("id"),
        provider_event_id,
    )
    enqueue_event(
        db,
        "payment.refunded",
        {
            "order_id": payment.order_id,
            "status": payment.status,
            "amount": money_json(refundable),
        },
    )
    db.commit()
    await publish_best_effort()


async def finalize(
    payment: Payment,
    db: Session,
    provider_reference: str | None,
    provider_event_id: str | None,
    *,
    enqueue_event,
    publish_best_effort,
    refund_payment,
) -> None:
    if payment.status in {"refunded", "partially_refunded"}:
        return
    if payment.status == "completed":
        if provider_reference and not payment.payment_intent_id:
            payment.payment_intent_id = provider_reference
            db.add(payment)
            db.commit()
        return
    if payment.status == "refund_pending":
        if provider_reference:
            payment.payment_intent_id = provider_reference
            db.add(payment)
            db.commit()
        await refund_payment(payment, db, provider_event_id)
        return

    was_cancelled = payment.status == "cancelled"
    payment.status = "completed"
    if provider_reference:
        payment.payment_intent_id = provider_reference
    db.add(payment)
    record_transaction(
        db,
        payment,
        "payment",
        "completed",
        payment.amount,
        provider_reference,
        provider_event_id,
    )
    enqueue_event(
        db,
        "payment.completed",
        {
            "order_id": payment.order_id,
            "status": "completed",
            "amount": money_json(payment.amount),
        },
    )
    db.commit()
    await publish_best_effort()
    if was_cancelled:
        await refund_payment(payment, db)


async def refresh_from_stripe(
    payment: Payment,
    db: Session,
    *,
    stripe_client,
    stripe_secret_key: str,
    finalize_payment,
) -> None:
    if (
        not payment.checkout_session_id
        or payment.status == "completed"
        or not stripe_secret_key
    ):
        return
    session = stripe_client.checkout.Session.retrieve(payment.checkout_session_id)
    if session.get("payment_status") == "paid":
        await finalize_payment(payment, db, session.get("payment_intent"))
