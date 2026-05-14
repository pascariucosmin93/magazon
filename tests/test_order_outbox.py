import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import clear_mappers, sessionmaker

from shared.db import Base
from shared import kafka as shared_kafka


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    clear_mappers()
    Base.registry.dispose()
    Base.metadata.clear()
    spec = spec_from_file_location(name, ROOT / relative_path)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def build_test_session(order_module):
    engine = create_engine("sqlite:///:memory:")
    order_module.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return testing_session


def test_create_order_writes_outbox_event(monkeypatch):
    order_module = load_module("order_main_outbox_create", "services/order-service/app/main.py")
    testing_session = build_test_session(order_module)
    monkeypatch.setattr(order_module, "SessionLocal", testing_session)
    monkeypatch.setattr(
        order_module,
        "fetch_product",
        lambda product_id: {"id": product_id, "price": 149.0},
    )

    async def fake_publish_pending_outbox_events_once(limit: int = 20):
        return None

    monkeypatch.setattr(order_module, "publish_pending_outbox_events_once", fake_publish_pending_outbox_events_once)

    db = testing_session()
    payload = order_module.OrderRequest(
        items=[order_module.OrderItemRequest(product_id=1, quantity=2)],
        customer_name="Jane Doe",
        customer_email="jane@example.com",
        shipping_address="Main Street 1",
    )

    result = asyncio.run(order_module.create_order(payload, db=db, claims=None))

    outbox_event = db.query(order_module.OutboxEvent).one()
    assert result["status"] == "created"
    assert result["total"] == 298.0
    assert outbox_event.topic == "order.created"
    assert outbox_event.published is False


def test_publish_pending_outbox_events_marks_rows_published(monkeypatch):
    order_module = load_module("order_main_outbox_publish", "services/order-service/app/main.py")
    testing_session = build_test_session(order_module)
    monkeypatch.setattr(order_module, "SessionLocal", testing_session)

    published = []

    async def fake_publish_event(topic, payload):
        published.append((topic, payload))

    monkeypatch.setattr(order_module, "publish_event", fake_publish_event)

    db = testing_session()
    db.add(
        order_module.OutboxEvent(
            topic="order.created",
            payload=order_module._serialize_outbox_payload({"order_id": 7, "total": 100.0, "items": []}),
        )
    )
    db.commit()

    asyncio.run(order_module.publish_pending_outbox_events_once())

    stored = db.query(order_module.OutboxEvent).one()
    assert published == [("order.created", {"order_id": 7, "total": 100.0, "items": []})]
    assert stored.published is True
    assert stored.publish_attempts == 1
    assert stored.published_at is not None
    assert stored.last_error is None


def test_publish_pending_outbox_events_records_publish_error(monkeypatch):
    order_module = load_module("order_main_outbox_error", "services/order-service/app/main.py")
    testing_session = build_test_session(order_module)
    monkeypatch.setattr(order_module, "SessionLocal", testing_session)

    async def failing_publish_event(topic, payload):
        raise RuntimeError("kafka unavailable")

    monkeypatch.setattr(order_module, "publish_event", failing_publish_event)

    db = testing_session()
    db.add(
        order_module.OutboxEvent(
            topic="order.created",
            payload=order_module._serialize_outbox_payload({"order_id": 8, "total": 50.0, "items": []}),
        )
    )
    db.commit()

    asyncio.run(order_module.publish_pending_outbox_events_once())

    stored = db.query(order_module.OutboxEvent).one()
    assert stored.published is False
    assert stored.publish_attempts == 1
    assert "kafka unavailable" in stored.last_error


def test_handle_event_is_idempotent_for_duplicate_event(monkeypatch):
    order_module = load_module("order_main_idempotency", "services/order-service/app/main.py")
    testing_session = build_test_session(order_module)
    monkeypatch.setattr(order_module, "SessionLocal", testing_session)

    db = testing_session()
    order = order_module.Order(status="created", total=10.0)
    db.add(order)
    db.commit()
    db.refresh(order)

    token = shared_kafka.current_event_envelope.set(
        {
            "event_id": "evt-dup-1",
            "event_type": "payment.completed",
            "payload": {"order_id": order.id, "status": "completed"},
        }
    )
    try:
        asyncio.run(order_module.handle_event("payment.completed", {"order_id": order.id, "status": "completed"}))
        asyncio.run(order_module.handle_event("payment.completed", {"order_id": order.id, "status": "failed"}))
    finally:
        shared_kafka.current_event_envelope.reset(token)

    stored_order = db.query(order_module.Order).filter(order_module.Order.id == order.id).one()
    processed = db.query(order_module.ProcessedMessage).all()
    assert stored_order.status == "paid"
    assert len(processed) == 1
