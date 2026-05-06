import secrets
from hashlib import sha256
from datetime import datetime

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from shared.db import Base, engine, get_db
from shared.kafka import publish_event
from shared.redis_client import redis_client
from shared.service_app import create_base_app


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


async def startup():
    Base.metadata.create_all(bind=engine)


app = create_base_app("auth-service", startup_hook=startup, enable_kafka=True)


def hash_password(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


@app.post("/register")
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(email=payload.email, password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    await publish_event("user.created", {"user_id": user.id, "email": user.email})
    return {"id": user.id, "email": user.email}


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
    redis_client.setex(f"session:{token}", 3600, str(user.id))
    return {"token": token, "user_id": user.id, "email": user.email}


@app.get("/validate/{token}")
def validate_token(token: str):
    user_id = redis_client.get(f"session:{token}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"valid": True, "user_id": int(user_id)}
