import {
  configureAdmin,
  createCategory,
  createProduct,
  deleteProduct,
  deleteUser,
  loadAdminData,
  updateInventory,
  updateOrderStatus,
  updateProduct
} from "./storefront/admin.js";
import { endpoints } from "./shared/constants.js";
import { request } from "./shared/http.js";
import { toast } from "./shared/ui.js";

async function loadCategories() {
  const result = await request(`${endpoints.products}/categories`);
  const select = document.getElementById("admin-product-category-id");
  select.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "Fără categorie";
  select.appendChild(empty);
  (result.items || []).forEach((category) => {
    const option = document.createElement("option");
    option.value = category.id;
    option.textContent = `${category.id} - ${category.name}`;
    select.appendChild(option);
  });
}

async function reloadCatalog() {
  await loadCategories();
}

async function adminLogout() {
  await request(`${endpoints.auth}/logout`, { method: "POST" });
  window.location.href = "/";
}

Object.assign(window, {
  adminLogout,
  createCategory,
  createProduct,
  deleteProduct,
  deleteUser,
  loadAdminData,
  updateInventory,
  updateOrderStatus,
  updateProduct
});

async function bootstrapAdmin() {
  configureAdmin({ onReloadProducts: reloadCatalog });
  try {
    const session = await request(`${endpoints.auth}/session`);
    if (session.role !== "admin") {
      throw new Error("Rolul administrator este necesar");
    }
    document.getElementById("admin-session").textContent = session.email;
    document.getElementById("admin-access").hidden = true;
    document.getElementById("admin-app").hidden = false;
    await Promise.all([loadCategories(), loadAdminData()]);
  } catch (error) {
    const access = document.getElementById("admin-access");
    access.replaceChildren();
    const title = document.createElement("h1");
    title.textContent = "Acces restricționat";
    const message = document.createElement("p");
    message.textContent = error.message;
    const login = document.createElement("a");
    login.className = "primary admin-login-link";
    login.href = "/login.html?next=%2Fadmin.html";
    login.textContent = "Login administrator";
    access.append(title, message, login);
    toast("Trebuie să fii autentificat ca administrator.");
  }
}

bootstrapAdmin();
