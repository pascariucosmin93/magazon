import logging

from fastapi import HTTPException

from shared.redis_client import redis_client

logger = logging.getLogger(__name__)


def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    try:
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, window_seconds)
        if current > limit:
            raise HTTPException(status_code=429, detail="Too many requests")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Rate limit backend unavailable for key %s: %s", key, exc)
