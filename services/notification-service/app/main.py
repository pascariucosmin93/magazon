import asyncio
import logging

from shared.kafka import consume_topics, publish_event
from shared.service_app import create_base_app

logger = logging.getLogger(__name__)
consumer_task = None


async def handle_notifications(topic: str, payload: dict):
    message = {"source_topic": topic, "payload": payload}
    logger.info("Notification received: %s", message)
    await publish_event("notification.sent", message)


async def startup():
    global consumer_task
    consumer_task = asyncio.create_task(
        consume_topics(
            "notification-service",
            ["user.created", "order.created", "payment.completed"],
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
)


@app.get("/notifications/info")
def notifications_info():
    return {
        "topics": ["user.created", "order.created", "payment.completed", "notification.sent"],
        "mode": "log-only",
    }
