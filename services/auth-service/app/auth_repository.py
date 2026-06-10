from sqlalchemy.orm import Session

from auth_models import User, UserAddress


def get_user(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()


def get_address(db: Session, user_id: int, address_id: int) -> UserAddress | None:
    return (
        db.query(UserAddress)
        .filter(UserAddress.id == address_id, UserAddress.user_id == user_id)
        .first()
    )


def list_addresses(db: Session, user_id: int) -> list[UserAddress]:
    return (
        db.query(UserAddress)
        .filter(UserAddress.user_id == user_id)
        .order_by(UserAddress.is_default.desc(), UserAddress.created_at.asc())
        .all()
    )
