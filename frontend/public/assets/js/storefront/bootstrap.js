import { browseCatalog, loadProducts, renderProducts, selectCategory } from "./catalog.js";
import {
  addToCart,
  changeCartQuantity,
  clearCart,
  guestCartFromStorage,
  loadCart,
  removeFromCart,
  renderCart,
  syncGuestCartToServer
} from "./cart.js";
import { focusAccount, focusCart, goToLogin, logout, openAccount, loadSession, updateUserState } from "./session.js";
import { loadLastOrderContext } from "./storage.js";
import { state } from "./state.js";
import { configureCatalog } from "./catalog.js";
import { configureSession } from "./session.js";

function exposeGlobals() {
  Object.assign(window, {
    renderProducts,
    browseCatalog,
    selectCategory,
    focusAccount,
    focusCart,
    openAccount,
    goToLogin,
    logout,
    loadProducts,
    clearCart,
    changeCartQuantity,
    removeFromCart,
  });
}

export async function bootstrap() {
  configureCatalog({
    onAddToCart: addToCart,
    onRenderCart: () => renderCart(state.userId ? (state.cart || { items: [], total: 0 }) : guestCartFromStorage())
  });
  configureSession({
    onRenderCart: renderCart,
    getGuestCart: guestCartFromStorage
  });
  exposeGlobals();
  document.getElementById("search-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      browseCatalog();
    }
  });

  loadLastOrderContext();
  updateUserState();
  await loadProducts();

  try {
    await loadSession();
    updateUserState();
    await syncGuestCartToServer();
    await loadCart();
  } catch (_error) {
    renderCart(guestCartFromStorage());
  }
}
