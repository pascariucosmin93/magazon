from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth_models import User, UserAddress
from auth_repository import get_address, get_user, list_addresses as repository_list_addresses
from auth_schemas import AddressRequest, ProfileUpdateRequest
from auth_serializers import serialize_address, serialize_user
from shared.auth import current_user_claims
from shared.db import get_db

router = APIRouter()


def _current_user(db: Session, claims: dict) -> User:
    try:
        user_id = int(claims.get("sub"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _address_summary(address: UserAddress) -> str:
    parts = [address.line1, address.city, address.postal_code, address.country]
    return ", ".join(part for part in parts if part)


def _set_default_address(db: Session, user: User, address: UserAddress) -> None:
    db.query(UserAddress).filter(
        UserAddress.user_id == user.id,
        UserAddress.id != address.id,
    ).update({UserAddress.is_default: False}, synchronize_session=False)
    address.is_default = True
    user.address = _address_summary(address)
    db.add_all([user, address])


@router.get("/profile")
def get_profile(
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    return serialize_user(_current_user(db, claims))


@router.put("/profile")
def update_profile(
    payload: ProfileUpdateRequest,
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    user = _current_user(db, claims)
    username = payload.username.strip()
    email = payload.email.strip().lower()
    username_owner = (
        db.query(User)
        .filter(User.username == username, User.id != user.id)
        .first()
    )
    if username_owner:
        raise HTTPException(status_code=409, detail="Username already exists")
    email_owner = (
        db.query(User)
        .filter(User.email == email, User.id != user.id)
        .first()
    )
    if email_owner:
        raise HTTPException(status_code=409, detail="Email already exists")
    user.username = username
    user.email = email
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.get("/addresses")
def list_addresses(
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    user = _current_user(db, claims)
    addresses = repository_list_addresses(db, user.id)
    return {
        "items": [serialize_address(item) for item in addresses],
        "total": len(addresses),
    }


@router.post("/addresses")
def create_address(
    payload: AddressRequest,
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    user = _current_user(db, claims)
    has_addresses = (
        db.query(UserAddress).filter(UserAddress.user_id == user.id).first()
        is not None
    )
    address = UserAddress(
        user_id=user.id,
        label=payload.label.strip(),
        recipient_name=payload.recipient_name.strip(),
        line1=payload.line1.strip(),
        city=payload.city.strip(),
        postal_code=payload.postal_code.strip(),
        country=payload.country.strip().upper(),
        is_default=payload.is_default or not has_addresses,
    )
    db.add(address)
    db.flush()
    if address.is_default:
        _set_default_address(db, user, address)
    db.commit()
    db.refresh(address)
    return serialize_address(address)


@router.put("/addresses/{address_id}")
def update_address(
    address_id: int,
    payload: AddressRequest,
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    user = _current_user(db, claims)
    address = get_address(db, user.id, address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    for field in ("label", "recipient_name", "line1", "city", "postal_code", "country"):
        value = getattr(payload, field).strip()
        setattr(address, field, value.upper() if field == "country" else value)
    if payload.is_default:
        _set_default_address(db, user, address)
    elif address.is_default:
        user.address = _address_summary(address)
        db.add(user)
    db.add(address)
    db.commit()
    db.refresh(address)
    return serialize_address(address)


@router.delete("/addresses/{address_id}")
def delete_address(
    address_id: int,
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    user = _current_user(db, claims)
    address = get_address(db, user.id, address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    was_default = address.is_default
    db.delete(address)
    db.flush()
    if was_default:
        replacement = (
            db.query(UserAddress)
            .filter(UserAddress.user_id == user.id)
            .order_by(UserAddress.created_at.asc())
            .first()
        )
        if replacement:
            _set_default_address(db, user, replacement)
        else:
            user.address = ""
            db.add(user)
    db.commit()
    return {"message": "Address deleted", "address_id": address_id}
