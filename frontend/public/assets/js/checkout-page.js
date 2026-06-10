import { endpoints } from "./shared/constants.js";
import { request } from "./shared/http.js";
import { formatPrice, setButtonLoading, toast } from "./shared/ui.js";
import {
  changeCartQuantity,
  clearCart,
  guestCartFromStorage,
  loadCart,
  removeFromCart,
  syncGuestCartToServer
} from "./storefront/cart.js";
import { loadSession } from "./storefront/session.js";
import { saveLastOrderContext } from "./storefront/storage.js";
import { state } from "./storefront/state.js";

let currentStep = 1;
let currentCart = { items: [], total: 0 };
let submitting = false;

function showStep(step) {
  currentStep = step;
  document.querySelectorAll("[data-step-panel]").forEach((node) => {
    node.classList.toggle("active", Number(node.dataset.stepPanel) === step);
  });
  document.querySelectorAll("[data-step-indicator]").forEach((node) => {
    node.classList.toggle("active", Number(node.dataset.stepIndicator) === step);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function selectedDelivery() {
  if (!state.userId) {
    return {
      customer_name: document.getElementById("guest-name").value.trim(),
      customer_email: document.getElementById("guest-email").value.trim(),
      shipping_address: document.getElementById("guest-address").value.trim()
    };
  }
  const addressId = Number(document.getElementById("checkout-address").value);
  const address = state.addresses.find((item) => item.id === addressId);
  if (!address) {
    return null;
  }
  return {
    customer_name: address.recipient_name,
    customer_email: state.profile?.email || state.email,
    shipping_address: [address.line1, address.city, address.postal_code, address.country]
      .filter(Boolean)
      .join(", ")
  };
}

function validateDelivery() {
  const delivery = selectedDelivery();
  if (!delivery) {
    toast("Adaugă și selectează o adresă de livrare.");
    return false;
  }
  if (!delivery.customer_name || !delivery.customer_email || !delivery.shipping_address) {
    toast("Completează numele, emailul și adresa de livrare.");
    return false;
  }
  return true;
}

function renderAddresses() {
  const select = document.getElementById("checkout-address");
  select.innerHTML = state.addresses.map((address) => `
    <option value="${address.id}" ${address.is_default ? "selected" : ""}>
      ${address.label}: ${address.line1}, ${address.city}
    </option>
  `).join("");
}

function renderReview() {
  const delivery = selectedDelivery();
  const items = currentCart.items.map((item) => `
    <div class="line-item">
      <div>
        <strong>${item.name}</strong>
        <span>${item.quantity} x ${formatPrice(item.price)}</span>
      </div>
      <strong>${formatPrice(item.subtotal)}</strong>
    </div>
  `).join("");
  document.getElementById("checkout-review").innerHTML = `
    <div class="order-items">${items}</div>
    <div class="detail-list">
      <div class="detail-row"><span>Client</span><strong>${delivery.customer_name}</strong></div>
      <div class="detail-row"><span>Email</span><strong>${delivery.customer_email}</strong></div>
      <div class="detail-row"><span>Livrare</span><strong>${delivery.shipping_address}</strong></div>
    </div>
    <div class="summary-row"><span>Total</span><span>${formatPrice(currentCart.total)}</span></div>
  `;
}

async function refreshCart() {
  currentCart = await loadCart();
  return currentCart;
}

export async function changeCheckoutQuantity(productId, quantity) {
  await changeCartQuantity(productId, quantity);
  await refreshCart();
}

export async function removeCheckoutItem(productId) {
  await removeFromCart(productId);
  await refreshCart();
}

export async function clearCheckoutCart(button) {
  setButtonLoading(button, true, "Golim...");
  try {
    await clearCart();
    await refreshCart();
  } finally {
    setButtonLoading(button, false);
  }
}

export async function nextCheckoutStep(button) {
  if (currentStep === 1) {
    setButtonLoading(button, true, "Verificăm...");
    try {
      await refreshCart();
      if (!currentCart.items.length) {
        toast("Coșul este gol.");
        return;
      }
      showStep(2);
    } finally {
      setButtonLoading(button, false);
    }
    return;
  }
  if (currentStep === 2 && validateDelivery()) {
    renderReview();
    showStep(3);
  }
}

export function previousCheckoutStep() {
  showStep(Math.max(1, currentStep - 1));
}

export async function placeCheckoutOrder(button) {
  if (submitting || !validateDelivery()) {
    return;
  }
  submitting = true;
  setButtonLoading(button, true, "Trimitem comanda...");
  try {
    await refreshCart();
    if (!currentCart.items.length) {
      throw new Error("Coșul este gol");
    }
    const result = await request(`${endpoints.orders}/orders`, {
      method: "POST",
      body: JSON.stringify({
        items: currentCart.items.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity
        })),
        ...selectedDelivery()
      })
    });
    state.lastOrderId = result.order_id;
    state.lastOrderToken = result.guest_token || null;
    saveLastOrderContext();
    await clearCart(true);
    window.location.href = `/payment.html?order_id=${encodeURIComponent(result.order_id)}`;
  } catch (error) {
    toast(`Comanda nu a fost trimisă: ${error.message}`);
    submitting = false;
    setButtonLoading(button, false);
  }
}

export function openAccount() {
  window.location.href = state.userId
    ? "/account.html"
    : `/login.html?next=${encodeURIComponent("/checkout.html")}`;
}

Object.assign(window, {
  changeCartQuantity: changeCheckoutQuantity,
  clearCheckoutCart,
  nextCheckoutStep,
  openAccount,
  placeCheckoutOrder,
  previousCheckoutStep,
  removeFromCart: removeCheckoutItem
});

async function bootstrapCheckout() {
  try {
    const products = await request(`${endpoints.products}/products`);
    state.products = products.items || [];
    let authenticated = false;
    try {
      await loadSession();
      authenticated = true;
    } catch (_error) {
      state.userId = null;
    }

    if (authenticated) {
      await syncGuestCartToServer();
      const [profile, addresses] = await Promise.all([
        request(`${endpoints.auth}/profile`),
        request(`${endpoints.auth}/addresses`)
      ]);
      state.profile = profile;
      state.addresses = addresses.items || [];
      document.getElementById("member-delivery").classList.remove("hidden");
      document.getElementById("guest-delivery").classList.add("hidden");
      document.getElementById("account-button").innerText = "Contul meu";
      renderAddresses();
    } else {
      currentCart = guestCartFromStorage();
    }
    await refreshCart();
  } catch (error) {
    toast(`Checkout-ul nu a putut fi încărcat: ${error.message}`);
    document.getElementById("cart-output").innerHTML =
      `<div class="empty status-error">${error.message}</div>`;
  }
}

bootstrapCheckout();
