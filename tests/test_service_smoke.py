from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
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


def test_product_serializers_include_category_name():
    product_module = load_module("product_main", "services/product-service/app/main.py")

    category = product_module.Category(id=7, name="Accessories", description="Desk gear")
    product = product_module.Product(
        id=11,
        name="USB-C Dock",
        description="Dock",
        price=149.0,
        category_id=7,
    )

    serialized_category = product_module.serialize_category(category)
    serialized_product = product_module.serialize_product(product, {7: category})

    assert serialized_category["name"] == "Accessories"
    assert serialized_product["category_name"] == "Accessories"
    assert serialized_product["price"] == 149.0


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

    result = cart_module.get_cart(1)

    assert result["user_id"] == 1
    assert result["total"] == 387.0
    assert result["items"][0]["name"] == "Mechanical Keyboard"
    assert result["items"][0]["subtotal"] == 238.0
