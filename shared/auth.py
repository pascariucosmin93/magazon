from fastapi import Cookie, Header, HTTPException
import jwt

from shared.config import settings

JWT_ALGORITHM = "HS256"


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def bearer_token(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> str:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Bearer token required")
        return token.strip()
    if access_token:
        return access_token.strip()
    raise HTTPException(status_code=401, detail="Authentication required")


def current_user_claims(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> dict:
    return decode_access_token(bearer_token(authorization, access_token))


def optional_user_claims(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> dict | None:
    if not authorization and not access_token:
        return None
    return decode_access_token(bearer_token(authorization, access_token))


def require_user_id(user_id: int, claims: dict) -> None:
    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        token_user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Token user does not match requested user")
