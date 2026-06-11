import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { toast } from "../shared/ui.js";

let reloadProducts = null;
const ORDER_STATUS_TRANSITIONS = {
  created: ["cancelled"],
  inventory_reserved: ["cancelled"],
  inventory_failed: ["cancelled"],
  payment_failed: ["cancelled"],
  paid: ["processing", "cancelled"],
  processing: ["shipped", "cancelled"],
  shipped: ["delivered"],
  delivered: [],
  cancelled: []
};
const ORDER_STATUS_LABELS = {
  created: "Creată",
  inventory_reserved: "Stoc rezervat",
  inventory_failed: "Stoc insuficient",
  payment_failed: "Plată eșuată",
  paid: "Plătită",
  processing: "În procesare",
  shipped: "Expediată",
  delivered: "Livrată",
  cancelled: "Anulată"
};

export function configureAdmin({ onReloadProducts }) {
  reloadProducts = onReloadProducts;
}

function selectedImportFile() {
  const input = document.getElementById("admin-import-file");
  return input?.files?.[0] || null;
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
  const sku = document.getElementById("admin-product-sku").value.trim();
  return {
    sku: sku || null,
    name: document.getElementById("admin-product-name").value.trim(),
    description: document.getElementById("admin-product-description").value.trim(),
    price: Number(document.getElementById("admin-product-price").value),
    category_id: categoryValue ? Number(categoryValue) : null
  };
}

function validateProductPayload(payload) {
  if (!payload.name || !payload.description) {
    throw new Error("Completează numele și descrierea produsului");
  }
  if (!Number.isFinite(payload.price) || payload.price <= 0) {
    throw new Error("Prețul trebuie să fie mai mare decât 0");
  }
}

export function clearProductForm() {
  document.getElementById("admin-product-id").value = "";
  document.getElementById("admin-product-sku").value = "";
  document.getElementById("admin-product-name").value = "";
  document.getElementById("admin-product-description").value = "";
  document.getElementById("admin-product-price").value = "";
  document.getElementById("admin-product-category-id").value = "";
  document.getElementById("admin-product-editor-title").textContent = "Produs nou";
  document.getElementById("admin-product-create").hidden = false;
  document.getElementById("admin-product-update").hidden = true;
  document.getElementById("admin-product-delete").hidden = true;
  document.getElementById("admin-product-cancel").hidden = true;
}

export function editProduct(product) {
  document.getElementById("admin-product-id").value = product.id;
  document.getElementById("admin-product-sku").value = product.sku || "";
  document.getElementById("admin-product-name").value = product.name || "";
  document.getElementById("admin-product-description").value = product.description || "";
  document.getElementById("admin-product-price").value = Number(product.price).toFixed(2);
  document.getElementById("admin-product-category-id").value = product.category_id ?? "";
  document.getElementById("admin-product-editor-title").textContent = `Editezi produsul #${product.id}`;
  document.getElementById("admin-product-create").hidden = true;
  document.getElementById("admin-product-update").hidden = false;
  document.getElementById("admin-product-delete").hidden = false;
  document.getElementById("admin-product-cancel").hidden = false;
  document.getElementById("admin-product-editor").scrollIntoView({ behavior: "smooth", block: "center" });
  document.getElementById("admin-product-price").focus({ preventScroll: true });
}

function renderProducts(items) {
  const container = document.getElementById("admin-products");
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Nu există produse.";
    container.appendChild(empty);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "admin-table-wrap";
  const table = document.createElement("table");
  table.className = "admin-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["ID", "SKU", "Produs", "Categorie", "Preț", "Status", "Acțiune"].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.appendChild(cell);
  });
  head.appendChild(headRow);

  const body = document.createElement("tbody");
  items.forEach((product) => {
    const row = document.createElement("tr");
    [
      product.id,
      product.sku,
      product.name,
      product.category_name || "Fără categorie",
      `${Number(product.price).toFixed(2)} EUR`,
      product.archived ? "Arhivat" : "Activ"
    ].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    const actionCell = document.createElement("td");
    const editButton = document.createElement("button");
    editButton.className = "secondary admin-edit-button";
    editButton.type = "button";
    editButton.textContent = "Editează";
    editButton.onclick = () => editProduct(product);
    actionCell.appendChild(editButton);
    row.appendChild(actionCell);
    body.appendChild(row);
  });

  table.append(head, body);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

