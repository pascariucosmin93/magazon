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


def test_internal_api_token_dependency_accepts_only_configured_secret(monkeypatch):
    from shared import auth as shared_auth

    monkeypatch.setattr(shared_auth.settings, "internal_api_token", "internal-secret")
    shared_auth.require_internal_api_token("internal-secret")

    with pytest.raises(HTTPException) as exc:
        shared_auth.require_internal_api_token("wrong-token")
    assert exc.value.status_code == 401


def test_chat_service_builds_ollama_messages_and_returns_reply(monkeypatch):
    chat_module = load_module("chat_main", "services/chat-service/app/main.py")

    request = chat_module.ChatRequest(
        message="Ai laptopuri pentru birou?",
        history=[
            chat_module.ChatMessage(role="user", content="Salut"),
            chat_module.ChatMessage(role="assistant", content="Salut. Cu ce te ajut?"),
        ],
    )

    messages = chat_module._ollama_messages(request)
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "Ai laptopuri pentru birou?"}

    monkeypatch.setattr(chat_module, "ask_ollama", lambda _payload: "Da, verifica sectiunea Laptopuri.")
    response = chat_module.create_chat_message(request)

    assert response.reply == "Da, verifica sectiunea Laptopuri."
    assert response.model == chat_module.OLLAMA_MODEL
    assert response.conversation_id


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


def test_product_import_preview_classifies_create_update_and_archive():
    product_module = load_module("product_main_import_preview", "services/product-service/app/main.py")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        category = product_module.Category(name="Periferice", description="Peripherals")
        archived_category = product_module.Category(name="Accesorii", description="Accessories")
        db.add_all([category, archived_category])
        db.flush()
        db.add_all(
            [
                product_module.Product(
                    sku="KB-001",
                    name="Old Keyboard",
                    description="Old",
                    price=99.0,
                    category_id=category.id,
                ),
                product_module.Product(
                    sku="MOUSE-OLD",
                    name="Old Mouse",
                    description="Old",
                    price=49.0,
                    category_id=archived_category.id,
                ),
            ]
        )
        db.commit()

        preview = product_module._build_import_preview(
            [
                {
                    "row_number": 2,
                    "sku": "KB-001",
                    "name": "Mechanical Keyboard",
                    "description": "Hot swap",
                    "price": "119.00",
                    "category": "Periferice",
                    "stock": "10",
                    "active": "true",
                    "operation": "upsert",
                },
                {
                    "row_number": 3,
                    "sku": "DOCK-NEW",
                    "name": "USB-C Dock",
                    "description": "Dock",
                    "price": "149.99",
                    "category": "Accesorii",
                    "stock": "20",
                    "active": "true",
                    "operation": "upsert",
                },
                {
                    "row_number": 4,
                    "sku": "MOUSE-OLD",
                    "name": "Old Mouse",
                    "description": "Old",
                    "price": "49.00",
                    "category": "Accesorii",
                    "stock": "0",
                    "active": "false",
                    "operation": "archive",
                },
            ],
            db,
        )

        assert preview["summary"] == {
            "create": 1,
            "update": 1,
            "archive": 1,
            "skip": 0,
            "error": 0,
        }


def test_product_import_apply_updates_products_and_archives(monkeypatch):
    product_module = load_module("product_main_import_apply", "services/product-service/app/main.py")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inventory_updates = []

    monkeypatch.setattr(
        product_module,
        "_sync_inventory_bulk",
        lambda items: inventory_updates.extend(items),
    )
    monkeypatch.setattr(product_module.redis_client, "delete", lambda *_args, **_kwargs: 1)

    with Session(engine) as db:
        category = product_module.Category(name="Periferice", description="Peripherals")
        db.add(category)
        db.flush()
        db.add(
            product_module.Product(
                sku="KB-001",
                name="Keyboard",
                description="Old",
                price=99.0,
                category_id=category.id,
            )
        )
        db.commit()

        preview = {
            "summary": {"create": 1, "update": 1, "archive": 0, "skip": 0, "error": 0},
            "rows": [
                {
                    "row_number": 2,
                    "action": "update",
                    "sku": "KB-001",
                    "name": "Keyboard Pro",
                    "description": "Updated",
                    "price": 129.0,
                    "category": "Periferice",
                    "stock": 14,
                },
                {
                    "row_number": 3,
                    "action": "create",
                    "sku": "DOCK-001",
                    "name": "Dock",
                    "description": "New dock",
                    "price": 149.0,
                    "category": "Accesorii",
                    "stock": 8,
                },
                {
                    "row_number": 4,
                    "action": "archive",
                    "sku": "KB-001",
                    "name": "Keyboard Pro",
                    "description": "Updated",
                    "price": 129.0,
                    "category": "Periferice",
                    "stock": 0,
                },
            ],
        }

        result = product_module._apply_import(
            preview,
            db,
            filename="import.xlsx",
            created_by="admin@example.com",
        )
        products = db.query(product_module.Product).order_by(product_module.Product.sku).all()
        jobs = db.query(product_module.ProductImportJob).all()

        assert result["summary"]["created"] == 1
        assert result["summary"]["updated"] == 1
        assert result["summary"]["archived"] == 1
        assert any(product.sku == "DOCK-001" for product in products)
        archived = db.query(product_module.Product).filter(product_module.Product.sku == "KB-001").one()
        assert archived.archived_at is not None
        assert inventory_updates
        assert len(jobs) == 1
        assert jobs[0].filename == "import.xlsx"
        assert jobs[0].created_by == "admin@example.com"


def test_product_inventory_sync_uses_internal_token(monkeypatch):
    product_module = load_module("product_main_internal_sync", "services/product-service/app/main.py")
    captured = {}

    class DummyResponse:
        status_code = 200

    def fake_post(url, json=None, timeout=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(product_module.settings, "internal_api_token", "internal-secret")
    monkeypatch.setattr(product_module.requests, "post", fake_post)

    product_module._sync_inventory_bulk([{"product_id": 7, "stock": 12}])

    assert captured["headers"]["X-Internal-Api-Token"] == "internal-secret"
    assert captured["json"] == {"items": [{"product_id": 7, "stock": 12}]}


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
