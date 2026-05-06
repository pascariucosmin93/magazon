import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from shared.config import settings
from shared.kafka import start_producer, stop_producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_base_app(title: str, startup_hook=None, shutdown_hook=None, enable_kafka: bool = False):
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

    @app.get("/health")
    def health():
        return {"status": "ok", "service": settings.service_name}

    @app.get("/ready")
    def ready():
        return {"status": "ready", "service": settings.service_name}

    return app
