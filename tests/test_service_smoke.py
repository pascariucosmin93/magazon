from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, clear_mappers

from shared.db import Base


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


def test_password_hash_uses_salted_argon2_and_verifies():
    auth_module = load_module("auth_main", "services/auth-service/app/main.py")

    first = auth_module.hash_password("admin123")
    second = auth_module.hash_password("admin123")

    assert first.startswith("$argon2")
    assert second.startswith("$argon2")
    assert first != second
    assert auth_module.verify_password("admin123", first)
    assert not auth_module.verify_password("demo123", first)


def test_legacy_sha256_password_hash_still_verifies():
    auth_module = load_module("auth_main", "services/auth-service/app/main.py")

    legacy = auth_module.legacy_hash_password("admin123")

    assert auth_module.is_legacy_password_hash(legacy)
    assert auth_module.verify_password("admin123", legacy)
    assert not auth_module.verify_password("demo123", legacy)


def test_login_request_accepts_existing_local_admin_email():
    auth_module = load_module("auth_main_login", "services/auth-service/app/main.py")

    payload = auth_module.LoginRequest(
        email="admin@microshop.local",
        password="admin-password",
    )

    assert payload.email == "admin@microshop.local"


def test_admin_can_delete_customer_but_not_admin_account():
    auth_module = load_module("auth_main_delete_user", "services/auth-service/app/main.py")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        admin = auth_module.User(
            username="admin",
            email="admin@microshop.local",
            password="unused",
            address="Admin Console",
            role="admin",
        )
        customer = auth_module.User(
            username="customer",
            email="customer@example.com",
            password="unused",
            address="Test Address",
            role="customer",
        )
        db.add_all([admin, customer])
        db.commit()
        db.refresh(admin)
        db.refresh(customer)

        result = auth_module.delete_user(customer.id, db, {"sub": str(admin.id), "role": "admin"})
        assert result == {"message": "User deleted", "user_id": customer.id}
        assert db.get(auth_module.User, customer.id) is None

        with pytest.raises(HTTPException) as exc:
            auth_module.delete_user(admin.id, db, {"sub": str(admin.id), "role": "admin"})
        assert exc.value.status_code == 409


def test_password_reset_request_returns_token_for_existing_account(monkeypatch):
    auth_module = load_module("auth_main_password_reset", "services/auth-service/app/main.py")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    published = []

    async def fake_publish_event(topic, payload, **_kwargs):
        published.append((topic, payload))

    monkeypatch.setattr(auth_module, "publish_event", fake_publish_event)

    class DummyClient:
        host = "127.0.0.1"

    class DummyRequest:
        client = DummyClient()

    with Session(engine) as db:
        user = auth_module.User(
            username="customer",
            email="customer@example.com",
            password="unused",
            address="Test Address",
            role="customer",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        response = asyncio.run(
            auth_module.request_password_reset(
                auth_module.PasswordResetRequest(email="customer@example.com"),
                DummyRequest(),
                db,
            )
        )

        db.refresh(user)
        assert response["reset_token"]
        assert user.reset_token_hash == auth_module.sha256(
            response["reset_token"].encode("utf-8")
        ).hexdigest()
        assert user.reset_token_expires_at is not None
        assert published[0][0] == "user.password_reset_requested"
        assert published[0][1]["reset_token"] == response["reset_token"]


def test_product_serializers_include_category_name():
    product_module = load_module("product_main", "services/product-service/app/main.py")

    category = product_module.Category(id=7, name="Accessories", description="Desk gear")
    product = product_module.Product(
        id=11,
        sku="DOCK-USBC-001",
        name="USB-C Dock",
        description="Dock",
        price=149.0,
        category_id=7,
    )

    serialized_category = product_module.serialize_category(category)
    serialized_product = product_module.serialize_product(product, {7: category})

    assert serialized_category["name"] == "Accessories"
    assert serialized_product["category_name"] == "Accessories"
    assert serialized_product["sku"] == "DOCK-USBC-001"
    assert serialized_product["price"] == 149.0


def test_product_sku_is_normalized_and_generated():
    product_module = load_module("product_main_sku", "services/product-service/app/main.py")

    assert product_module.normalize_sku(" dock usb-c / pro ") == "DOCK-USB-C-PRO"
    assert product_module.generate_sku("USB-C Dock", 17) == "USB-C-DOCK-17"


def test_cart_response_includes_totals(monkeypatch):
    cart_module = load_module("cart_main", "services/cart-service/app/main.py")

    class FakeRedis:
        @staticmethod
        def hgetall(_key):
            return {"1": "2", "3": "1"}

    def fake_fetch_product(product_id):
        products = {
            1: {"name": "Mechanical Keyboard", "price": 119.0},
            3: {"name": "USB-C Dock", "price": 149.0},
        }
        return products[product_id]

    monkeypatch.setattr(cart_module, "redis_client", FakeRedis())
    monkeypatch.setattr(cart_module, "fetch_product", fake_fetch_product)

    result = cart_module.get_cart(1, {"sub": "1"})

    assert result["user_id"] == 1
    assert result["total"] == 387.0
    assert result["items"][0]["name"] == "Mechanical Keyboard"
    assert result["items"][0]["subtotal"] == 238.0


def test_order_serialize_includes_items():
    order_module = load_module("order_main", "services/order-service/app/main.py")

    order = order_module.Order(id=12, user_id=7, status="created", total=298.0)
    order.items = [
        order_module.OrderItem(
            product_id=1,
            product_name="USB-C Dock",
            product_sku="DOCK-USBC-001",
            quantity=2,
            price=149.0,
        ),
    ]

    serialized = order_module.serialize_order(order)

    assert serialized["order_id"] == 12
    assert serialized["user_id"] == 7
    assert serialized["items"][0]["product_id"] == 1
    assert serialized["items"][0]["product_name"] == "USB-C Dock"
    assert serialized["items"][0]["product_sku"] == "DOCK-USBC-001"
    assert serialized["items"][0]["quantity"] == 2
    assert serialized["items"][0]["price"] == 149.0


def test_order_admin_status_transitions_are_explicit():
    order_module = load_module("order_main_statuses", "services/order-service/app/main.py")

    assert order_module.ADMIN_STATUS_TRANSITIONS["paid"] == {"processing", "cancelled"}
    assert order_module.ADMIN_STATUS_TRANSITIONS["processing"] == {"shipped", "cancelled"}
    assert order_module.ADMIN_STATUS_TRANSITIONS["shipped"] == {"delivered"}
    assert order_module.ADMIN_STATUS_TRANSITIONS["delivered"] == set()
