export function formatPrice(value) {
  return `${Number(value || 0).toFixed(2)} EUR`;
}

export function toast(message) {
  const node = document.getElementById("toast");
  node.innerText = message;
  node.classList.add("visible");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove("visible"), 2600);
}
