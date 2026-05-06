import os
import secrets
from hashlib import sha256
from datetime import datetime

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import Base, SessionLocal, get_db
from shared.kafka import publish_event
from shared.redis_client import redis_client
from shared.service_app import create_base_app


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
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == "admin@microshop.local").first()
        if not admin:
            db.add(
                User(
                    email="admin@microshop.local",
                    password=hash_password("admin123"),
                    role="admin",
                )
            )
            db.commit()


app = create_base_app("auth-service", startup_hook=startup, enable_kafka=True, check_db=True, check_redis=True)


def hash_password(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


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
    user = (
        db.query(User)
        .filter(User.email == payload.email, User.password == hash_password(payload.password))
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = secrets.token_hex(16)
    redis_client.setex(f"session:{token}", 3600, f"{user.id}:{user.role}:{user.email}")
    return {"token": token, "user_id": user.id, "email": user.email, "role": user.role}


@app.get("/validate/{token}")
def validate_token(token: str):
    session_data = redis_client.get(f"session:{token}")
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id, role, email = session_data.split(":", 2)
    return {"valid": True, "user_id": int(user_id), "role": role, "email": email}
