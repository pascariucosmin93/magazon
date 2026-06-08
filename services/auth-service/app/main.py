import os
from hashlib import sha256
import secrets
from datetime import datetime, timedelta, timezone

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
import jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from shared.auth import current_user_claims
from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import publish_event
from shared.rate_limit import enforce_rate_limit
from shared.service_app import create_base_app

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@microshop.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
AUTH_COOKIE_NAME = "access_token"
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    address = Column(String(255), nullable=False, default="")
    reset_token_hash = Column(String(64), nullable=True)
    reset_token_expires_at = Column(DateTime, nullable=True)
    role = Column(String(50), nullable=False, default="customer")
    created_at = Column(DateTime, default=datetime.utcnow)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)
    address: str = Field(min_length=5, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=255)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=255)
    password: str = Field(min_length=8, max_length=255)


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
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
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


def require_admin(claims: dict = Depends(current_user_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "address": user.address,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def hash_password(value: str) -> str:
    return password_hasher.hash(value)


def legacy_hash_password(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def is_legacy_password_hash(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


def verify_password(plain_password: str, stored_hash: str) -> bool:
    if is_legacy_password_hash(stored_hash):
        return legacy_hash_password(plain_password) == stored_hash
    try:
        return password_hasher.verify(stored_hash, plain_password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    if is_legacy_password_hash(stored_hash):
        return True
    try:
        return password_hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": expire,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def set_auth_cookie(response: Response, token: str, request: Request) -> None:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=forwarded_proto == "https",
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


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

    existing_username = db.query(User).filter(User.username == normalized_username).first()
    if existing_username:
        raise HTTPException(status_code=409, detail="Username already exists")

    existing = db.query(User).filter(User.email == normalized_email).first()
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
    user = db.query(User).filter(User.email == normalized_email).first()
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
def session(claims: dict = Depends(current_user_claims)):
    return _serialize_claims(claims)


@app.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    users = db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
    return {"items": [serialize_user(user) for user in users], "total": len(users)}


@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
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

    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
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
