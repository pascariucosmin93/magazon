from sqlalchemy.orm import Session

from order_models import Order


def get_order(db: Session, order_id: int) -> Order | None:
    return db.query(Order).filter(Order.id == order_id).first()


def list_orders(db: Session) -> list[Order]:
    return db.query(Order).order_by(Order.created_at.desc(), Order.id.desc()).all()


def list_orders_for_user(db: Session, user_id: int) -> list[Order]:
    return (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
