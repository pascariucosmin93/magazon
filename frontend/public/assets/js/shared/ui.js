export function formatPrice(value) {
  return `${Number(value || 0).toFixed(2)} EUR`;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function toast(message) {
  const node = document.getElementById("toast");
  if (!node) {
    return;
  }
  node.innerText = message;
  node.classList.add("visible");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove("visible"), 2600);
}

export function setButtonLoading(button, loading, loadingLabel = "Se încarcă...") {
  if (!button) {
    return;
  }
  if (loading) {
    button.dataset.originalLabel = button.innerText;
    button.innerText = loadingLabel;
    button.disabled = true;
    button.classList.add("is-loading");
    return;
  }
  button.innerText = button.dataset.originalLabel || button.innerText;
  button.disabled = false;
  button.classList.remove("is-loading");
  delete button.dataset.originalLabel;
}
