from payment_models import Payment, PaymentTransaction
from shared.money import money_json


def serialize_payment(payment: Payment) -> dict:
    return {
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": money_json(payment.amount),
        "refunded_amount": money_json(payment.refunded_amount),
        "currency": payment.currency,
        "provider": payment.provider,
        "checkout_session_id": payment.checkout_session_id,
        "checkout_url": payment.checkout_url,
        "payment_intent_id": payment.payment_intent_id,
    }


def serialize_transaction(transaction: PaymentTransaction) -> dict:
    return {
        "id": transaction.id,
        "payment_id": transaction.payment_id,
        "provider_event_id": transaction.provider_event_id,
        "type": transaction.transaction_type,
        "status": transaction.status,
        "amount": money_json(transaction.amount),
        "currency": transaction.currency,
        "provider_reference": transaction.provider_reference,
        "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
    }
