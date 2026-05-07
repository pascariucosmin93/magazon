import { endpoints, LAST_ORDER_STORAGE_KEY } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { toast } from "../shared/ui.js";
import { state } from "./state.js";

let renderCartHandler = null;
let guestCartProvider = null;

export function configureSession({ onRenderCart, getGuestCart }) {
  renderCartHandler = onRenderCart;
  guestCartProvider = getGuestCart;
}

export function goToLogin() {
  window.location.href = `/login.html?next=${encodeURIComponent(window.location.pathname || "/")}`;
}

export function focusAccount() {
  document.getElementById("account").scrollIntoView({ behavior: "smooth", block: "start" });
}

export function openAccount() {
  if (state.userId) {
    focusAccount();
    return;
  }
  goToLogin();
}

export function focusCart() {
  document.getElementById("cart").scrollIntoView({ behavior: "smooth", block: "start" });
}

export function toggleGuestCheckout() {
  const showGuest = !state.userId;
  document.getElementById("guest-checkout-fields").classList.toggle("hidden", !showGuest);
  document.getElementById("guest-note").classList.toggle("hidden", !showGuest);
}

export function updateUserState() {
  document.getElementById("user-state").innerText = state.email ? state.email : "Vizitator";
  document.getElementById("user-role").innerText = state.role
    ? `Rol: ${state.role}`
    : "Poți cumpăra ca guest sau te poți autentifica pentru un flux mai rapid.";
  document.getElementById("account-button").innerText = state.email ? "Contul meu" : "Login / Cont";
  document.getElementById("logout-button").style.display = state.userId ? "inline-flex" : "none";
  const isAdmin = state.role === "admin";
  document.getElementById("admin-panel").classList.toggle("visible", isAdmin);
  document.getElementById("admin-nav").style.display = isAdmin ? "inline" : "none";
  toggleGuestCheckout();
}

export async function loadSession() {
  const session = await request(`${endpoints.auth}/session`);
  state.userId = session.user_id;
  state.email = session.email;
  state.role = session.role;
  return session;
}

export async function logout() {
  try {
    await request(`${endpoints.auth}/logout`, { method: "POST" });
  } catch (_error) {
    // Best effort logout; local state still gets cleared.
  }
  state.userId = null;
  state.email = null;
  state.role = null;
  state.lastOrderId = null;
  state.lastOrderToken = null;
  state.cart = null;
  localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
  document.getElementById("order-output").innerHTML = `<div class="empty">Nu există încă o comandă trimisă din sesiunea curentă.</div>`;
  if (renderCartHandler && guestCartProvider) {
    renderCartHandler(guestCartProvider());
  }
  updateUserState();
  toast("Deconectat.");
}
