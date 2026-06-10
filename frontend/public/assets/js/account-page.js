import {
  addAddress,
  cancelHistoryOrder,
  deleteAddress,
  loadAccountData,
  saveProfile,
  setDefaultAddress,
  showHistoryOrder
} from "./storefront/account.js";
import { loadSession, logout } from "./storefront/session.js";
import { setButtonLoading, toast } from "./shared/ui.js";
import { state } from "./storefront/state.js";

async function logoutFromAccount(button) {
  setButtonLoading(button, true, "Ieșim...");
  await logout();
  window.location.href = "/";
}

Object.assign(window, {
  addAddress,
  cancelHistoryOrder,
  deleteAddress,
  logoutFromAccount,
  saveProfile,
  setDefaultAddress,
  showHistoryOrder
});

async function bootstrapAccount() {
  try {
    await loadSession();
    await loadAccountData();
    document.getElementById("account-summary").innerText =
      `Autentificat ca ${state.email}. Poți actualiza profilul, adresele și comenzile din aceeași pagină.`;
  } catch (error) {
    toast(`Contul nu a putut fi încărcat: ${error.message}`);
    window.setTimeout(() => {
      window.location.href = `/login.html?next=${encodeURIComponent("/account.html")}`;
    }, 500);
  }
}

bootstrapAccount();
