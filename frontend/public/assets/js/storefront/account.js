import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { formatPrice, toast } from "../shared/ui.js";
import { state } from "./state.js";


function addressSummary(address) {
  return [address.line1, address.city, address.postal_code, address.country]
    .filter(Boolean)
    .join(", ");
}


function renderProfile() {
  if (!state.profile) {
    return;
  }
  document.getElementById("profile-username").value = state.profile.username || "";
  document.getElementById("profile-email").value = state.profile.email || "";
}


function renderAddresses() {
  const root = document.getElementById("address-list");
  const select = document.getElementById("checkout-address");
  const addresses = state.addresses || [];

  root.innerHTML = addresses.length
    ? addresses.map((address) => `
        <div class="line-item">
          <div>
            <strong>${address.label}${address.is_default ? " · implicită" : ""}</strong>
            <span>${address.recipient_name} · ${addressSummary(address)}</span>
          </div>
          <div class="inline-actions">
            ${address.is_default ? "" : `<button class="secondary" onclick="setDefaultAddress(${address.id})">Implicită</button>`}
            <button class="secondary" onclick="deleteAddress(${address.id})">Șterge</button>
          </div>
        </div>
      `).join("")
    : `<div class="empty">Nu ai nicio adresă salvată.</div>`;

  select.innerHTML = addresses.map((address) => `
    <option value="${address.id}" ${address.is_default ? "selected" : ""}>
      ${address.label}: ${addressSummary(address)}
    </option>
  `).join("");
}


function canCancel(order) {
  return !["cancelled", "shipped", "delivered"].includes(order.status);
}


export function renderOrderHistory() {
  const root = document.getElementById("order-history-output");
  const orders = state.orders || [];
  root.innerHTML = orders.length
    ? orders.map((order) => `
        <div class="line-item">
          <div>
            <strong>Comanda #${order.order_id} · ${formatPrice(order.total)}</strong>
            <span>Status: ${order.status} · ${order.created_at ? new Date(order.created_at).toLocaleString("ro-RO") : ""}</span>
            <div class="inline-actions">
              <button class="secondary" onclick="showHistoryOrder(${order.order_id})">Detalii</button>
              ${canCancel(order) ? `<button class="secondary" onclick="cancelHistoryOrder(${order.order_id})">Anulează</button>` : ""}
            </div>
          </div>
        </div>
      `).join("")
    : `<div class="empty">Nu ai plasat încă nicio comandă din acest cont.</div>`;
}


export async function loadAccountData() {
  if (!state.userId) {
    return;
  }
  const [profile, addresses, orders] = await Promise.all([
    request(`${endpoints.auth}/profile`),
    request(`${endpoints.auth}/addresses`),
    request(`${endpoints.orders}/orders/mine`)
  ]);
  state.profile = profile;
  state.addresses = addresses.items || [];
  state.orders = orders.items || [];
  renderProfile();
  renderAddresses();
  renderOrderHistory();
}


export async function saveProfile() {
  try {
    state.profile = await request(`${endpoints.auth}/profile`, {
      method: "PUT",
      body: JSON.stringify({
        username: document.getElementById("profile-username").value.trim(),
        email: document.getElementById("profile-email").value.trim()
      })
    });
    state.email = state.profile.email;
    renderProfile();
    toast("Profilul a fost actualizat.");
  } catch (error) {
    toast(`Profilul nu a fost salvat: ${error.message}`);
  }
}


export async function addAddress() {
  try {
    await request(`${endpoints.auth}/addresses`, {
      method: "POST",
      body: JSON.stringify({
        label: document.getElementById("address-label").value.trim(),
        recipient_name: document.getElementById("address-recipient").value.trim(),
        line1: document.getElementById("address-line1").value.trim(),
        city: document.getElementById("address-city").value.trim(),
        postal_code: document.getElementById("address-postal-code").value.trim(),
        country: "RO",
        is_default: document.getElementById("address-default").checked
      })
    });
    await loadAccountData();
    toast("Adresa a fost salvată.");
  } catch (error) {
    toast(`Adresa nu a fost salvată: ${error.message}`);
  }
}


export async function setDefaultAddress(addressId) {
  const address = state.addresses.find((item) => item.id === addressId);
  if (!address) {
    return;
  }
  await request(`${endpoints.auth}/addresses/${addressId}`, {
    method: "PUT",
    body: JSON.stringify({ ...address, is_default: true })
  });
  await loadAccountData();
  toast("Adresa implicită a fost schimbată.");
}


export async function deleteAddress(addressId) {
  await request(`${endpoints.auth}/addresses/${addressId}`, { method: "DELETE" });
  await loadAccountData();
  toast("Adresa a fost ștearsă.");
}


export function showHistoryOrder(orderId) {
  const order = state.orders.find((item) => item.order_id === orderId);
  if (!order) {
    return;
  }
  state.lastOrderId = orderId;
  document.getElementById("order-output").innerHTML = `
    <strong>Comanda #${order.order_id}</strong>
    <div class="muted" style="margin-top:4px;">Status: ${order.status}</div>
    <div class="summary-row"><span>Total</span><span>${formatPrice(order.total)}</span></div>
  `;
  document.getElementById("orders").scrollIntoView({ behavior: "smooth" });
}


export async function cancelHistoryOrder(orderId) {
  try {
    await request(`${endpoints.orders}/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "Anulată de client" })
    });
    await loadAccountData();
    toast(`Comanda #${orderId} a fost anulată.`);
  } catch (error) {
    toast(`Comanda nu a putut fi anulată: ${error.message}`);
  }
}


window.addEventListener("orders:changed", () => {
  if (state.userId) {
    loadAccountData().catch((error) => toast(`Istoricul nu a fost actualizat: ${error.message}`));
  }
});