function renderImportPreview(preview) {
  const summary = document.getElementById("admin-import-preview-summary");
  summary.textContent =
    `Create: ${preview.summary.create}, Update: ${preview.summary.update}, ` +
    `Archive: ${preview.summary.archive}, Skip: ${preview.summary.skip}, Error: ${preview.summary.error}`;

  renderTable(
    "admin-import-preview-table",
    [
      { key: "row_number", label: "Rând" },
      { key: "action", label: "Acțiune" },
      { key: "sku", label: "SKU" },
      { key: "name", label: "Produs" },
      { key: "category", label: "Categorie" },
      { key: "stock", label: "Stoc" },
      { key: "message", label: "Mesaj" }
    ],
    preview.rows,
    "Preview indisponibil."
  );
}

function showAdminResult(result) {
  document.getElementById("admin-output").innerText = JSON.stringify(result, null, 2);
}

function renderOrders(items) {
  const container = document.getElementById("admin-orders");
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Nu există comenzi.";
    container.appendChild(empty);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "admin-table-wrap";
  const table = document.createElement("table");
  table.className = "admin-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Comandă", "Client", "Status", "Total", "Creată", "Acțiune"].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.appendChild(cell);
  });
  head.appendChild(headRow);

  const body = document.createElement("tbody");
  items.forEach((order) => {
    const row = document.createElement("tr");
    const values = [
      `#${order.order_id}`,
      order.customer_email || (order.user_id ? `User #${order.user_id}` : "Guest"),
      ORDER_STATUS_LABELS[order.status] || order.status,
      `${Number(order.total).toFixed(2)} EUR`,
      order.created_at ? new Date(order.created_at).toLocaleString("ro-RO") : "-"
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });

    const actionCell = document.createElement("td");
    const transitions = ORDER_STATUS_TRANSITIONS[order.status] || [];
    if (transitions.length) {
      const controls = document.createElement("div");
      controls.className = "admin-order-action";
      const select = document.createElement("select");
      select.setAttribute("aria-label", `Status comandă ${order.order_id}`);
      transitions.forEach((status) => {
        const option = document.createElement("option");
        option.value = status;
        option.textContent = ORDER_STATUS_LABELS[status] || status;
        select.appendChild(option);
      });
      const button = document.createElement("button");
      button.className = "secondary";
      button.textContent = "Actualizează";
      button.onclick = () => updateOrderStatus(order.order_id, select.value);
      controls.append(select, button);
      actionCell.appendChild(controls);
    } else {
      actionCell.textContent = "Finalizată";
    }
    row.appendChild(actionCell);
    body.appendChild(row);
  });

  table.append(head, body);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

function renderUsers(items) {
  const container = document.getElementById("admin-users");
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Nu există utilizatori.";
    container.appendChild(empty);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "admin-table-wrap";
  const table = document.createElement("table");
  table.className = "admin-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["ID", "Utilizator", "Email", "Rol", "Creat", "Acțiune"].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.appendChild(cell);
  });
  head.appendChild(headRow);

  const body = document.createElement("tbody");
  items.forEach((user) => {
    const row = document.createElement("tr");
    [
      user.id,
      user.username,
      user.email,
      user.role,
      user.created_at ? new Date(user.created_at).toLocaleString("ro-RO") : "-"
    ].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value ?? "-";
      row.appendChild(cell);
    });

    const actionCell = document.createElement("td");
    if (user.role === "admin") {
      actionCell.textContent = "Protejat";
    } else {
      const button = document.createElement("button");
      button.className = "danger";
      button.textContent = "Șterge";
      button.onclick = () => deleteUser(user.id, user.email);
      actionCell.appendChild(button);
    }
    row.appendChild(actionCell);
    body.appendChild(row);
  });

  table.append(head, body);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

