"""ECS-compatible JSON logging for all services."""
import json
import logging
import os
import traceback
from datetime import datetime, timezone


class ECSFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "log.level": record.levelname.lower(),
            "message": record.getMessage(),
            "service.name": os.getenv("SERVICE_NAME", "unknown"),
            "log.logger": record.name,
        }
        if record.exc_info:
            log_entry["error.stack_trace"] = "".join(traceback.format_exception(*record.exc_info))
            log_entry["error.type"] = record.exc_info[0].__name__ if record.exc_info[0] else None

        for key, value in record.__dict__.items():
            if key.startswith("ecs_"):
                log_entry[key[4:]] = value

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(ECSFormatter())
    root.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
