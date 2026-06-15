import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    for module_name in (
        "cart_logic",
        "cart_routes",
        "cart_schemas",
    ):
        sys.modules.pop(module_name, None)

import cart_logic as cart_logic_module  # noqa: E402
import cart_routes as cart_routes_module  # noqa: E402
import cart_schemas as cart_schemas_module  # noqa: E402
from shared.auth import require_user_id  # noqa: E402
from shared.money import as_money, money_json  # noqa: E402
from shared.redis_client import redis_client  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

__all__ = ["CartItemRequest"]

PRODUCT_SERVICE_URL = cart_logic_module.PRODUCT_SERVICE_URL
CartItemRequest = cart_schemas_module.CartItemRequest
cart_key = cart_logic_module.cart_key
add_to_cart = cart_routes_module.add_to_cart
clear_cart = cart_routes_module.clear_cart
remove_cart_item = cart_routes_module.remove_cart_item
replace_cart = cart_routes_module.replace_cart
router = cart_routes_module.router


def fetch_product(product_id: int):
    return cart_logic_module.fetch_product(product_id)


def get_cart(user_id: int, claims: dict):
    require_user_id(user_id, claims)
    items = redis_client.hgetall(cart_key(user_id))
    result = []
    total = as_money(0)

    for product_id, quantity in items.items():
        product_id_int = int(product_id)
        quantity_int = int(quantity)
        product = fetch_product(product_id_int)
        price = as_money(product["price"]) if product else as_money(0)
        subtotal = price * quantity_int
        total += subtotal
        result.append(
            {
                "product_id": product_id_int,
                "name": product["name"] if product else f"Product {product_id_int}",
                "price": money_json(price),
                "quantity": quantity_int,
                "subtotal": money_json(subtotal),
            }
        )

    return {"user_id": user_id, "items": result, "total": money_json(total)}


app = create_base_app("cart-service", check_redis=True)
app.include_router(router)
