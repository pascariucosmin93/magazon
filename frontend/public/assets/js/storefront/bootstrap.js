import { loadProducts, renderProducts, selectCategory } from "./catalog.js";
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
import { createCategory, createProduct, deleteProduct } from "./admin.js";
import { loadOrder, placeOrder } from "./orders.js";
import { focusAccount, focusCart, goToLogin, logout, openAccount, resolveRole, updateUserState } from "./session.js";
import { loadAuth, loadLastOrderContext, saveAuth } from "./storage.js";
import { state } from "./state.js";
import { configureCatalog } from "./catalog.js";
import { configureAdmin } from "./admin.js";
import { configureSession } from "./session.js";

function exposeGlobals() {
  Object.assign(window, {
    renderProducts,
    selectCategory,
    focusAccount,
    focusCart,
    openAccount,
    goToLogin,
    logout,
    loadProducts,
    clearCart,
    placeOrder,
    loadOrder,
    changeCartQuantity,
    removeFromCart,
    createCategory,
    createProduct,
    deleteProduct
  });
}

export async function bootstrap() {
  configureCatalog({
    onAddToCart: addToCart,
    onRenderCart: () => renderCart(state.userId ? (state.cart || { items: [], total: 0 }) : guestCartFromStorage())
  });
  configureAdmin({ onReloadProducts: loadProducts });
  configureSession({
    onRenderCart: renderCart,
    getGuestCart: guestCartFromStorage
  });
  exposeGlobals();

  loadAuth();
  loadLastOrderContext();
  updateUserState();
  await loadProducts();

  if (state.userId) {
    try {
      state.role = await resolveRole(state.token, state.role);
      saveAuth();
      updateUserState();
      await syncGuestCartToServer();
      await loadCart();
    } catch (_error) {
      logout();
    }
  } else {
    renderCart(guestCartFromStorage());
  }
}
