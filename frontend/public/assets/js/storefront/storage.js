import {
  AUTH_STORAGE_KEY,
  GUEST_CART_STORAGE_KEY,
  LAST_ORDER_STORAGE_KEY
} from "../shared/constants.js";
import { state } from "./state.js";

export function saveAuth() {
  if (!state.token || !state.userId) {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    return;
  }

  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
    userId: state.userId,
    email: state.email,
    token: state.token,
    role: state.role
  }));
}

export function loadAuth() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw);
    state.userId = parsed.userId || null;
    state.email = parsed.email || null;
    state.token = parsed.token || null;
    state.role = parsed.role || null;
  } catch (_error) {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  }
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
