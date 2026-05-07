import { GUEST_CART_STORAGE_KEY, LAST_ORDER_STORAGE_KEY } from "../shared/constants.js";
import { state } from "./state.js";

export function resetSessionState() {
  state.userId = null;
  state.email = null;
  state.role = null;
}

export function guestCartPayload() {
  try {
    const raw = localStorage.getItem(GUEST_CART_STORAGE_KEY);
    return raw ? (JSON.parse(raw) || {}) : {};
  } catch (_error) {
    localStorage.removeItem(GUEST_CART_STORAGE_KEY);
    return {};
  }
}

export function saveGuestCartPayload(payload) {
  localStorage.setItem(GUEST_CART_STORAGE_KEY, JSON.stringify(payload));
}

export function clearGuestCartPayload() {
  localStorage.removeItem(GUEST_CART_STORAGE_KEY);
}

export function saveLastOrderContext() {
  if (!state.lastOrderId) {
    localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
    return;
  }

  localStorage.setItem(LAST_ORDER_STORAGE_KEY, JSON.stringify({
    orderId: state.lastOrderId,
    guestToken: state.lastOrderToken || null
  }));
}

export function loadLastOrderContext() {
  try {
    const raw = localStorage.getItem(LAST_ORDER_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw);
    state.lastOrderId = parsed.orderId || null;
    state.lastOrderToken = parsed.guestToken || null;
  } catch (_error) {
    localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
  }
}
