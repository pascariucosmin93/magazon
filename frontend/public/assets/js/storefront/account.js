import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { escapeHtml, formatPrice, setButtonLoading, toast } from "../shared/ui.js";
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
  const username = document.getElementById("profile-username");
  const email = document.getElementById("profile-email");
  if (username) {
    username.value = state.profile.username || "";
  }
  if (email) {
    email.value = state.profile.email || "";
  }
}


function renderAddresses() {
  const root = document.getElementById("address-list");
  const select = document.getElementById("checkout-address");
  const addresses = state.addresses || [];

  if (root) {
    root.innerHTML = addresses.length
      ? addresses.map((address) => `
        <div class="line-item">
          <div>
            <strong>${escapeHtml(address.label)}${address.is_default ? " · implicită" : ""}</strong>
            <span>${escapeHtml(address.recipient_name)} · ${escapeHtml(addressSummary(address))}</span>
          </div>
          <div class="inline-actions">
            ${address.is_default ? "" : `<button class="secondary" onclick="setDefaultAddress(${address.id}, this)">Implicită</button>`}
            <button class="secondary" onclick="deleteAddress(${address.id}, this)">Șterge</button>
          </div>
        </div>
      `).join("")
      : `<div class="empty">Nu ai nicio adresă salvată.</div>`;
  }

  if (select) {
    select.innerHTML = addresses.map((address) => `
      <option value="${address.id}" ${address.is_default ? "selected" : ""}>
        ${escapeHtml(address.label)}: ${escapeHtml(addressSummary(address))}
      </option>
    `).join("");
  }
}


function canCancel(order) {
  return !["cancelled", "shipped", "delivered"].includes(order.status);
}


export function renderOrderHistory() {
  const root = document.getElementById("order-history-output");
  if (!root) {
    return;
  }
  const orders = state.orders || [];
  root.innerHTML = orders.length
    ? orders.map((order) => `
        <div class="line-item">
          <div>
            <strong>Comanda #${order.order_id} · ${formatPrice(order.total)}</strong>
            <span>Status: ${escapeHtml(order.status)} · ${order.created_at ? new Date(order.created_at).toLocaleString("ro-RO") : ""}</span>
            <div class="inline-actions">
              <button class="secondary" onclick="showHistoryOrder(${order.order_id})">Detalii</button>
              ${canCancel(order) ? `<button class="secondary" onclick="cancelHistoryOrder(${order.order_id}, this)">Anulează</button>` : ""}
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


export async function saveProfile(button) {
  setButtonLoading(button, true, "Salvăm...");
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
  } finally {
    setButtonLoading(button, false);
  }
}


export async function addAddress(button) {
  setButtonLoading(button, true, "Adăugăm...");
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
  } finally {
    setButtonLoading(button, false);
  }
}


export async function setDefaultAddress(addressId, button) {
  const address = state.addresses.find((item) => item.id === addressId);
  if (!address) {
    return;
  }
  setButtonLoading(button, true, "Salvăm...");
  try {
    await request(`${endpoints.auth}/addresses/${addressId}`, {
      method: "PUT",
      body: JSON.stringify({ ...address, is_default: true })
    });
    await loadAccountData();
    toast("Adresa implicită a fost schimbată.");
  } catch (error) {
    toast(`Adresa implicită nu a fost schimbată: ${error.message}`);
  } finally {
    setButtonLoading(button, false);
  }
}


export async function deleteAddress(addressId, button) {
  setButtonLoading(button, true, "Ștergem...");
  try {
    await request(`${endpoints.auth}/addresses/${addressId}`, { method: "DELETE" });
    await loadAccountData();
    toast("Adresa a fost ștearsă.");
  } catch (error) {
    toast(`Adresa nu a fost ștearsă: ${error.message}`);
  } finally {
    setButtonLoading(button, false);
  }
}


export function showHistoryOrder(orderId) {
  window.location.href = `/order.html?id=${encodeURIComponent(orderId)}`;
}


export async function cancelHistoryOrder(orderId, button) {
  setButtonLoading(button, true, "Anulăm...");
  try {
    await request(`${endpoints.orders}/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "Anulată de client" })
    });
    await loadAccountData();
    toast(`Comanda #${orderId} a fost anulată.`);
  } catch (error) {
    toast(`Comanda nu a putut fi anulată: ${error.message}`);
  } finally {
    setButtonLoading(button, false);
  }
}


window.addEventListener("orders:changed", () => {
  if (state.userId) {
    loadAccountData().catch((error) => toast(`Istoricul nu a fost actualizat: ${error.message}`));
  }
});
