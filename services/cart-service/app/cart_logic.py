import os
from typing import Any

import requests

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")


def cart_key(user_id: int) -> str:
    return f"cart:{user_id}"


def fetch_product(product_id: int) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=3,
        )
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        return None
    return None
