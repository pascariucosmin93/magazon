from datetime import datetime, timedelta, timezone
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request, Response
import jwt

from auth_models import User
from shared.config import settings

JWT_ALGORITHM = "HS256"
AUTH_COOKIE_NAME = "access_token"
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


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


def create_access_token(user: User, expire_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)
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


def set_auth_cookie(
    response: Response,
    token: str,
    request: Request,
    expire_minutes: int,
) -> None:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=forwarded_proto == "https",
        samesite="lax",
        max_age=expire_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
