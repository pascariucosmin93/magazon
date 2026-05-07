import { endpoints } from "../shared/constants.js";
import { request } from "../shared/http.js";
import { toast } from "../shared/ui.js";
import { state } from "./state.js";

let reloadProducts = null;

export function configureAdmin({ onReloadProducts }) {
  reloadProducts = onReloadProducts;
}

export async function createCategory() {
  try {
    const result = await request(`${endpoints.products}/categories`, {
      method: "POST",
      headers: { Authorization: `Bearer ${state.token}` },
      body: JSON.stringify({
        name: document.getElementById("category-name").value,
        description: document.getElementById("category-description").value
      })
    });
    document.getElementById("admin-output").innerText = JSON.stringify(result, null, 2);
    await reloadProducts();
    toast("Categorie adăugată.");
  } catch (error) {
    toast(`Categoria nu a fost creată: ${error.message}`);
  }
}

export async function createProduct() {
  try {
    const categoryValue = document.getElementById("admin-product-category-id").value;
    const result = await request(`${endpoints.products}/products`, {
      method: "POST",
      headers: { Authorization: `Bearer ${state.token}` },
      body: JSON.stringify({
        name: document.getElementById("admin-product-name").value,
        description: document.getElementById("admin-product-description").value,
        price: Number(document.getElementById("admin-product-price").value),
        category_id: categoryValue ? Number(categoryValue) : null
      })
    });
    document.getElementById("admin-output").innerText = JSON.stringify(result, null, 2);
    await reloadProducts();
    toast("Produs adăugat.");
  } catch (error) {
    toast(`Produsul nu a fost creat: ${error.message}`);
  }
}

export async function deleteProduct() {
  try {
    const productId = Number(prompt("ID produs de șters"));
    if (!productId) {
      return;
    }
    const result = await request(`${endpoints.products}/products/${productId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${state.token}` }
    });
    document.getElementById("admin-output").innerText = JSON.stringify(result, null, 2);
    await reloadProducts();
    toast("Produs șters.");
  } catch (error) {
    toast(`Produsul nu a fost șters: ${error.message}`);
  }
}
