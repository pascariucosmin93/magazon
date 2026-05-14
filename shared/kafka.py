import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4
from contextvars import ContextVar
from contextlib import suppress
from typing import Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from shared.config import settings

logger = logging.getLogger(__name__)

producer: AIOKafkaProducer | None = None
current_event_envelope: ContextVar[dict[str, Any] | None] = ContextVar(
    "current_event_envelope",
    default=None,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event_envelope(
    topic: str,
    payload: dict[str, Any],
    *,
    producer_name: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    event_id = str(uuid4())
    return {
        "event_id": event_id,
        "event_type": topic,
        "event_version": settings.kafka_event_version,
        "occurred_at": _utc_now_iso(),
        "correlation_id": correlation_id or event_id,
        "producer": producer_name or settings.service_name,
        "payload": payload,
    }


def normalize_event_message(topic: str, value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("payload"), dict) and value.get("event_id"):
        normalized = dict(value)
        normalized.setdefault("event_type", topic)
        normalized.setdefault("event_version", settings.kafka_event_version)
        normalized.setdefault("occurred_at", _utc_now_iso())
        normalized.setdefault("correlation_id", normalized["event_id"])
        normalized.setdefault("producer", "unknown")
        return normalized
    return {
        "event_id": str(uuid4()),
        "event_type": topic,
        "event_version": settings.kafka_event_version,
        "occurred_at": _utc_now_iso(),
        "correlation_id": str(uuid4()),
        "producer": "legacy-producer",
        "payload": value,
    }


async def _publish_raw(topic: str, message: dict[str, Any]) -> None:
    if producer is None:
        await start_producer()
    assert producer is not None
    await producer.send_and_wait(topic, message)


async def publish_to_dlq(
    topic: str,
    envelope: dict[str, Any],
    *,
    service_name: str,
    error: Exception,
    attempts: int,
) -> None:
    dlq_message = {
        "failed_at": _utc_now_iso(),
        "consumer": service_name,
        "source_topic": topic,
        "attempts": attempts,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "event": envelope,
    }
    await _publish_raw(f"{topic}{settings.kafka_dlq_suffix}", dlq_message)


async def process_event_with_retries(
    service_name: str,
    topic: str,
    value: dict[str, Any],
    handler: Callable[[str, dict], Awaitable[None]],
) -> None:
    envelope = normalize_event_message(topic, value)
    payload = envelope["payload"]
    last_error: Exception | None = None

    for attempt in range(1, settings.kafka_consumer_max_retries + 1):
        try:
            token = current_event_envelope.set(envelope)
            try:
                await handler(topic, payload)
            finally:
                current_event_envelope.reset(token)
            logger.info(
                "Processed topic=%s event_id=%s attempt=%s",
                topic,
                envelope["event_id"],
                attempt,
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Handler failed topic=%s event_id=%s attempt=%s/%s: %s",
                topic,
                envelope["event_id"],
                attempt,
                settings.kafka_consumer_max_retries,
                exc,
            )
            if attempt < settings.kafka_consumer_max_retries:
                await asyncio.sleep(settings.kafka_retry_backoff_seconds * (2 ** (attempt - 1)))

    assert last_error is not None
    await publish_to_dlq(
        topic,
        envelope,
        service_name=service_name,
        error=last_error,
        attempts=settings.kafka_consumer_max_retries,
    )
    logger.error(
        "Sent topic=%s event_id=%s to DLQ after %s attempts",
        topic,
        envelope["event_id"],
        settings.kafka_consumer_max_retries,
    )


def get_current_event() -> dict[str, Any] | None:
    return current_event_envelope.get()


async def start_producer():
    global producer
    if producer is None:
        candidate = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )
        try:
            await candidate.start()
        except Exception:
            with suppress(Exception):
                await candidate.stop()
            raise
        producer = candidate
        logger.info("Kafka producer started")


async def stop_producer():
    global producer
    if producer is not None:
        await producer.stop()
        producer = None


async def publish_event(topic: str, payload: dict[str, Any]):
    message = build_event_envelope(topic, payload)
    await _publish_raw(topic, message)
    logger.info("Published topic=%s event_id=%s", topic, message["event_id"])


async def consume_topics(
    service_name: str,
    topics: list[str],
    handler: Callable[[str, dict], Awaitable[None]],
):
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{service_name}-group",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    logger.info("%s consumer started for topics=%s", service_name, topics)
    try:
        async for message in consumer:
            await process_event_with_retries(service_name, message.topic, message.value, handler)
            await consumer.commit()
    except asyncio.CancelledError:
        logger.info("%s consumer cancelled", service_name)
        raise
    finally:
        await consumer.stop()
