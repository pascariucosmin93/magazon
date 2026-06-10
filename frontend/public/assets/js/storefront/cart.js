import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { formatPrice, toast } from "../shared/ui.js";
import { state } from "./state.js";
import {
  clearGuestCartPayload,
  guestCartPayload,
  saveGuestCartPayload
} from "./storage.js";

export function guestCartFromStorage() {
  const payload = guestCartPayload();
  const items = Object.entries(payload)
    .map(([productId, quantity]) => {
      const productIdInt = Number(productId);
      const quantityInt = Number(quantity);
      const product = state.products.find((candidate) => candidate.id === productIdInt);
      const price = product ? Number(product.price) : 0;
      return {
        product_id: productIdInt,
        quantity: quantityInt,
        price,
        name: product ? product.name : `Produs ${productIdInt}`,
        subtotal: price * quantityInt
      };
    })
    .filter((item) => item.quantity > 0);

  return {
    items,
    total: items.reduce((sum, item) => sum + item.subtotal, 0)
  };
}

export async function syncGuestCartToServer() {
  if (!state.userId) {
    return;
  }

  const entries = Object.entries(guestCartPayload());
  if (!entries.length) {
    return;
  }

  for (const [productId, quantity] of entries) {
    await request(`${endpoints.cart}/cart/add`, {
      method: "POST",
      body: JSON.stringify({
        user_id: state.userId,
        product_id: Number(productId),
        quantity: Number(quantity)
      })
    });
  }

  clearGuestCartPayload();
}

export async function addToCart(productId) {
  if (!state.userId) {
    const payload = guestCartPayload();
    payload[productId] = Number(payload[productId] || 0) + 1;
    saveGuestCartPayload(payload);
    renderCart(guestCartFromStorage());
    toast("Produs adăugat în coșul de guest.");
    return;
  }

  await request(`${endpoints.cart}/cart/add`, {
    method: "POST",
    body: JSON.stringify({ user_id: state.userId, product_id: productId, quantity: 1 })
  });
  await loadCart();
  toast("Produs adăugat în coș.");
}

export async function loadCart() {
  if (!state.userId) {
    const guestCart = guestCartFromStorage();
    renderCart(guestCart);
    return guestCart;
  }

  const result = await request(`${endpoints.cart}/cart/${state.userId}`);
  state.cart = result;
  renderCart(result);
  return result;
}

export function renderCart(cart) {
  const resolvedCart = cart || guestCartFromStorage();
  const root = document.getElementById("cart-output");
  const count = (resolvedCart.items || []).reduce((sum, item) => sum + item.quantity, 0);
  const countNode = document.getElementById("cart-count");
  if (countNode) {
    countNode.innerText = count;
  }
  if (!root) {
    return;
  }

  if (!resolvedCart.items || !resolvedCart.items.length) {
    root.innerHTML = `<div class="empty">Coșul este gol.</div>`;
    return;
  }

  const items = resolvedCart.items.map((item) => `
    <div class="line-item">
      <div>
        <strong>${item.name}</strong>
        <span>${item.quantity} x ${formatPrice(item.price)}</span>
        <div class="inline-actions">
          <button class="secondary" onclick="changeCartQuantity(${item.product_id}, ${item.quantity - 1})">-</button>
          <button class="secondary" onclick="changeCartQuantity(${item.product_id}, ${item.quantity + 1})">+</button>
          <button class="secondary" onclick="removeFromCart(${item.product_id})">Șterge</button>
        </div>
      </div>
      <strong>${formatPrice(item.subtotal)}</strong>
    </div>
  `).join("");

  root.innerHTML = `
    <div class="cart-items">${items}</div>
    <div class="summary-row">
      <span>Total</span>
      <span class="cart-total">${formatPrice(resolvedCart.total)}</span>
    </div>
  `;
}

export async function changeCartQuantity(productId, quantity) {
  if (!state.userId) {
    const payload = guestCartPayload();
    if (quantity < 1) {
      delete payload[productId];
    } else {
      payload[productId] = quantity;
    }
    saveGuestCartPayload(payload);
    renderCart(guestCartFromStorage());
    return;
  }

  await request(`${endpoints.cart}/cart/replace`, {
    method: "POST",
    body: JSON.stringify({
      user_id: state.userId,
      product_id: productId,
      quantity
    })
  });
  await loadCart();
}

export async function removeFromCart(productId) {
  if (!state.userId) {
    const payload = guestCartPayload();
    delete payload[productId];
    saveGuestCartPayload(payload);
    renderCart(guestCartFromStorage());
    toast("Produs scos din coș.");
    return;
  }

  await request(`${endpoints.cart}/cart/${state.userId}/items/${productId}`, {
    method: "DELETE"
  });
  await loadCart();
  toast("Produs scos din coș.");
}

export async function clearCart(silent = false) {
  if (!state.userId) {
    clearGuestCartPayload();
    renderCart(guestCartFromStorage());
    if (!silent) {
      toast("Coș golit.");
    }
    return;
  }

  await request(`${endpoints.cart}/cart/${state.userId}`, {
    method: "DELETE"
  });
  await loadCart();
  if (!silent) {
    toast("Coș golit.");
  }
}
