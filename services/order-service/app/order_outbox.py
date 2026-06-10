import json
from datetime import datetime

from sqlalchemy.orm import Session

from order_models import OutboxEvent


def serialize_payload(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def enqueue(db: Session, topic: str, payload: dict) -> OutboxEvent:
    event = OutboxEvent(topic=topic, payload=serialize_payload(payload))
    db.add(event)
    return event


async def publish_pending_once(session_factory, publisher, logger, limit: int = 20) -> None:
    db = session_factory()
    try:
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.published.is_(False))
            .order_by(OutboxEvent.id.asc())
            .limit(limit)
            .all()
        )
        for event in events:
            event.publish_attempts += 1
            try:
                await publisher(event.topic, json.loads(event.payload))
                event.published = True
                event.published_at = datetime.utcnow()
                event.last_error = None
            except Exception as exc:
                event.last_error = str(exc)
                logger.warning(
                    "Outbox publish failed id=%s topic=%s error=%s",
                    event.id,
                    event.topic,
                    exc,
                )
                db.add(event)
                db.commit()
                continue
            db.add(event)
            db.commit()
    finally:
        db.close()
