import asyncio
import json
import logging
from contextlib import suppress
from typing import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from shared.config import settings

logger = logging.getLogger(__name__)

producer: AIOKafkaProducer | None = None


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


async def publish_event(topic: str, payload: dict):
    if producer is None:
        await start_producer()
    assert producer is not None
    await producer.send_and_wait(topic, payload)
    logger.info("Published topic=%s payload=%s", topic, payload)


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
    )
    await consumer.start()
    logger.info("%s consumer started for topics=%s", service_name, topics)
    try:
        async for message in consumer:
            await handler(message.topic, message.value)
    except asyncio.CancelledError:
        logger.info("%s consumer cancelled", service_name)
        raise
    finally:
        await consumer.stop()
