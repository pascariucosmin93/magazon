import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { formatPrice, toast } from "../shared/ui.js";
import { state } from "./state.js";

let addToCartHandler = null;
let renderCartHandler = null;

export function configureCatalog({ onAddToCart, onRenderCart }) {
  addToCartHandler = onAddToCart;
  renderCartHandler = onRenderCart;
}

export function updateCategorySelect() {
  const select = document.getElementById("admin-product-category-id");
  select.innerHTML = `<option value="">Fără categorie</option>`;
  state.categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category.id;
    option.innerText = `${category.id} - ${category.name}`;
    select.appendChild(option);
  });
}

export function renderCategories() {
  const root = document.getElementById("category-list");
  const counts = state.products.reduce((acc, product) => {
    const key = product.category_id || "none";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  document.getElementById("all-count").innerText = state.products.length;
  root.innerHTML = `
    <button class="category-item ${state.selectedCategoryId === null ? "active" : ""}" onclick="selectCategory(null)">
      Toate produsele <span>${state.products.length}</span>
    </button>
  `;

  state.categories.forEach((category) => {
    const node = document.createElement("button");
    node.className = `category-item ${state.selectedCategoryId === category.id ? "active" : ""}`;
    node.onclick = () => selectCategory(category.id);
    node.innerHTML = `${category.name} <span>${counts[category.id] || 0}</span>`;
    root.appendChild(node);
  });
}

export function selectCategory(categoryId) {
  state.selectedCategoryId = categoryId;
  renderCategories();
  renderProducts();
}

export function filteredProducts() {
  const term = document.getElementById("search-input").value.trim().toLowerCase();
  const sort = document.getElementById("sort-select").value;
  let items = [...state.products];

  if (state.selectedCategoryId !== null) {
    items = items.filter((product) => product.category_id === state.selectedCategoryId);
  }

  if (term) {
    const terms = term
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .split(/\s+/)
      .filter(Boolean);

    items = items.filter((product) => {
      const haystack = `${product.name} ${product.description} ${product.category_name || ""}`
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
      return terms.every((token) => haystack.includes(token));
    });
  }

  if (sort === "price-asc") {
    items.sort((a, b) => a.price - b.price);
  } else if (sort === "price-desc") {
    items.sort((a, b) => b.price - a.price);
  } else {
    items.sort((a, b) => a.name.localeCompare(b.name));
  }

  return items;
}

function productSvg(product) {
  const category = (product.category_name || "").toLowerCase();
  const color = category.includes("keyboard") ? "#b8571b" : category.includes("mice") ? "#0f766e" : "#3156c6";
  const label = (product.name || "IT").slice(0, 2).toUpperCase();
  return `
    <svg viewBox="0 0 120 120" role="img" aria-label="${product.name}">
      <rect x="14" y="24" width="92" height="72" rx="12" fill="#ffffff" stroke="#d9cfbf" stroke-width="3"/>
      <rect x="24" y="36" width="72" height="14" rx="4" fill="${color}" opacity="0.9"/>
      <rect x="25" y="60" width="14" height="10" rx="2" fill="#e6ddcf"/>
      <rect x="44" y="60" width="14" height="10" rx="2" fill="#e6ddcf"/>
      <rect x="63" y="60" width="14" height="10" rx="2" fill="#e6ddcf"/>
      <rect x="82" y="60" width="14" height="10" rx="2" fill="#e6ddcf"/>
      <text x="60" y="88" text-anchor="middle" font-size="18" font-weight="800" fill="#18202b">${label}</text>
    </svg>
  `;
}

function productCardMarkup(product) {
  return `
    <div class="product-media">${productSvg(product)}</div>
    <div class="product-body">
      <div class="product-category">${product.category_name || "Necategorizat"}</div>
      <h3 class="product-name">${product.name}</h3>
      <p class="product-description">${product.description}</p>
      <div class="price-row">
        <span class="price">${formatPrice(product.price)}</span>
        <button class="buy-button">Adaugă</button>
      </div>
    </div>
  `;
}

function buildProductCard(product, className = "panel product-card") {
  const node = document.createElement("article");
  node.className = className;
  node.innerHTML = productCardMarkup(product);
  node.querySelector("button").onclick = () => addToCartHandler(product.id);
  return node;
}

export function renderFeaturedProducts() {
  const root = document.getElementById("featured-products");
  if (!root) {
    return;
  }

  const items = [...state.products].sort((a, b) => a.price - b.price).slice(0, 4);
  root.innerHTML = "";

  if (!items.length) {
    root.innerHTML = `<div class="panel" style="padding:18px;"><div class="empty">Produsele recomandate vor apărea după încărcarea catalogului.</div></div>`;
    return;
  }

  items.forEach((product) => {
    root.appendChild(buildProductCard(product, "panel product-card featured-product"));
  });
}

export function renderProducts() {
  const root = document.getElementById("products");
  const items = filteredProducts();
  document.getElementById("catalog-status").innerText = `${items.length} produse`;
  root.innerHTML = "";

  if (!items.length) {
    root.innerHTML = `<div class="panel" style="padding:18px;"><div class="empty">Nu am găsit produse pentru filtrul curent.</div></div>`;
    return;
  }

  items.forEach((product) => {
    root.appendChild(buildProductCard(product));
  });
}

export async function loadCategories() {
  const result = await request(`${endpoints.products}/categories`);
  state.categories = result.items || [];
  updateCategorySelect();
}

export async function loadProducts() {
  try {
    await loadCategories();
    const result = await request(`${endpoints.products}/products`);
    state.products = result.items || [];
    renderCategories();
    renderFeaturedProducts();
    renderProducts();
    if (renderCartHandler) {
      renderCartHandler();
    }
  } catch (error) {
    toast(`Nu pot încărca produsele: ${error.message}`);
    document.getElementById("catalog-status").innerText = "Eroare";
  }
}
