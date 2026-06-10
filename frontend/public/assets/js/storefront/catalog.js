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
  if (!select) {
    return;
  }
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
  document.getElementById("search-input").value = "";
  renderCategories();
  renderProducts();
  document.getElementById("catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function normalized(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function browseCatalog(query = "") {
  const searchInput = document.getElementById("search-input");
  const requested = normalized(query);
  const matchingCategory = requested
    ? state.categories.find((category) => {
        const categoryName = normalized(category.name);
        return categoryName.includes(requested) || requested.includes(categoryName);
      })
    : null;

  state.selectedCategoryId = matchingCategory ? matchingCategory.id : null;
  searchInput.value = matchingCategory ? "" : query;
  renderCategories();
  renderProducts();
  document.getElementById("catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
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
  const category = normalized(product.category_name);
  const color = category.includes("gaming")
    ? "#cf352f"
    : category.includes("monitor")
      ? "#1da8e4"
      : category.includes("laptop")
        ? "#6d5ce7"
        : category.includes("componente")
          ? "#e18728"
          : "#238b68";
  const label = (product.category_name || "IT").slice(0, 2).toUpperCase();
  return `
    <svg viewBox="0 0 120 120" role="img" aria-label="${product.name}">
      <circle cx="60" cy="60" r="48" fill="${color}" opacity="0.1"/>
      <rect x="20" y="28" width="80" height="58" rx="11" fill="#fff" stroke="${color}" stroke-width="3"/>
      <rect x="28" y="37" width="64" height="31" rx="6" fill="${color}" opacity="0.92"/>
      <path d="M14 90h92l-8 10H22z" fill="#fff" stroke="${color}" stroke-width="3" stroke-linejoin="round"/>
      <circle cx="60" cy="53" r="12" fill="#fff" opacity="0.18"/>
      <text x="60" y="58" text-anchor="middle" font-size="13" font-weight="900" fill="#fff">${label}</text>
    </svg>
  `;
}

function productPromo(product) {
  const promos = [14, 18, 22, 25, 30];
  return promos[Math.abs(Number(product.id || 0)) % promos.length];
}

function productCardMarkup(product) {
  const promo = productPromo(product);
  return `
    <div class="product-promo">-${promo}% în coș</div>
    <div class="product-media">${productSvg(product)}</div>
    <div class="product-body">
      <div class="product-category">${product.category_name || "Necategorizat"}</div>
      <h3 class="product-name">${product.name}</h3>
      <p class="product-description">${product.description}</p>
      <div class="price-row">
        <span class="price">${formatPrice(product.price)}</span>
        <div class="product-actions">
          <a class="secondary product-details" href="/product.html?id=${product.id}">Detalii</a>
          <button class="buy-button" data-action="add">Adaugă</button>
        </div>
      </div>
    </div>
  `;
}

function buildProductCard(product, className = "panel product-card") {
  const node = document.createElement("article");
  node.className = className;
  node.innerHTML = productCardMarkup(product);
  node.querySelector('[data-action="add"]').onclick = () => addToCartHandler(product.id);
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
