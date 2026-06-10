from auth_models import User, UserAddress


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "address": user.address,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def serialize_address(address: UserAddress) -> dict:
    return {
        "id": address.id,
        "label": address.label,
        "recipient_name": address.recipient_name,
        "line1": address.line1,
        "city": address.city,
        "postal_code": address.postal_code,
        "country": address.country,
        "is_default": address.is_default,
    }
