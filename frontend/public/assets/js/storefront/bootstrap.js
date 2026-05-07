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
import { focusAccount, focusCart, goToLogin, logout, openAccount, loadSession, updateUserState } from "./session.js";
import { loadLastOrderContext } from "./storage.js";
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
