import asyncio
from decimal import Decimal

from shared import kafka as shared_kafka

from test_checkout_hardening import build_session
from test_service_smoke import load_module


def test_payment_state_and_outbox_are_committed_together(monkeypatch):
    payment_module = load_module(
        "payment_main_outbox_finalize",
        "services/payment-service/app/main.py",
    )
    testing_session = build_session(payment_module)
    monkeypatch.setattr(payment_module, "SessionLocal", testing_session)

    async def skip_immediate_publish():
        return None

    monkeypatch.setattr(
        payment_module,
        "_publish_payment_outbox_best_effort",
        skip_immediate_publish,
    )

    with testing_session() as db:
        payment = payment_module.Payment(
            order_id=71,
            amount=Decimal("49.99"),
            refunded_amount=Decimal("0.00"),
            status="awaiting_payment",
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        asyncio.run(
            payment_module.finalize_payment(
                payment,
                db,
                provider_reference="pi_outbox_1",
                provider_event_id="evt_stripe_1",
            )
        )

        db.refresh(payment)
        event = db.query(payment_module.PaymentOutboxEvent).one()
        assert payment.status == "completed"
        assert event.topic == "payment.completed"
        assert event.published is False
        assert '"amount":49.99' in event.payload


def test_payment_outbox_retries_with_stable_event_id(monkeypatch):
    payment_module = load_module(
        "payment_main_outbox_retry",
        "services/payment-service/app/main.py",
    )
    testing_session = build_session(payment_module)
    monkeypatch.setattr(payment_module, "SessionLocal", testing_session)

    calls = []

    async def flaky_publish(topic, payload, *, event_id=None):
        calls.append((topic, payload, event_id))
        if len(calls) == 1:
            raise RuntimeError("kafka unavailable")

    monkeypatch.setattr(payment_module, "publish_event", flaky_publish)

    with testing_session() as db:
        event = payment_module._enqueue_payment_event(
            db,
            "payment.refunded",
            {"order_id": 72, "status": "refunded", "amount": 12.5},
        )
        db.commit()
        stable_event_id = event.event_id

    asyncio.run(payment_module.publish_pending_payment_events_once())

    with testing_session() as db:
        failed = db.query(payment_module.PaymentOutboxEvent).one()
        assert failed.published is False
        assert failed.publish_attempts == 1
        assert "kafka unavailable" in failed.last_error

    asyncio.run(payment_module.publish_pending_payment_events_once())

    with testing_session() as db:
        stored = db.query(payment_module.PaymentOutboxEvent).one()
        assert stored.published is True
        assert stored.publish_attempts == 2
        assert stored.last_error is None
        assert stored.event_id == stable_event_id

    assert [call[2] for call in calls] == [stable_event_id, stable_event_id]


def test_shared_kafka_accepts_stable_event_id():
    envelope = shared_kafka.build_event_envelope(
        "payment.completed",
        {"order_id": 73},
        event_id="payment-outbox-event-73",
    )

    assert envelope["event_id"] == "payment-outbox-event-73"
