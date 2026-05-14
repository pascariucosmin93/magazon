import asyncio

from shared import kafka


def test_build_event_envelope_wraps_payload():
    envelope = kafka.build_event_envelope("order.created", {"order_id": 1}, producer_name="order-service")

    assert envelope["event_type"] == "order.created"
    assert envelope["producer"] == "order-service"
    assert envelope["payload"]["order_id"] == 1
    assert envelope["event_version"] == 1
    assert envelope["event_id"]
    assert envelope["correlation_id"]


def test_normalize_event_message_preserves_existing_envelope():
    message = {
        "event_id": "evt-1",
        "event_type": "order.created",
        "correlation_id": "corr-1",
        "payload": {"order_id": 7},
    }

    normalized = kafka.normalize_event_message("order.created", message)

    assert normalized["event_id"] == "evt-1"
    assert normalized["correlation_id"] == "corr-1"
    assert normalized["payload"]["order_id"] == 7


def test_process_event_with_retries_sends_to_dlq_after_failures(monkeypatch):
    attempts = []
    dlq_calls = []

    async def failing_handler(topic, payload):
        attempts.append((topic, payload))
        raise RuntimeError("boom")

    async def fake_publish_to_dlq(topic, envelope, *, service_name, error, attempts):
        dlq_calls.append(
            {
                "topic": topic,
                "event_id": envelope["event_id"],
                "service_name": service_name,
                "error": str(error),
                "attempts": attempts,
            }
        )

    monkeypatch.setattr(kafka.settings, "kafka_consumer_max_retries", 2)
    monkeypatch.setattr(kafka.settings, "kafka_retry_backoff_seconds", 0)
    monkeypatch.setattr(kafka, "publish_to_dlq", fake_publish_to_dlq)

    asyncio.run(
        kafka.process_event_with_retries(
            "inventory-service",
            "order.created",
            {"order_id": 9},
            failing_handler,
        )
    )

    assert len(attempts) == 2
    assert dlq_calls[0]["topic"] == "order.created"
    assert dlq_calls[0]["service_name"] == "inventory-service"
    assert dlq_calls[0]["attempts"] == 2


def test_process_event_with_retries_accepts_legacy_payload(monkeypatch):
    received = []

    async def handler(topic, payload):
        received.append((topic, payload))

    monkeypatch.setattr(kafka.settings, "kafka_consumer_max_retries", 2)

    asyncio.run(
        kafka.process_event_with_retries(
            "payment-service",
            "inventory.reserved",
            {"order_id": 12, "status": "reserved"},
            handler,
        )
    )

    assert received == [("inventory.reserved", {"order_id": 12, "status": "reserved"})]


def test_process_event_with_retries_exposes_current_event(monkeypatch):
    seen = {}

    async def handler(topic, payload):
        event = kafka.get_current_event()
        seen["topic"] = topic
        seen["payload"] = payload
        seen["event_id"] = event["event_id"] if event else None

    monkeypatch.setattr(kafka.settings, "kafka_consumer_max_retries", 1)

    asyncio.run(
        kafka.process_event_with_retries(
            "order-service",
            "payment.completed",
            {"event_id": "evt-42", "payload": {"order_id": 42, "status": "completed"}},
            handler,
        )
    )

    assert seen == {
        "topic": "payment.completed",
        "payload": {"order_id": 42, "status": "completed"},
        "event_id": "evt-42",
    }
