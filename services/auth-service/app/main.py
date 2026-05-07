import os
from hashlib import sha256
from datetime import datetime, timedelta, timezone

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException
import jwt
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import publish_event
from shared.service_app import create_base_app

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@microshop.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="customer")
    created_at = Column(DateTime, default=datetime.utcnow)


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


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
                    email=ADMIN_EMAIL,
                    password=hash_password(ADMIN_PASSWORD),
                    role="admin",
                )
            )
            db.commit()
        elif not verify_password(ADMIN_PASSWORD, admin.password) or password_needs_rehash(admin.password):
            admin.password = hash_password(ADMIN_PASSWORD)
            db.commit()


app = create_base_app("auth-service", startup_hook=startup, enable_kafka=True, check_db=True)


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


@app.post("/register")
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(email=payload.email, password=hash_password(payload.password), role="customer")
    db.add(user)
    db.commit()
    db.refresh(user)

    await publish_event("user.created", {"user_id": user.id, "email": user.email})
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if password_needs_rehash(user.password):
        user.password = hash_password(payload.password)
        db.commit()

    token = create_access_token(user)
    return {"token": token, "user_id": user.id, "email": user.email, "role": user.role}


@app.get("/validate/{token}")
def validate_token(token: str):
    claims = decode_access_token(token)
    user_id = claims.get("sub")
    role = claims.get("role")
    email = claims.get("email")
    if not user_id or not role or not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"valid": True, "user_id": int(user_id), "role": role, "email": email}
