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
      request(`${endpoints.products}/products`)
    ]);

    document.getElementById("admin-user-count").textContent = users.total;
    document.getElementById("admin-order-count").textContent = orders.total;
    document.getElementById("admin-stock-count").textContent = inventory.total;
    document.getElementById("admin-payment-count").textContent = payments.length;
    document.getElementById("admin-product-count").textContent = products.items.length;

    renderTable(
      "admin-products",
      [
        { key: "id", label: "ID" },
        { key: "sku", label: "SKU" },
        { key: "name", label: "Produs" },
        { key: "category_name", label: "Categorie" },
        { key: "price", label: "Preț", format: (value) => `${Number(value).toFixed(2)} EUR` }
      ],
      products.items,
      "Nu există produse."
    );

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
