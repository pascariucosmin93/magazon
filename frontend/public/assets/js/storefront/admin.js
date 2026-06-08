import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { toast } from "../shared/ui.js";

let reloadProducts = null;

export function configureAdmin({ onReloadProducts }) {
  reloadProducts = onReloadProducts;
}

function renderTable(containerId, columns, items, emptyMessage) {
  const container = document.getElementById(containerId);
  container.replaceChildren();

  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = emptyMessage;
    container.appendChild(empty);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "admin-table-wrap";
  const table = document.createElement("table");
  table.className = "admin-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");

  columns.forEach(({ label }) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.appendChild(cell);
  });
  head.appendChild(headRow);

  const body = document.createElement("tbody");
  items.forEach((item) => {
    const row = document.createElement("tr");
    columns.forEach(({ key, format }) => {
      const cell = document.createElement("td");
      const value = format ? format(item[key], item) : item[key];
      cell.textContent = value ?? "-";
      row.appendChild(cell);
    });
    body.appendChild(row);
  });

  table.append(head, body);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

function productPayload() {
  const categoryValue = document.getElementById("admin-product-category-id").value;
  return {
    name: document.getElementById("admin-product-name").value.trim(),
    description: document.getElementById("admin-product-description").value.trim(),
    price: Number(document.getElementById("admin-product-price").value),
    category_id: categoryValue ? Number(categoryValue) : null
  };
}

function showAdminResult(result) {
  document.getElementById("admin-output").innerText = JSON.stringify(result, null, 2);
}

export async function loadAdminData() {
  try {
    const [users, orders, inventory, payments] = await Promise.all([
      request(`${endpoints.auth}/users`),
      request(`${endpoints.orders}/orders`),
      request(`${endpoints.inventory}/inventory`),
      request(`${endpoints.payments}/payments`)
    ]);

    document.getElementById("admin-user-count").textContent = users.total;
    document.getElementById("admin-order-count").textContent = orders.total;
    document.getElementById("admin-stock-count").textContent = inventory.total;
    document.getElementById("admin-payment-count").textContent = payments.length;

    renderTable(
      "admin-users",
      [
        { key: "id", label: "ID" },
        { key: "username", label: "Utilizator" },
        { key: "email", label: "Email" },
        { key: "role", label: "Rol" },
        { key: "created_at", label: "Creat", format: (value) => value ? new Date(value).toLocaleString("ro-RO") : "-" }
      ],
      users.items,
      "Nu există utilizatori."
    );
    renderTable(
      "admin-orders",
      [
        { key: "order_id", label: "Comandă" },
        { key: "customer_email", label: "Client", format: (value, item) => value || (item.user_id ? `User #${item.user_id}` : "Guest") },
        { key: "status", label: "Status" },
        { key: "total", label: "Total", format: (value) => `${Number(value).toFixed(2)} lei` },
        { key: "items", label: "Produse", format: (value) => String(value.length) }
      ],
      orders.items,
      "Nu există comenzi."
    );
    renderTable(
      "admin-inventory",
      [
        { key: "product_id", label: "Produs ID" },
        { key: "stock", label: "Stoc" },
        { key: "updated_at", label: "Actualizat", format: (value) => value ? new Date(value).toLocaleString("ro-RO") : "-" }
      ],
      inventory.items,
      "Nu există înregistrări de stoc."
    );
    renderTable(
      "admin-payments",
      [
        { key: "order_id", label: "Comandă" },
        { key: "amount", label: "Sumă", format: (value, item) => `${Number(value).toFixed(2)} ${String(item.currency).toUpperCase()}` },
        { key: "provider", label: "Procesator" },
        { key: "status", label: "Status" }
      ],
      payments,
      "Nu există plăți."
    );
  } catch (error) {
    toast(`Datele de administrare nu au fost încărcate: ${error.message}`);
  }
}

export async function createCategory() {
  try {
    const result = await request(`${endpoints.products}/categories`, {
      method: "POST",
      body: JSON.stringify({
        name: document.getElementById("category-name").value,
        description: document.getElementById("category-description").value
      })
    });
    showAdminResult(result);
    await reloadProducts();
    toast("Categorie adăugată.");
  } catch (error) {
    toast(`Categoria nu a fost creată: ${error.message}`);
  }
}

export async function createProduct() {
  try {
    const result = await request(`${endpoints.products}/products`, {
      method: "POST",
      body: JSON.stringify(productPayload())
    });
    showAdminResult(result);
    await reloadProducts();
    toast("Produs adăugat.");
  } catch (error) {
    toast(`Produsul nu a fost creat: ${error.message}`);
  }
}

export async function updateProduct() {
  try {
    const productId = Number(document.getElementById("admin-product-id").value);
    if (!productId) {
      throw new Error("Completează ID-ul produsului");
    }
    const result = await request(`${endpoints.products}/products/${productId}`, {
      method: "PUT",
      body: JSON.stringify(productPayload())
    });
    showAdminResult(result);
    await reloadProducts();
    toast("Produs actualizat.");
  } catch (error) {
    toast(`Produsul nu a fost actualizat: ${error.message}`);
  }
}

export async function deleteProduct() {
  try {
    const productId = Number(document.getElementById("admin-product-id").value);
    if (!productId) {
      throw new Error("Completează ID-ul produsului");
    }
    const result = await request(`${endpoints.products}/products/${productId}`, {
      method: "DELETE"
    });
    showAdminResult(result);
    await reloadProducts();
    toast("Produs șters.");
  } catch (error) {
    toast(`Produsul nu a fost șters: ${error.message}`);
  }
}

export async function updateInventory() {
  try {
    const productId = Number(document.getElementById("admin-stock-product-id").value);
    const stock = Number(document.getElementById("admin-stock-value").value);
    if (!productId || !Number.isInteger(stock) || stock < 0) {
      throw new Error("Produsul și stocul trebuie să fie valori valide");
    }
    const result = await request(`${endpoints.inventory}/inventory/seed`, {
      method: "POST",
      body: JSON.stringify({ product_id: productId, stock })
    });
    showAdminResult(result);
    await loadAdminData();
    toast("Stoc actualizat.");
  } catch (error) {
    toast(`Stocul nu a fost actualizat: ${error.message}`);
  }
}
