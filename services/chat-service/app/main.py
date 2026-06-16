import os
import sys
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

SYSTEM_PROMPT = (
    "Esti asistentul magazinului Magazon. Raspunde concis in romana. "
    "Ajuta clientii cu produse, comenzi, cont, checkout, livrare si retur. "
    "Nu inventa statusuri de comanda sau stocuri exacte daca nu ai date. "
    "Cand nu esti sigur, spune ce poate verifica utilizatorul in catalog, cont sau checkout."
)


app = create_base_app("chat-service")


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


@app.post("/chat/messages", response_model=ChatResponse)
def create_chat_message(payload: ChatRequest):
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    return ChatResponse(
        reply=ask_ollama(payload),
        model=OLLAMA_MODEL,
        conversation_id=conversation_id,
    )


@app.post("/messages", response_model=ChatResponse)
def create_chat_message_proxy(payload: ChatRequest):
    return create_chat_message(payload)