export async function loadAdminData() {
  try {
    const [users, orders, inventory, payments, products] = await Promise.all([
      request(`${endpoints.auth}/users`),
      request(`${endpoints.orders}/orders`),
      request(`${endpoints.inventory}/inventory`),
      request(`${endpoints.payments}/payments`),
      request(`${endpoints.products}/products?include_archived=true`)
    ]);

    document.getElementById("admin-user-count").textContent = users.total;
    document.getElementById("admin-order-count").textContent = orders.total;
    document.getElementById("admin-stock-count").textContent = inventory.total;
    document.getElementById("admin-payment-count").textContent = payments.length;
    document.getElementById("admin-product-count").textContent = products.items.length;

    renderProducts(products.items);

    renderUsers(users.items);
    renderOrders(orders.items);
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

export async function updateOrderStatus(orderId, status) {
  try {
    const result = await request(`${endpoints.orders}/orders/${orderId}/status`, {
      method: "PUT",
      body: JSON.stringify({ status })
    });
    showAdminResult(result);
    await loadAdminData();
    toast(`Comanda #${orderId} a fost actualizată.`);
  } catch (error) {
    toast(`Statusul comenzii nu a fost actualizat: ${error.message}`);
  }
}

export async function deleteUser(userId, email) {
  if (!window.confirm(`Ștergi definitiv utilizatorul ${email}?`)) {
    return;
  }

  try {
    const result = await request(`${endpoints.auth}/users/${userId}`, {
      method: "DELETE"
    });
    showAdminResult(result);
    await loadAdminData();
    toast("Utilizator șters.");
  } catch (error) {
    toast(`Utilizatorul nu a fost șters: ${error.message}`);
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
    const payload = productPayload();
    validateProductPayload(payload);
    const result = await request(`${endpoints.products}/products`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
    showAdminResult(result);
    await reloadProducts();
    clearProductForm();
    await loadAdminData();
    toast("Produs adăugat.");
  } catch (error) {
    toast(`Produsul nu a fost creat: ${error.message}`);
  }
}

export async function updateProduct() {
  try {
    const productId = Number(document.getElementById("admin-product-id").value);
    if (!productId) {
      throw new Error("Selectează un produs din tabel");
    }
    const payload = productPayload();
    validateProductPayload(payload);
    const result = await request(`${endpoints.products}/products/${productId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
    showAdminResult(result);
    await reloadProducts();
    clearProductForm();
    await loadAdminData();
    toast("Produs actualizat. Noul preț este vizibil în catalog.");
  } catch (error) {
    toast(`Produsul nu a fost actualizat: ${error.message}`);
  }
}

export async function deleteProduct() {
  try {
    const productId = Number(document.getElementById("admin-product-id").value);
    if (!productId) {
      throw new Error("Selectează un produs din tabel");
    }
    const productName = document.getElementById("admin-product-name").value.trim();
    if (!window.confirm(`Ștergi definitiv produsul „${productName}”?`)) {
      return;
    }
    const result = await request(`${endpoints.products}/products/${productId}`, {
      method: "DELETE"
    });
    showAdminResult(result);
    await reloadProducts();
    clearProductForm();
    await loadAdminData();
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

export function downloadImportTemplate() {
  window.location.href = `${endpoints.products}/products/import/template`;
}

export async function previewProductImport() {
  try {
    const file = selectedImportFile();
    if (!file) {
      throw new Error("Selectează un fișier Excel .xlsx");
    }
    const formData = new FormData();
    formData.append("file", file);
    const result = await request(`${endpoints.products}/products/import/preview`, {
      method: "POST",
      body: formData
    });
    renderImportPreview(result);
    showAdminResult(result);
    toast("Preview generat.");
  } catch (error) {
    toast(`Preview-ul importului a eșuat: ${error.message}`);
  }
}

export async function applyProductImport() {
  try {
    const file = selectedImportFile();
    if (!file) {
      throw new Error("Selectează un fișier Excel .xlsx");
    }
    const formData = new FormData();
    formData.append("file", file);
    const result = await request(`${endpoints.products}/products/import/apply`, {
      method: "POST",
      body: formData
    });
    renderImportPreview({
      summary: {
        create: result.summary.created,
        update: result.summary.updated,
        archive: result.summary.archived,
        skip: 0,
        error: 0
      },
      rows: result.rows
    });
    showAdminResult(result);
    await reloadProducts();
    await loadAdminData();
    toast("Importul din Excel a fost aplicat.");
  } catch (error) {
    toast(`Importul nu a fost aplicat: ${error.message}`);
  }
}
