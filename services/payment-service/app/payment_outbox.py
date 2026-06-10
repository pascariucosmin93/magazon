import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from payment_models import PaymentOutboxEvent


def serialize_payload(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def enqueue(db: Session, topic: str, payload: dict) -> PaymentOutboxEvent:
    event = PaymentOutboxEvent(
        event_id=str(uuid4()),
        topic=topic,
        payload=serialize_payload(payload),
    )
    db.add(event)
    return event


async def publish_pending_once(session_factory, publisher, logger, limit: int = 20) -> None:
    db = session_factory()
    attempted_ids: list[int] = []
    try:
        for _ in range(limit):
            query = db.query(PaymentOutboxEvent).filter(
                PaymentOutboxEvent.published.is_(False)
            )
            if attempted_ids:
                query = query.filter(PaymentOutboxEvent.id.notin_(attempted_ids))
            event = (
                query.order_by(PaymentOutboxEvent.id.asc())
                .with_for_update(skip_locked=True)
                .first()
            )
            if not event:
                break
            attempted_ids.append(event.id)
            event.publish_attempts += 1
            try:
                await publisher(
                    event.topic,
                    json.loads(event.payload),
                    event_id=event.event_id,
                )
                event.published = True
                event.published_at = datetime.utcnow()
                event.last_error = None
            except Exception as exc:
                event.last_error = str(exc)
                logger.warning(
                    "Payment outbox publish failed id=%s topic=%s error=%s",
                    event.id,
                    event.topic,
                    exc,
                )
            db.add(event)
            db.commit()
    finally:
        db.close()
