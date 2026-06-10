#!/usr/bin/env python3
"""Generate demo catalog products through the public Magazon API."""

import argparse
import getpass
import json
import os
import random
import sys
from decimal import Decimal
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


CATEGORY_SPECS = [
    ("Laptopuri", "Laptopuri office, business, gaming și ultraportabile"),
    ("Gaming", "Periferice și echipamente pentru gaming"),
    ("Componente", "Componente și upgrade-uri pentru PC"),
    ("Monitoare", "Monitoare pentru productivitate, creație și gaming"),
    ("Periferice", "Tastaturi, mouse-uri, căști și camere web"),
    ("Accesorii", "Dock-uri, cabluri, suporturi și accesorii pentru birou"),
]

PRODUCT_PARTS = {
    "Laptopuri": {
        "types": ["Laptop Office", "Laptop Business", "Ultrabook", "Laptop Gaming"],
        "features": ["Ryzen 7", "Core i7", "16GB RAM", "32GB RAM", "SSD 1TB"],
        "price": (2299, 8999),
    },
    "Gaming": {
        "types": ["Mouse Gaming", "Tastatură Mecanică", "Căști Gaming", "Controller"],
        "features": ["RGB", "Wireless", "Pro", "Low Latency", "Tournament"],
        "price": (149, 1299),
    },
    "Componente": {
        "types": ["SSD NVMe", "Memorie DDR5", "Placă Video", "Sursă Modulară"],
        "features": ["Performance", "Pro", "Gaming", "Silent", "Creator"],
        "price": (249, 6499),
    },
    "Monitoare": {
        "types": ["Monitor IPS", "Monitor Gaming", "Monitor Ultrawide", "Monitor 4K"],
        "features": ["144Hz", "165Hz", "HDR", "USB-C", "Professional"],
        "price": (699, 4999),
    },
    "Periferice": {
        "types": ["Tastatură Wireless", "Mouse Office", "Webcam", "Microfon USB"],
        "features": ["Silent", "Ergonomic", "Full HD", "Studio", "Compact"],
        "price": (79, 1099),
    },
    "Accesorii": {
        "types": ["Dock USB-C", "Hub USB", "Suport Laptop", "Cablu Premium"],
        "features": ["8-in-1", "Aluminium", "Fast Charge", "Dual Display", "Travel"],
        "price": (49, 899),
    },
}


class ApiClient:
    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("detail", raw)
            except json.JSONDecodeError:
                detail = raw
            raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot connect to {self.base_url}: {exc.reason}") from exc

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, payload: dict):
        return self.request("POST", path, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create generated products and inventory through the Magazon API."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("MAGAZON_URL", "http://127.0.0.1:8081"),
        help="Frontend/API URL (default: %(default)s or MAGAZON_URL)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=120,
        help="Number of generated products that should exist (default: %(default)s)",
    )
    parser.add_argument(
        "--stock",
        type=int,
        default=50,
        help="Inventory assigned to every generated product (default: %(default)s)",
    )
    parser.add_argument(
        "--admin-email",
        default=os.getenv("MAGAZON_ADMIN_EMAIL", "admin@microshop.local"),
        help="Admin email (default: %(default)s)",
    )
    parser.add_argument(
        "--admin-password",
        default=os.getenv("MAGAZON_ADMIN_PASSWORD"),
        help="Admin password; prefer MAGAZON_ADMIN_PASSWORD to avoid shell history",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Random seed used for reproducible names and prices",
    )
    parser.add_argument(
        "--skip-inventory",
        action="store_true",
        help="Create products without updating inventory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without changing the API",
    )
    return parser.parse_args()


def generated_product(index: int, category_name: str, category_id: int, seed: int) -> dict:
    spec = PRODUCT_PARTS[category_name]
    rng = random.Random(seed + index)
    product_type = rng.choice(spec["types"])
    feature = rng.choice(spec["features"])
    model = f"M{index:03d}"
    price_min, price_max = spec["price"]
    raw_price = rng.randint(price_min * 100, price_max * 100)
    price = Decimal(raw_price) / Decimal("100")
    return {
        "sku": f"DEMO-{category_name[:3].upper()}-{index:04d}",
        "name": f"{product_type} {feature} {model}",
        "description": (
            f"{product_type} din gama {feature}, model {model}. "
            "Produs generat automat pentru catalogul Magazon."
        ),
        "price": f"{price:.2f}",
        "category_id": category_id,
    }


def ensure_categories(client: ApiClient, dry_run: bool) -> dict[str, int]:
    existing = {
        item["name"]: item["id"]
        for item in client.get("/api/products/categories").get("items", [])
    }
    result = dict(existing)
    next_dry_id = max(existing.values(), default=0) + 1

    for name, description in CATEGORY_SPECS:
        if name in result:
            continue
        if dry_run:
            result[name] = next_dry_id
            next_dry_id += 1
            print(f"[dry-run] category: {name}")
            continue
        category = client.post(
            "/api/products/categories",
            {"name": name, "description": description},
        )
        result[name] = category["id"]
        print(f"Created category: {name}")
    return result


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    if args.stock < 0:
        raise SystemExit("--stock must be zero or greater")

    password = args.admin_password
    if not password:
        password = getpass.getpass(f"Password for {args.admin_email}: ")

    client = ApiClient(args.base_url)
    session = client.post(
        "/api/auth/login",
        {"email": args.admin_email, "password": password},
    )
    if session.get("role") != "admin":
        raise RuntimeError("The configured account does not have the admin role")

    categories = ensure_categories(client, args.dry_run)
    existing_products = client.get("/api/products/products").get("items", [])
    products_by_sku = {item.get("sku"): item for item in existing_products}
    category_names = [name for name, _description in CATEGORY_SPECS]

    created = 0
    skipped = 0
    inventory_updated = 0
    for index in range(1, args.count + 1):
        category_name = category_names[(index - 1) % len(category_names)]
        payload = generated_product(
            index,
            category_name,
            categories[category_name],
            args.seed,
        )
        existing = products_by_sku.get(payload["sku"])
        if existing:
            product = existing
            skipped += 1
        elif args.dry_run:
            product = {"id": index, **payload}
            created += 1
            print(f"[dry-run] {payload['sku']} | {payload['name']} | {payload['price']} EUR")
        else:
            product = client.post("/api/products/products", payload)
            products_by_sku[payload["sku"]] = product
            created += 1
            print(f"[{created:03d}] Created {payload['sku']}: {payload['name']}")

        if not args.skip_inventory and not args.dry_run:
            client.post(
                "/api/inventory/inventory/seed",
                {"product_id": product["id"], "stock": args.stock},
            )
            inventory_updated += 1

    print(
        f"Done: {created} created, {skipped} already existed, "
        f"{inventory_updated} inventory records updated."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
