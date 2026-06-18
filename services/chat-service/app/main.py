import os
import re
import sys
import unicodedata
import uuid
from pathlib import Path

from fastapi import HTTPException
import requests

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if not __package__:
    sys.modules.pop("chat_schemas", None)

from chat_schemas import ChatMessage, ChatRequest, ChatResponse  # noqa: E402
from shared.service_app import create_base_app  # noqa: E402

__all__ = ["ChatMessage", "ChatRequest", "ChatResponse"]


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000").rstrip("/")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8000").rstrip("/")
SERVICE_TIMEOUT_SECONDS = float(os.getenv("CHAT_SERVICE_TIMEOUT_SECONDS", "5"))

SYSTEM_PROMPT = (
    "Esti asistentul magazinului Magazon. Raspunde concis in romana. "
    "Ajuta clientii cu produse, comenzi, cont, checkout, livrare si retur. "
    "Nu inventa statusuri de comanda sau stocuri exacte daca nu ai date. "
    "Cand nu esti sigur, spune ce poate verifica utilizatorul in catalog, cont sau checkout."
)


app = create_base_app("chat-service")


PRODUCT_SYNONYMS = {
    "tastatura": {"tastatura", "tastaturi", "keyboard", "keyboards", "mechanical", "mecanica"},
    "mouse": {"mouse", "mice"},
    "laptop": {"laptop", "laptopuri", "notebook"},
    "monitor": {"monitor", "monitoare", "display"},
    "ssd": {"ssd", "storage", "stocare"},
    "casti": {"casti", "headset", "headphones"},
}


def _normalize_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return ascii_value.lower()


def _query_terms(message: str) -> set[str]:
    normalized = _normalize_text(message)
    words = {word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) >= 3}
    expanded = set(words)
    for canonical, synonyms in PRODUCT_SYNONYMS.items():
        if words & synonyms:
            expanded.add(canonical)
            expanded.update(synonyms)
    return expanded


def _is_product_question(message: str) -> bool:
    terms = _query_terms(message)
    product_words = {
        "produs",
        "produse",
        "stoc",
        "aveti",
        "pret",
        "preturi",
        "recomanzi",
        "recomandare",
    }
    return bool(terms & product_words) or any(terms & synonyms for synonyms in PRODUCT_SYNONYMS.values())


def _account_reply(message: str) -> str | None:
    terms = _query_terms(message)
    account_terms = {
        "cont",
        "account",
        "login",
        "logare",
        "inregistrat",
        "inregistrare",
        "parola",
        "utilizator",
        "user",
        "username",
        "email",
    }
    if not terms & account_terms:
        return None
    return (
        "Nu pot confirma daca un anumit username sau email are cont, din motive de confidentialitate. "
        "Incearca sa te autentifici din Login / Cont. Daca nu mai stii parola, foloseste resetarea parolei. "
        "Daca esti administrator, poti verifica utilizatorii in Panou admin."
    )


def _fetch_products() -> list[dict]:
    response = requests.get(f"{PRODUCT_SERVICE_URL}/products", timeout=SERVICE_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def _fetch_stock(product_id: int) -> int | None:
    try:
        response = requests.get(
            f"{INVENTORY_SERVICE_URL}/inventory/{product_id}",
            timeout=SERVICE_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except requests.RequestException:
        return None
    payload = response.json()
    stock = payload.get("stock")
    return int(stock) if isinstance(stock, int) else None


def _score_product(product: dict, terms: set[str]) -> int:
    haystack = _normalize_text(
        " ".join(
            str(product.get(field) or "")
            for field in ("name", "description", "category_name", "sku")
        )
    )
    score = 0
    for term in terms:
        if term in haystack:
            score += 1
    return score


def _catalog_reply(message: str) -> str | None:
    if not _is_product_question(message):
        return None

    try:
        products = _fetch_products()
    except requests.RequestException:
        return "Nu pot verifica momentan catalogul. Incearca din nou in cateva secunde."

    terms = _query_terms(message)
    scored = [
        (product, _score_product(product, terms))
        for product in products
        if not product.get("archived")
    ]
    matches = [product for product, score in scored if score > 0]
    if not matches:
        return "Nu am gasit produse care sa se potriveasca intrebarii tale in catalogul curent."

    enriched = []
    for product in matches[:12]:
        stock = _fetch_stock(int(product["id"]))
        enriched.append((product, stock))

    asks_stock = bool(_query_terms(message) & {"stoc", "disponibil", "disponibile", "aveti"})
    visible = [(product, stock) for product, stock in enriched if not asks_stock or stock is None or stock > 0]
    if asks_stock and not visible:
        return "Am gasit produse potrivite, dar nu apar cu stoc disponibil momentan."

    lines = ["Am gasit aceste produse in catalog:"]
    for product, stock in visible[:6]:
        stock_text = "stoc neconfirmat" if stock is None else f"stoc: {stock}"
        lines.append(
            f"- {product.get('name')} ({product.get('sku')}), "
            f"{product.get('price')} RON, {stock_text}"
        )
    return "\n".join(lines)


def _ollama_messages(payload: ChatRequest) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in payload.history[-12:]:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": payload.message.strip()})
    return messages


def ask_ollama(payload: ChatRequest) -> str:
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": _ollama_messages(payload),
                "stream": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.4,
                    "num_ctx": 1024,
                    "num_predict": 160,
                },
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise HTTPException(status_code=504, detail="AI assistant timed out") from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="AI assistant unavailable") from exc

    data = response.json()
    reply = data.get("message", {}).get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise HTTPException(status_code=502, detail="AI assistant returned an invalid response")
    return reply.strip()


@app.get("/chat/info")
def chat_info():
    return {"model": OLLAMA_MODEL, "provider": "ollama"}


@app.get("/info")
def chat_info_proxy():
    return chat_info()


@app.post("/chat/messages", response_model=ChatResponse)
def create_chat_message(payload: ChatRequest):
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    account_reply = _account_reply(payload.message)
    if account_reply:
        return ChatResponse(
            reply=account_reply,
            model="account-help",
            conversation_id=conversation_id,
        )
    catalog_reply = _catalog_reply(payload.message)
    if catalog_reply:
        return ChatResponse(
            reply=catalog_reply,
            model="catalog",
            conversation_id=conversation_id,
        )
    return ChatResponse(
        reply=ask_ollama(payload),
        model=OLLAMA_MODEL,
        conversation_id=conversation_id,
    )


@app.post("/messages", response_model=ChatResponse)
def create_chat_message_proxy(payload: ChatRequest):
    return create_chat_message(payload)
