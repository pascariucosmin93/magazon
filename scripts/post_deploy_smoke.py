#!/usr/bin/env python3
import json
import os
import sys
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = os.environ["MAGAZON_SMOKE_BASE_URL"].rstrip("/") + "/"
ADMIN_EMAIL = os.getenv("MAGAZON_SMOKE_ADMIN_EMAIL") or "admin@microshop.local"
ADMIN_PASSWORD = os.getenv("MAGAZON_SMOKE_ADMIN_PASSWORD")
TIMEOUT_SECONDS = float(os.getenv("MAGAZON_SMOKE_TIMEOUT_SECONDS", "10"))
ATTEMPTS = int(os.getenv("MAGAZON_SMOKE_ATTEMPTS", "18"))
SLEEP_SECONDS = float(os.getenv("MAGAZON_SMOKE_SLEEP_SECONDS", "10"))


cookie_jar = CookieJar()
opener = build_opener(HTTPCookieProcessor(cookie_jar))


def _request(path: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, bytes]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        urljoin(BASE_URL, path.lstrip("/")),
        data=data,
        headers=headers,
        method=method,
    )
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        return response.status, response.read()


def _json(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    status, body = _request(path, method=method, payload=payload)
    if status < 200 or status >= 300:
        raise RuntimeError(f"{path} returned HTTP {status}")
    return json.loads(body.decode("utf-8"))


def _check_frontend() -> None:
    status, body = _request("/")
    if status != 200:
        raise RuntimeError(f"frontend returned HTTP {status}")
    if b"<html" not in body.lower() and b"<!doctype html" not in body.lower():
        raise RuntimeError("frontend did not return HTML")


def _check_catalog() -> None:
    payload = _json("/api/products/products")
    if "items" not in payload or not isinstance(payload["items"], list):
        raise RuntimeError("catalog response does not contain an items list")


def _check_admin_login() -> None:
    if not ADMIN_PASSWORD:
        print("Skipping admin login smoke: MAGAZON_SMOKE_ADMIN_PASSWORD is not set")
        return

    login = _json(
        "/api/auth/login",
        method="POST",
        payload={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if not login.get("token") or login.get("role") != "admin":
        raise RuntimeError("admin login response did not include an admin token")

    session = _json("/api/auth/session")
    if session.get("role") != "admin":
        raise RuntimeError("admin session check did not return role=admin")


def run_once() -> None:
    _check_frontend()
    _check_catalog()
    _check_admin_login()


def main() -> int:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            print(f"Post-deploy smoke attempt {attempt}/{ATTEMPTS} against {BASE_URL}")
            run_once()
            print("Post-deploy smoke passed")
            return 0
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"Smoke attempt {attempt} failed: {exc}", file=sys.stderr)
            if attempt < ATTEMPTS:
                time.sleep(SLEEP_SECONDS)

    print(f"Post-deploy smoke failed after {ATTEMPTS} attempts: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
