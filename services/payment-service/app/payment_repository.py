from sqlalchemy.orm import Session

from payment_models import Payment, PaymentTransaction


def get_payment_by_order(db: Session, order_id: int) -> Payment | None:
    return db.query(Payment).filter(Payment.order_id == order_id).first()


def list_payments(db: Session) -> list[Payment]:
    return db.query(Payment).all()


def list_transactions(db: Session, payment_id: int) -> list[PaymentTransaction]:
    return (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.payment_id == payment_id)
        .order_by(PaymentTransaction.created_at.desc(), PaymentTransaction.id.desc())
        .all()
    )


def find_payment_for_stripe_object(db: Session, stripe_object: dict) -> Payment | None:
    session_id = (
        stripe_object.get("id")
        if stripe_object.get("object") == "checkout.session"
        else None
    )
    if session_id:
        payment = (
            db.query(Payment)
            .filter(Payment.checkout_session_id == session_id)
            .first()
        )
        if payment:
            return payment

    payment_intent_id = stripe_object.get("payment_intent")
    if payment_intent_id:
        payment = (
            db.query(Payment)
            .filter(Payment.payment_intent_id == payment_intent_id)
            .first()
        )
        if payment:
            return payment

    order_id = (stripe_object.get("metadata") or {}).get("order_id")
    return get_payment_by_order(db, int(order_id)) if order_id else None
