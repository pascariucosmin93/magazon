import hashlib
import hmac
import json
import time
from decimal import Decimal
from uuid import uuid4

import requests


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wait_until(fetch, predicate, timeout_seconds: float = 30, interval_seconds: float = 1):
    deadline = time.time() + timeout_seconds
    last_value = None
    while time.time() < deadline:
        last_value = fetch()
        if predicate(last_value):
            return last_value
        time.sleep(interval_seconds)
    raise AssertionError(f"Condition not met before timeout. Last value: {last_value}")


def _stripe_signature(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _money(value) -> Decimal:
    return Decimal(str(value))


def test_critical_checkout_flow(e2e_stack: dict[str, str]):
    auth_base = e2e_stack["auth-service"]
    cart_base = e2e_stack["cart-service"]
    order_base = e2e_stack["order-service"]
    inventory_base = e2e_stack["inventory-service"]
    payment_base = e2e_stack["payment-service"]

    username = f"e2e-user-{uuid4().hex[:8]}"
    email = f"e2e-{uuid4().hex[:8]}@example.com"
    password = "S3curePassw0rd!"
    register_response = requests.post(
        f"{auth_base}/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "address": "Strada Test 1",
        },
        timeout=10,
    )
    assert register_response.status_code == 200, register_response.text
    user_id = register_response.json()["id"]

    login_response = requests.post(
        f"{auth_base}/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json()["token"]
    customer_headers = _auth_headers(token)

    add_to_cart_response = requests.post(
        f"{cart_base}/cart/add",
        json={"user_id": user_id, "product_id": 1, "quantity": 2},
        headers=customer_headers,
        timeout=10,
    )
    assert add_to_cart_response.status_code == 200, add_to_cart_response.text

    cart_response = requests.get(
        f"{cart_base}/cart/{user_id}",
        headers=customer_headers,
        timeout=10,
    )
    assert cart_response.status_code == 200, cart_response.text
    cart_payload = cart_response.json()
    assert _money(cart_payload["total"]) == Decimal("238.00")
    assert len(cart_payload["items"]) == 1
    assert cart_payload["items"][0]["product_id"] == 1
    assert cart_payload["items"][0]["name"] == "Mechanical Keyboard"
    assert cart_payload["items"][0]["quantity"] == 2
    assert _money(cart_payload["items"][0]["price"]) == Decimal("119.00")
    assert _money(cart_payload["items"][0]["subtotal"]) == Decimal("238.00")

    order_response = requests.post(
        f"{order_base}/orders",
        json={"items": [{"product_id": 1, "quantity": 2}]},
        headers=customer_headers,
        timeout=10,
    )
    assert order_response.status_code == 200, order_response.text
    order_payload = order_response.json()
    order_id = order_payload["order_id"]
    assert order_payload["status"] == "created"
    assert _money(order_payload["total"]) == Decimal("238.00")

    reserved_order = _wait_until(
        lambda: requests.get(
            f"{order_base}/orders/{order_id}",
            headers=customer_headers,
            timeout=10,
        ).json(),
        lambda payload: payload["status"] == "inventory_reserved",
        timeout_seconds=45,
    )
    assert reserved_order["items"][0]["product_id"] == 1

    inventory_response = _wait_until(
        lambda: requests.get(f"{inventory_base}/inventory/1", timeout=10).json(),
        lambda payload: payload["stock"] == 23,
        timeout_seconds=20,
    )
    assert inventory_response == {"product_id": 1, "stock": 23}

    awaiting_payment = _wait_until(
        lambda: requests.get(
            f"{payment_base}/payments/orders/{order_id}",
            headers=customer_headers,
            timeout=10,
        ).json(),
        lambda payload: payload["status"] == "awaiting_payment",
        timeout_seconds=45,
    )
    assert _money(awaiting_payment["amount"]) == Decimal("238.00")
    assert awaiting_payment["provider"] == "stripe"

    event = {
        "id": f"evt_{uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "object": "checkout.session",
                "id": f"cs_{uuid4().hex}",
                "payment_status": "paid",
                "payment_intent": f"pi_{uuid4().hex}",
                "metadata": {"order_id": str(order_id)},
            }
        },
    }
    webhook_payload = json.dumps(event).encode("utf-8")
    webhook_response = requests.post(
        f"{payment_base}/webhooks/stripe",
        data=webhook_payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _stripe_signature(webhook_payload, "whsec_e2e_local"),
        },
        timeout=10,
    )
    assert webhook_response.status_code == 200, webhook_response.text
    assert webhook_response.json()["received"] is True

    completed_payment = _wait_until(
        lambda: requests.get(
            f"{payment_base}/payments/orders/{order_id}",
            headers=customer_headers,
            timeout=10,
        ).json(),
        lambda payload: payload["status"] == "completed",
        timeout_seconds=45,
    )
    assert completed_payment["payment_intent_id"] == event["data"]["object"]["payment_intent"]
    assert _money(completed_payment["amount"]) == Decimal("238.00")

    paid_order = _wait_until(
        lambda: requests.get(
            f"{order_base}/orders/{order_id}",
            headers=customer_headers,
            timeout=10,
        ).json(),
        lambda payload: payload["status"] == "paid",
        timeout_seconds=45,
    )
    assert _money(paid_order["total"]) == Decimal("238.00")

    admin_login = requests.post(
        f"{auth_base}/login",
        json={"email": "admin@microshop.local", "password": "e2e-admin-password"},
        timeout=10,
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_headers = _auth_headers(admin_login.json()["token"])

    transactions_response = requests.get(
        f"{payment_base}/payments/orders/{order_id}/transactions",
        headers=admin_headers,
        timeout=10,
    )
    assert transactions_response.status_code == 200, transactions_response.text
    transactions = transactions_response.json()["items"]
    assert len(transactions) == 1
    assert transactions[0]["status"] == "completed"
    assert transactions[0]["provider_event_id"] == event["id"]
