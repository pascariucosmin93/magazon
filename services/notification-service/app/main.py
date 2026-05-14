import asyncio
import logging

from shared.kafka import consume_topics, get_current_event, publish_event
from shared.redis_client import redis_client
from shared.service_app import create_base_app

logger = logging.getLogger(__name__)
consumer_task = None
PROCESSED_MESSAGE_TTL_SECONDS = 7 * 24 * 60 * 60


def _processed_event_key(event_id: str) -> str:
    return f"notification-service:processed-events:{event_id}"


async def handle_notifications(topic: str, payload: dict):
    event = get_current_event()
    if event:
        marker_created = redis_client.set(
            _processed_event_key(event["event_id"]),
            topic,
            nx=True,
            ex=PROCESSED_MESSAGE_TTL_SECONDS,
        )
        if not marker_created:
            return

    message = {"source_topic": topic, "payload": payload}
    logger.info("Notification received: %s", message)
    await publish_event("notification.sent", message)


async def startup():
    global consumer_task
    consumer_task = asyncio.create_task(
        consume_topics(
            "notification-service",
            ["user.created", "user.password_reset_requested", "order.created", "payment.completed"],
            handle_notifications,
        )
    )


async def shutdown():
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = create_base_app(
    "notification-service",
    startup_hook=startup,
    shutdown_hook=shutdown,
    enable_kafka=True,
    check_redis=True,
)


@app.get("/notifications/info")
def notifications_info():
    return {
        "topics": [
            "user.created",
            "user.password_reset_requested",
            "order.created",
            "payment.completed",
            "notification.sent",
        ],
        "mode": "log-only",
    }
