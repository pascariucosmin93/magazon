import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from shared.config import settings
from shared.kafka import start_producer, stop_producer
from shared.logging import setup_logging

setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))

logger = logging.getLogger(__name__)


def create_base_app(
    title: str,
    startup_hook=None,
    shutdown_hook=None,
    enable_kafka: bool = False,
    check_db: bool = False,
    check_redis: bool = False,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if enable_kafka:
            await start_producer()
        if startup_hook:
            await startup_hook()
        yield
        if shutdown_hook:
            await shutdown_hook()
        if enable_kafka:
            await stop_producer()

    app = FastAPI(title=title, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "ecs_trace.id": request_id,
                "ecs_http.method": request.method,
                "ecs_url.path": request.url.path,
                "ecs_http.response.status_code": response.status_code,
                "ecs_event.duration_ms": duration_ms,
            },
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "service": settings.service_name}

    @app.get("/ready")
    def ready():
        failures: dict[str, str] = {}

        if check_db:
            try:
                from sqlalchemy import text
                from shared.db import engine
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:
                failures["db"] = str(exc)

        if check_redis:
            try:
                from shared.redis_client import redis_client
                redis_client.ping()
            except Exception as exc:
                failures["redis"] = str(exc)

        if failures:
            raise HTTPException(
                status_code=503,
                detail={"status": "not ready", "service": settings.service_name, **failures},
            )

        return {"status": "ready", "service": settings.service_name}

    return app
