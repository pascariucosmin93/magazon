import { endpoints, LAST_ORDER_STORAGE_KEY } from "./shared/constants.js";
import { request } from "./shared/http.js";
import { escapeHtml, formatPrice, setButtonLoading, toast } from "./shared/ui.js";

const params = new URLSearchParams(window.location.search);
const queryOrderId = params.get("order_id");
const checkoutState = params.get("checkout");
let orderId = queryOrderId ? Number(queryOrderId) : null;
let guestToken = null;

function loadStoredContext() {
  try {
    const raw = localStorage.getItem(LAST_ORDER_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw);
    if (!orderId && parsed.orderId) {
      orderId = Number(parsed.orderId);
    }
    guestToken = parsed.guestToken || null;
  } catch (_error) {
    localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
  }
}

function requestOptions() {
  return guestToken ? { headers: { "X-Guest-Token": guestToken } } : {};
}

function setStatus(label, copy, canPay = false) {
  document.getElementById("payment-status-badge").innerText = label;
  document.getElementById("payment-copy").innerText = copy;
  document.getElementById("pay-now-button").disabled = !canPay;
}

function renderSummary(order, payment) {
  const items = (order.items || []).map((item) => `
    <div class="line-item">
      <div>
        <strong>${escapeHtml(item.product_name || `Produs #${item.product_id}`)}</strong>
        <span>${escapeHtml(item.product_sku || `PRODUCT-${item.product_id}`)} · ${item.quantity} x ${formatPrice(item.price)}</span>
      </div>
      <strong>${formatPrice(item.quantity * item.price)}</strong>
    </div>
  `).join("");

  document.getElementById("payment-order-output").innerHTML = `
    <strong>Comanda #${order.order_id}</strong>
    <div class="muted" style="margin-top:4px;">Status comandă: ${escapeHtml(order.status)}</div>
    <div class="muted" style="margin-top:4px;">Status plată: ${escapeHtml(payment.status)}</div>
    <div class="order-items" style="margin-top:16px;">${items}</div>
    <div class="summary-row">
      <span>Total de plată</span>
      <span>${formatPrice(payment.amount || order.total)}</span>
    </div>
  `;
}

async function loadOrder() {
  return request(`${endpoints.orders}/orders/${orderId}`, requestOptions());
}

async function loadPayment() {
  return request(`${endpoints.payments}/payments/orders/${orderId}`, requestOptions());
}

async function confirmSuccessfulCheckout() {
  if (checkoutState !== "success") {
    return null;
  }
  return request(`${endpoints.payments}/payments/orders/${orderId}/confirm`, {
    method: "POST",
    ...(requestOptions())
  });
}

export async function refreshPaymentState(button) {
  if (!orderId) {
    setStatus("Lipsește comanda", "Nu există order_id pentru această pagină.");
    return;
  }

  setButtonLoading(button, true, "Verificăm...");
  try {
    const order = await loadOrder();
    const confirmed = await confirmSuccessfulCheckout();
    const payment = confirmed || await loadPayment();
    renderSummary(order, payment);

    if (payment.status === "completed" || order.status === "paid") {
      setStatus("Plată finalizată", "Plata a fost confirmată și comanda este marcată ca paid.");
      toast(`Plata pentru comanda #${orderId} a fost confirmată.`);
      return;
    }

    if (payment.status === "payment_failed") {
      setStatus("Plată eșuată", "Sesiunea de plată a expirat sau nu a fost confirmată.");
      return;
    }

    if (payment.status === "waiting_for_inventory" || order.status === "created") {
      setStatus("Așteptăm stocul", "Comanda a fost înregistrată. Așteptăm rezervarea stocului înainte de plată.");
      return;
    }

    if (payment.status === "awaiting_payment" || payment.status === "checkout_created" || order.status === "inventory_reserved") {
      setStatus("Gata de plată", "Stocul este rezervat. Poți continua spre pagina securizată de plată.", true);
      return;
    }

    setStatus("În procesare", "Verificăm statusul plății și al comenzii.");
  } catch (error) {
    setStatus("Eroare", `Nu am putut încărca plata: ${error.message}`);
    toast(`Plata nu a putut fi încărcată: ${error.message}`);
  } finally {
    setButtonLoading(button, false);
  }
}

export async function startPayment(button) {
  setButtonLoading(button, true, "Deschidem plata...");
  try {
    const result = await request(`${endpoints.payments}/payments/orders/${orderId}/checkout-session`, {
      method: "POST",
      body: JSON.stringify({ return_base_url: window.location.origin }),
      ...(requestOptions())
    });
    if (!result.checkout_url) {
      throw new Error("Checkout URL indisponibil");
    }
    window.location.href = result.checkout_url;
  } catch (error) {
    toast(`Plata nu a putut fi inițiată: ${error.message}`);
    setButtonLoading(button, false);
  }
}

export function goToOrderDetails() {
  window.location.href = `/order.html?id=${encodeURIComponent(orderId)}`;
}

Object.assign(window, { goToOrderDetails, startPayment, refreshPaymentState });

loadStoredContext();
refreshPaymentState();
