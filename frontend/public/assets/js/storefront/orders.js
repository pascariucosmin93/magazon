import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { formatPrice, toast } from "../shared/ui.js";
import { state } from "./state.js";
import { clearCart, loadCart } from "./cart.js";
import { saveLastOrderContext } from "./storage.js";

export async function placeOrder() {
  try {
    const cart = await loadCart();
    if (!cart.items.length) {
      toast("Coșul este gol.");
      return;
    }

    document.getElementById("catalog-status").innerText = "Trimitem comanda...";

    const body = {
      items: cart.items.map((item) => ({
        product_id: item.product_id,
        quantity: item.quantity
      }))
    };
    const requestOptions = { method: "POST", body: JSON.stringify(body) };

    if (!state.userId) {
      const customerName = document.getElementById("guest-name").value.trim();
      const customerEmail = document.getElementById("guest-email").value.trim();
      const shippingAddress = document.getElementById("guest-address").value.trim();

      if (!customerName || !customerEmail || !shippingAddress) {
        toast("Completează nume, email și adresă pentru comanda ca guest.");
        return;
      }

      body.customer_name = customerName;
      body.customer_email = customerEmail;
      body.shipping_address = shippingAddress;
      requestOptions.body = JSON.stringify(body);
    }

    const result = await request(`${endpoints.orders}/orders`, requestOptions);
    state.lastOrderId = result.order_id;
    state.lastOrderToken = result.guest_token || null;
    saveLastOrderContext();
    renderOrder(result);
    await clearCart(true);

    if (!state.userId) {
      document.getElementById("guest-name").value = "";
      document.getElementById("guest-email").value = "";
      document.getElementById("guest-address").value = "";
    }

    toast(`Comanda #${result.order_id} a fost plasată.`);
    window.setTimeout(() => {
      loadOrder().catch(() => {});
    }, 1500);
  } catch (error) {
    document.getElementById("catalog-status").innerText = "Eroare la comandă";
    toast(`Comanda nu a fost trimisă: ${error.message}`);
  }
}

export async function loadOrder() {
  if (!state.lastOrderId) {
    toast("Nu există o comandă recentă în sesiune.");
    return;
  }

  const url = `${endpoints.orders}/orders/${state.lastOrderId}`;
  const options = !state.userId && state.lastOrderToken
    ? { headers: { "X-Guest-Token": state.lastOrderToken } }
    : {};

  const result = await request(url, options);
  renderOrder(result);

  if (result.status === "paid") {
    document.getElementById("catalog-status").innerText = "Plata finalizată";
  } else if (result.status === "inventory_failed") {
    document.getElementById("catalog-status").innerText = "Stoc insuficient";
  } else if (result.status === "payment_failed") {
    document.getElementById("catalog-status").innerText = "Plata eșuată";
  } else {
    document.getElementById("catalog-status").innerText = "Comandă în procesare";
  }
}

export function renderOrder(order) {
  const root = document.getElementById("order-output");
  const items = (order.items || []).map((item) => {
    const product = state.products.find((candidate) => candidate.id === item.product_id);
    const name = product ? product.name : `Produs ${item.product_id}`;
    return `
      <div class="line-item">
        <div>
          <strong>${name}</strong>
          <span>${item.quantity} x ${formatPrice(item.price)}</span>
        </div>
        <strong>${formatPrice(item.quantity * item.price)}</strong>
      </div>
    `;
  }).join("");

  root.innerHTML = `
    <strong>Comanda #${order.order_id}</strong>
    <div class="muted" style="margin-top:4px;">Status: ${order.status}</div>
    <div class="order-items">${items || `<div class="empty">Nu există linii de comandă.</div>`}</div>
    <div class="summary-row">
      <span>Total</span>
      <span>${formatPrice(order.total)}</span>
    </div>
  `;
}
