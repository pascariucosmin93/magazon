import { endpoints, GUEST_CART_STORAGE_KEY } from "./shared/constants.js";
import { request } from "./shared/http.js";
import { formatPrice, toast } from "./shared/ui.js";

let currentProduct = null;
let currentUserId = null;
let currentStock = null;

function guestCart() {
  try {
    return JSON.parse(localStorage.getItem(GUEST_CART_STORAGE_KEY) || "{}") || {};
  } catch (_error) {
    return {};
  }
}

function updateGuestCartCount() {
  const count = Object.values(guestCart()).reduce((sum, quantity) => sum + Number(quantity || 0), 0);
  document.getElementById("product-cart-count").textContent = count;
}

async function loadSession() {
  try {
    const session = await request(`${endpoints.auth}/session`);
    currentUserId = session.user_id;
    document.getElementById("product-account").textContent = session.email;
    document.getElementById("product-account").href = session.role === "admin" ? "/admin.html" : "/#account";
    const cart = await request(`${endpoints.cart}/cart/${currentUserId}`);
    const count = (cart.items || []).reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    document.getElementById("product-cart-count").textContent = count;
  } catch (_error) {
    currentUserId = null;
    const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
    document.getElementById("product-account").href = `/login.html?next=${next}`;
    updateGuestCartCount();
  }
}

function renderProduct(product) {
  document.title = `${product.name} | Magazon`;
  document.getElementById("product-breadcrumb").textContent = product.name;
  const root = document.getElementById("product-detail");
  root.replaceChildren();

  const visual = document.createElement("div");
  visual.className = "product-visual";
  const initials = document.createElement("div");
  initials.className = "product-initials";
  initials.textContent = product.name.slice(0, 2).toUpperCase();
  visual.appendChild(initials);

  const info = document.createElement("div");
  info.className = "product-info";
  const category = document.createElement("span");
  category.className = "eyebrow";
  category.textContent = product.category_name || "Produs";
  const title = document.createElement("h1");
  title.textContent = product.name;
  const description = document.createElement("p");
  description.className = "product-copy";
  description.textContent = product.description;
  const price = document.createElement("div");
  price.className = "product-price";
  price.textContent = formatPrice(product.price);
  const stock = document.createElement("span");
  stock.className = `product-stock${currentStock === 0 ? " unavailable" : ""}`;
  stock.textContent = currentStock === null
    ? "Stoc în curs de verificare"
    : currentStock > 0
      ? `${currentStock} bucăți disponibile`
      : "Indisponibil momentan";

  const purchase = document.createElement("div");
  purchase.className = "product-purchase";
  const quantity = document.createElement("input");
  quantity.id = "product-quantity";
  quantity.type = "number";
  quantity.min = "1";
  quantity.max = currentStock > 0 ? String(currentStock) : "99";
  quantity.value = "1";
  quantity.setAttribute("aria-label", "Cantitate");
  const addButton = document.createElement("button");
  addButton.className = "primary";
  addButton.textContent = "Adaugă în coș";
  addButton.disabled = currentStock === 0;
  addButton.onclick = addCurrentProductToCart;
  purchase.append(quantity, addButton);
  info.append(category, title, description, price, stock, purchase);
  root.append(visual, info);
}

async function addCurrentProductToCart() {
  const quantity = Number(document.getElementById("product-quantity").value);
  if (!Number.isInteger(quantity) || quantity < 1 || (currentStock !== null && quantity > currentStock)) {
    toast("Cantitatea selectată nu este validă.");
    return;
  }

  try {
    if (currentUserId) {
      await request(`${endpoints.cart}/cart/add`, {
        method: "POST",
        body: JSON.stringify({
          user_id: currentUserId,
          product_id: currentProduct.id,
          quantity
        })
      });
      const cart = await request(`${endpoints.cart}/cart/${currentUserId}`);
      const count = (cart.items || []).reduce((sum, item) => sum + Number(item.quantity || 0), 0);
      document.getElementById("product-cart-count").textContent = count;
    } else {
      const cart = guestCart();
      cart[currentProduct.id] = Number(cart[currentProduct.id] || 0) + quantity;
      localStorage.setItem(GUEST_CART_STORAGE_KEY, JSON.stringify(cart));
      updateGuestCartCount();
    }
    toast("Produs adăugat în coș.");
  } catch (error) {
    toast(`Produsul nu a fost adăugat: ${error.message}`);
  }
}

async function bootstrapProduct() {
  const productId = Number(new URLSearchParams(window.location.search).get("id"));
  if (!productId) {
    document.getElementById("product-detail").textContent = "Produsul solicitat nu este valid.";
    return;
  }

  await loadSession();
  try {
    currentProduct = await request(`${endpoints.products}/products/${productId}`);
    try {
      const inventory = await request(`${endpoints.inventory}/inventory/${productId}`);
      currentStock = Number(inventory.stock);
    } catch (_error) {
      currentStock = 0;
    }
    renderProduct(currentProduct);
  } catch (error) {
    const root = document.getElementById("product-detail");
    root.replaceChildren();
    const message = document.createElement("div");
    message.className = "product-loading";
    message.textContent = error.message;
    root.appendChild(message);
  }
}

bootstrapProduct();
