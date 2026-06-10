import os
import secrets
import sys
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    for module_name in (
        "auth_account_routes",
        "auth_repository",
        "auth_serializers",
        "auth_security",
        "auth_schemas",
        "auth_models",
    ):
        sys.modules.pop(module_name, None)

from auth_models import User, UserAddress  # noqa: E402
from auth_account_routes import (  # noqa: E402
    _address_summary,
    _current_user,
    _set_default_address,
    create_address,
    delete_address,
    get_profile,
    list_addresses,
    router as account_router,
    update_address,
    update_profile,
)
from auth_repository import get_user as repository_get_user  # noqa: E402
from auth_repository import get_user_by_email, get_user_by_username  # noqa: E402
from auth_repository import list_users as repository_list_users  # noqa: E402
from auth_schemas import (  # noqa: E402
    AddressRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ProfileUpdateRequest,
    RegisterRequest,
)
from auth_security import (  # noqa: E402
    clear_auth_cookie,
    create_access_token as _create_access_token,
    decode_access_token,
    hash_password,
    is_legacy_password_hash,
    legacy_hash_password,
    password_needs_rehash,
    set_auth_cookie as _set_auth_cookie,
    verify_password,
)
from auth_serializers import serialize_address, serialize_user  # noqa: E402
from shared.auth import current_user_claims  # noqa: E402
from shared.config import settings  # noqa: E402
from shared.db import Base, SessionLocal, get_db  # noqa: E402
from shared.kafka import publish_event  # noqa: E402
from shared.rate_limit import enforce_rate_limit  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

__all__ = [
    "_address_summary",
    "_current_user",
    "_set_default_address",
    "AddressRequest",
    "Base",
    "LoginRequest",
    "PasswordResetConfirmRequest",
    "PasswordResetRequest",
    "ProfileUpdateRequest",
    "RegisterRequest",
    "User",
    "UserAddress",
    "create_address",
    "delete_address",
    "get_profile",
    "is_legacy_password_hash",
    "legacy_hash_password",
    "list_addresses",
    "serialize_address",
    "serialize_user",
    "update_address",
    "update_profile",
]

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@microshop.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))


def _run_migrations() -> None:
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")


async def startup():
    _run_migrations()
    if not ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_PASSWORD must be set for auth-service startup")
    with SessionLocal() as db:
        admin = get_user_by_email(db, ADMIN_EMAIL)
        if not admin:
            db.add(
                User(
                    username="admin",
                    email=ADMIN_EMAIL,
                    password=hash_password(ADMIN_PASSWORD),
                    address="Admin Console",
                    role="admin",
                )
            )
            db.commit()
        else:
            changed = False
            if not getattr(admin, "username", None):
                admin.username = "admin"
                changed = True
            if not getattr(admin, "address", None):
                admin.address = "Admin Console"
                changed = True
            if admin.role != "admin":
                admin.role = "admin"
                changed = True
            if not verify_password(ADMIN_PASSWORD, admin.password) or password_needs_rehash(admin.password):
                admin.password = hash_password(ADMIN_PASSWORD)
                changed = True
            if changed:
                db.add(admin)
                db.commit()


app = create_base_app("auth-service", startup_hook=startup, enable_kafka=True, check_db=True)
app.include_router(account_router)


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


def create_access_token(user: User) -> str:
    return _create_access_token(user, ACCESS_TOKEN_EXPIRE_MINUTES)


def set_auth_cookie(response: Response, token: str, request: Request) -> None:
    _set_auth_cookie(response, token, request, ACCESS_TOKEN_EXPIRE_MINUTES)


@app.post("/register")
async def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"auth:register:{client_ip}", limit=10, window_seconds=300)
    normalized_username = payload.username.strip()
    normalized_address = payload.address.strip()
    normalized_email = payload.email.strip().lower()

    if not normalized_username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not normalized_address:
        raise HTTPException(status_code=400, detail="Address is required")

    existing_username = get_user_by_username(db, normalized_username)
    if existing_username:
        raise HTTPException(status_code=409, detail="Username already exists")

    existing = get_user_by_email(db, normalized_email)
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        username=normalized_username,
        email=normalized_email,
        password=hash_password(payload.password),
        address=normalized_address,
        role="customer",
    )
    db.add(user)
    db.flush()
    db.add(
        UserAddress(
            user_id=user.id,
            label="Acasă",
            recipient_name=user.username,
            line1=user.address,
            city="Nespecificat",
            country="RO",
            is_default=True,
        )
    )
    db.commit()
    db.refresh(user)

    await publish_event("user.created", {"user_id": user.id, "email": user.email})
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "address": user.address,
        "role": user.role,
    }


@app.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"auth:login:{client_ip}", limit=12, window_seconds=300)
    normalized_email = payload.email.strip().lower()
    user = get_user_by_email(db, normalized_email)
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if password_needs_rehash(user.password):
        user.password = hash_password(payload.password)
        db.commit()

    token = create_access_token(user)
    set_auth_cookie(response, token, request)
    return {"token": token, "user_id": user.id, "email": user.email, "role": user.role}


@app.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "Logged out"}


def _serialize_claims(claims: dict) -> dict:
    user_id = claims.get("sub")
    role = claims.get("role")
    email = claims.get("email")
    if not user_id or not role or not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"valid": True, "user_id": int(user_id), "role": role, "email": email}


@app.get("/session")
def session(
    claims: dict = Depends(current_user_claims),
    db: Session = Depends(get_db),
):
    user_id = int(claims["sub"])
    user = repository_get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {
        **_serialize_claims(claims),
        "username": user.username,
        "email": user.email,
        "address": user.address,
    }


@app.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    users = repository_list_users(db)
    return {"items": [serialize_user(user) for user in users], "total": len(users)}


@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    user = repository_get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        admin_user_id = int(admin.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    if user.id == admin_user_id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account")
    if user.role == "admin":
        raise HTTPException(status_code=409, detail="Administrator accounts cannot be deleted")

    db.delete(user)
    db.commit()
    return {"message": "User deleted", "user_id": user_id}


@app.post("/validate")
def validate_token(claims: dict = Depends(current_user_claims)):
    return _serialize_claims(claims)


@app.post("/password-reset/request")
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"auth:password-reset:{client_ip}", limit=5, window_seconds=900)

    user = get_user_by_email(db, payload.email.strip().lower())
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = sha256(token.encode("utf-8")).hexdigest()
        user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
        db.add(user)
        db.commit()
        await publish_event(
            "user.password_reset_requested",
            {
                "user_id": user.id,
                "email": user.email,
                "reset_token": token,
                "expires_in_minutes": PASSWORD_RESET_EXPIRE_MINUTES,
            },
        )

    return {"message": "If the account exists, reset instructions were generated."}


@app.post("/password-reset/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"auth:password-reset-confirm:{client_ip}", limit=10, window_seconds=900)

    token_hash = sha256(payload.token.encode("utf-8")).hexdigest()
    user = db.query(User).filter(User.reset_token_hash == token_hash).first()
    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password = hash_password(payload.password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.add(user)
    db.commit()
    return {"message": "Password updated successfully"}


@app.get("/validate/{token}")
def validate_token_legacy(token: str):
    return _serialize_claims(decode_access_token(token))
