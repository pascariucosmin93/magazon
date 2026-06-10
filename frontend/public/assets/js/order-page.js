import { endpoints, LAST_ORDER_STORAGE_KEY } from "./shared/constants.js";
import { request } from "./shared/http.js";
import { escapeHtml, formatPrice, setButtonLoading, toast } from "./shared/ui.js";

const orderId = Number(new URLSearchParams(window.location.search).get("id"));
let guestToken = null;
let currentOrder = null;

const normalStatuses = ["created", "inventory_reserved", "paid", "processing", "shipped", "delivered"];
const statusLabels = {
  created: "Înregistrată",
  inventory_reserved: "Stoc rezervat",
  paid: "Plătită",
  processing: "În pregătire",
  shipped: "Expediată",
  delivered: "Livrată",
  inventory_failed: "Stoc indisponibil",
  payment_failed: "Plată eșuată",
  cancelled: "Anulată"
};

function loadGuestToken() {
  try {
    const context = JSON.parse(localStorage.getItem(LAST_ORDER_STORAGE_KEY) || "{}");
    if (Number(context.orderId) === orderId) {
      guestToken = context.guestToken || null;
    }
  } catch (_error) {
    localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
  }
}

function requestOptions(options = {}) {
  return guestToken
    ? { ...options, headers: { ...(options.headers || {}), "X-Guest-Token": guestToken } }
    : options;
}

function renderTimeline(status) {
  const failed = ["inventory_failed", "payment_failed", "cancelled"].includes(status);
  const currentIndex = normalStatuses.indexOf(status);
  document.getElementById("order-timeline").innerHTML = normalStatuses.map((step, index) => {
    let className = "timeline-step";
    if (failed && index === 0) {
      className += " failed";
    } else if (currentIndex >= 0 && index < currentIndex) {
      className += " done";
    } else if (index === currentIndex) {
      className += " current";
    }
    return `<div class="${className}">${index + 1}. ${statusLabels[step]}</div>`;
  }).join("");
}

function renderOrder(order) {
  const items = (order.items || []).map((item) => `
    <div class="line-item">
      <div>
        <strong>${escapeHtml(item.product_name || `Produs #${item.product_id}`)}</strong>
        <span>${escapeHtml(item.product_sku || `PRODUCT-${item.product_id}`)} · ${item.quantity} x ${formatPrice(item.price)}</span>
      </div>
      <strong>${formatPrice(item.quantity * item.price)}</strong>
    </div>
  `).join("");

  document.title = `Comanda #${order.order_id} | Magazon`;
  document.getElementById("order-title").innerText = `Comanda #${order.order_id}`;
  document.getElementById("order-copy").innerText =
    `Plasată ${order.created_at ? new Date(order.created_at).toLocaleString("ro-RO") : ""}.`;
  document.getElementById("order-status").innerText = statusLabels[order.status] || order.status;
  document.getElementById("order-items").innerHTML = `
    <div class="order-items">${items || `<div class="empty">Comanda nu conține produse.</div>`}</div>
    <div class="summary-row"><span>Total comandă</span><span>${formatPrice(order.total)}</span></div>
  `;
  document.getElementById("shipping-details").innerHTML = `
    <div class="detail-row"><span>Client</span><strong>${escapeHtml(order.customer_name || "-")}</strong></div>
    <div class="detail-row"><span>Email</span><strong>${escapeHtml(order.customer_email || "-")}</strong></div>
    <div class="detail-row"><span>Adresă</span><strong>${escapeHtml(order.shipping_address || "-")}</strong></div>
    ${order.cancellation_reason ? `<div class="detail-row"><span>Motiv anulare</span><strong>${escapeHtml(order.cancellation_reason)}</strong></div>` : ""}
  `;
  renderTimeline(order.status);

  const canCancel = !["cancelled", "shipped", "delivered"].includes(order.status);
  document.getElementById("cancel-order-button").classList.toggle("hidden", !canCancel);
  document.getElementById("pay-order-button").classList.toggle(
    "hidden",
    !["created", "inventory_reserved", "payment_failed"].includes(order.status)
  );
}

function renderPayment(payment) {
  document.getElementById("payment-details").innerHTML = `
    <div class="detail-row"><span>Status</span><strong>${escapeHtml(payment.status || "necunoscut")}</strong></div>
    <div class="detail-row"><span>Sumă</span><strong>${formatPrice(payment.amount || currentOrder?.total)}</strong></div>
    <div class="detail-row"><span>Rambursat</span><strong>${formatPrice(payment.refunded_amount)}</strong></div>
    <div class="detail-row"><span>Procesator</span><strong>${escapeHtml(payment.provider || "-")}</strong></div>
  `;
}

export async function refreshOrder(button) {
  if (!orderId) {
    document.getElementById("order-title").innerText = "Comandă invalidă";
    document.getElementById("order-copy").innerText = "Adresa paginii nu conține un ID valid.";
    return;
  }
  setButtonLoading(button, true, "Actualizăm...");
  try {
    currentOrder = await request(`${endpoints.orders}/orders/${orderId}`, requestOptions());
    renderOrder(currentOrder);
    try {
      const payment = await request(`${endpoints.payments}/payments/orders/${orderId}`, requestOptions());
      renderPayment(payment);
    } catch (_error) {
      document.getElementById("payment-details").innerHTML =
        `<div class="empty">Plata nu a fost creată încă pentru această comandă.</div>`;
    }
  } catch (error) {
    document.getElementById("order-title").innerText = "Comanda nu a putut fi încărcată";
    document.getElementById("order-copy").innerText = error.message;
    toast(`Comanda nu a putut fi încărcată: ${error.message}`);
  } finally {
    setButtonLoading(button, false);
  }
}

export async function cancelOrder(button) {
  setButtonLoading(button, true, "Anulăm...");
  try {
    currentOrder = await request(
      `${endpoints.orders}/orders/${orderId}/cancel`,
      requestOptions({
        method: "POST",
        body: JSON.stringify({ reason: "Anulată de client" })
      })
    );
    renderOrder(currentOrder);
    toast(`Comanda #${orderId} a fost anulată.`);
  } catch (error) {
    toast(`Comanda nu a putut fi anulată: ${error.message}`);
  } finally {
    setButtonLoading(button, false);
  }
}

export function goToPayment() {
  window.location.href = `/payment.html?order_id=${encodeURIComponent(orderId)}`;
}

Object.assign(window, { cancelOrder, goToPayment, refreshOrder });

loadGuestToken();
refreshOrder();
