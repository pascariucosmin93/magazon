const state = {
  open: false,
  busy: false,
  conversationId: null,
  history: []
};

function trimHistory() {
  state.history = state.history.slice(-12);
}

function renderMessage(role, content) {
  const messages = document.getElementById("chat-messages");
  if (!messages) return;
  const item = document.createElement("div");
  item.className = `chat-message ${role}`;
  item.textContent = content;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function setBusy(value) {
  state.busy = value;
  const button = document.getElementById("chat-send");
  const input = document.getElementById("chat-input");
  if (button) button.disabled = value;
  if (input) input.disabled = value;
}

async function sendChatMessage() {
  const input = document.getElementById("chat-input");
  if (!input || state.busy) return;

  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  renderMessage("user", message);
  setBusy(true);

  try {
    const response = await fetch("/api/chat/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: state.conversationId,
        history: state.history
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Asistentul nu este disponibil.");
    }

    state.conversationId = payload.conversation_id || state.conversationId;
    state.history.push({ role: "user", content: message });
    state.history.push({ role: "assistant", content: payload.reply });
    trimHistory();
    renderMessage("assistant", payload.reply);
  } catch (error) {
    renderMessage("assistant", error.message || "Asistentul nu este disponibil.");
  } finally {
    setBusy(false);
    input.focus();
  }
}

function toggleChat() {
  state.open = !state.open;
  const panel = document.getElementById("chat-panel");
  const toggle = document.getElementById("chat-toggle");
  if (!panel || !toggle) return;

  panel.hidden = !state.open;
  toggle.setAttribute("aria-expanded", String(state.open));
  if (state.open) {
    document.getElementById("chat-input")?.focus();
  }
}

function handleChatKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChatMessage();
  }
}

window.toggleChat = toggleChat;
window.sendChatMessage = sendChatMessage;
window.handleChatKeydown = handleChatKeydown;
