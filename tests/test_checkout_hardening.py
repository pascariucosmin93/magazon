import asyncio
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.money import as_money, money_minor_units

from test_service_smoke import load_module


def build_session(module):
    engine = create_engine("sqlite:///:memory:")
    module.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_money_helpers_round_with_decimal_rules():
    assert as_money("10.005") == Decimal("10.01")
    assert as_money(0.1) + as_money(0.2) == Decimal("0.30")
    assert money_minor_units("149.99") == 14999


def test_customer_cancellation_writes_outbox_once():
    order_module = load_module(
        "order_main_customer_cancellation",
        "services/order-service/app/main.py",
    )
    testing_session = build_session(order_module)

    with testing_session() as db:
        order = order_module.Order(user_id=7, status="inventory_reserved", total=Decimal("20.00"))
        order.items = [
            order_module.OrderItem(
                product_id=1,
                quantity=2,
                price=Decimal("10.00"),
            )
        ]
        db.add(order)
        db.commit()
        db.refresh(order)

        order_module._cancel_order(order, "Nu mai este necesară", db)
        db.commit()
        order_module._cancel_order(order, "Mesaj duplicat", db)
        db.commit()

        events = db.query(order_module.OutboxEvent).all()
        assert order.status == "cancelled"
        assert order.cancellation_reason == "Nu mai este necesară"
        assert len(events) == 1
        assert events[0].topic == "order.cancelled"
        assert '"total":20.0' in events[0].payload


def test_inventory_cancellation_releases_reserved_stock_once(monkeypatch):
    inventory_module = load_module(
        "inventory_main_release",
        "services/inventory-service/app/main.py",
    )
    testing_session = build_session(inventory_module)
    monkeypatch.setattr(inventory_module, "SessionLocal", testing_session)

    published = []

    async def fake_publish(topic, payload):
        published.append((topic, payload))

    monkeypatch.setattr(inventory_module, "publish_event", fake_publish)

    with testing_session() as db:
        db.add(inventory_module.Inventory(product_id=1, stock=8))
        db.add(inventory_module.InventoryReservation(order_id=42, status="reserved"))
        db.commit()

    payload = {
        "order_id": 42,
        "items": [{"product_id": 1, "quantity": 2, "price": 10.0}],
    }
    asyncio.run(inventory_module.handle_order_event("order.cancelled", payload))
    asyncio.run(inventory_module.handle_order_event("order.cancelled", payload))

    with testing_session() as db:
        inventory = db.query(inventory_module.Inventory).one()
        reservation = db.query(inventory_module.InventoryReservation).one()
        assert inventory.stock == 10
        assert reservation.status == "released"
        assert reservation.released_at is not None
    assert published[-1] == ("inventory.released", {"order_id": 42, "status": "released"})


def test_completed_payment_refund_records_transaction(monkeypatch):
    payment_module = load_module(
        "payment_main_refund",
        "services/payment-service/app/main.py",
    )
    testing_session = build_session(payment_module)
    monkeypatch.setattr(payment_module, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(payment_module, "SessionLocal", testing_session)

    class FakeRefund:
        @staticmethod
        def create(**kwargs):
            assert kwargs["amount"] == 2050
            return {"id": "re_test_1"}

    monkeypatch.setattr(payment_module.stripe, "Refund", FakeRefund)

    published = []

    async def fake_publish(topic, payload, **_kwargs):
        published.append((topic, payload))

    monkeypatch.setattr(payment_module, "publish_event", fake_publish)

    with testing_session() as db:
        payment = payment_module.Payment(
            order_id=9,
            amount=Decimal("20.50"),
            refunded_amount=Decimal("0.00"),
            status="completed",
            payment_intent_id="pi_test_1",
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        asyncio.run(payment_module.refund_payment(payment, db))
        db.refresh(payment)

        transaction = db.query(payment_module.PaymentTransaction).one()
        assert payment.status == "refunded"
        assert payment.refunded_amount == Decimal("20.50")
        assert transaction.transaction_type == "refund"
        assert transaction.provider_reference == "re_test_1"

    assert published == [
        ("payment.refunded", {"order_id": 9, "status": "refunded", "amount": 20.5})
    ]


def test_late_paid_webhook_refunds_cancelled_payment(monkeypatch):
    payment_module = load_module(
        "payment_main_late_paid_refund",
        "services/payment-service/app/main.py",
    )
    testing_session = build_session(payment_module)
    monkeypatch.setattr(payment_module, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(payment_module, "SessionLocal", testing_session)
    monkeypatch.setattr(
        payment_module.stripe.Refund,
        "create",
        lambda **_kwargs: {"id": "re_late_1"},
    )

    async def fake_publish(_topic, _payload, **_kwargs):
        return None

    monkeypatch.setattr(payment_module, "publish_event", fake_publish)

    with testing_session() as db:
        payment = payment_module.Payment(
            order_id=10,
            amount=Decimal("15.00"),
            refunded_amount=Decimal("0.00"),
            status="cancelled",
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        asyncio.run(
            payment_module.finalize_payment(
                payment,
                db,
                provider_reference="pi_late_1",
                provider_event_id="evt_checkout_completed",
            )
        )

        db.refresh(payment)
        transactions = (
            db.query(payment_module.PaymentTransaction)
            .order_by(payment_module.PaymentTransaction.id)
            .all()
        )
        assert payment.status == "refunded"
        assert [item.transaction_type for item in transactions] == ["payment", "refund"]
        assert transactions[0].provider_event_id == "evt_checkout_completed"
        assert transactions[1].provider_event_id is None


def test_address_book_keeps_single_default_address():
    auth_module = load_module(
        "auth_main_addresses",
        "services/auth-service/app/main.py",
    )
    testing_session = build_session(auth_module)

    with testing_session() as db:
        user = auth_module.User(
            username="customer",
            email="customer@example.com",
            password="unused",
            address="Old address",
            role="customer",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        claims = {"sub": str(user.id), "role": "customer"}

        first = auth_module.create_address(
            auth_module.AddressRequest(
                label="Acasă",
                recipient_name="Customer",
                line1="Strada Principală 1",
                city="București",
                postal_code="010101",
                is_default=True,
            ),
            claims,
            db,
        )
        second = auth_module.create_address(
            auth_module.AddressRequest(
                label="Birou",
                recipient_name="Customer",
                line1="Calea Victoriei 10",
                city="București",
                postal_code="010102",
                is_default=True,
            ),
            claims,
            db,
        )

        addresses = auth_module.list_addresses(claims, db)["items"]
        assert first["is_default"] is True
        assert second["is_default"] is True
        assert sum(address["is_default"] for address in addresses) == 1
        assert addresses[0]["label"] == "Birou"
