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
import { cancelCurrentOrder, loadOrder, placeOrder } from "./orders.js";
import {
  addAddress,
  cancelHistoryOrder,
  deleteAddress,
  loadAccountData,
  saveProfile,
  setDefaultAddress,
  showHistoryOrder
} from "./account.js";
import { focusAccount, focusCart, goToLogin, logout, openAccount, loadSession, updateUserState } from "./session.js";
import { loadLastOrderContext } from "./storage.js";
import { state } from "./state.js";
import { configureCatalog } from "./catalog.js";
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
    saveProfile,
    addAddress,
    setDefaultAddress,
    deleteAddress,
    showHistoryOrder,
    cancelHistoryOrder,
    cancelCurrentOrder
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

  loadLastOrderContext();
  updateUserState();
  await loadProducts();

  try {
    await loadSession();
    updateUserState();
    await syncGuestCartToServer();
    await loadCart();
    await loadAccountData();
  } catch (_error) {
    renderCart(guestCartFromStorage());
  }
}
