      const endpoints = {
        auth: "/api/auth",
        products: "/api/products",
        cart: "/api/cart",
        orders: "/api/orders"
      };

      const AUTH_STORAGE_KEY = "magazon.auth";
      const GUEST_CART_STORAGE_KEY = "magazon.guest-cart";
      const LAST_ORDER_STORAGE_KEY = "magazon.last-order";

      const state = {
        userId: null,
        email: null,
        token: null,
        role: null,
        lastOrderId: null,
        lastOrderToken: null,
        products: [],
        categories: [],
        selectedCategoryId: null,
        cart: null
      };

      function saveAuth() {
        if (!state.token || !state.userId) {
          localStorage.removeItem(AUTH_STORAGE_KEY);
          return;
        }
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
          userId: state.userId,
          email: state.email,
          token: state.token,
          role: state.role
        }));
      }

      function loadAuth() {
        try {
          const raw = localStorage.getItem(AUTH_STORAGE_KEY);
          if (!raw) {
            return;
          }
          const parsed = JSON.parse(raw);
          state.userId = parsed.userId || null;
          state.email = parsed.email || null;
          state.token = parsed.token || null;
          state.role = parsed.role || null;
        } catch (_error) {
          localStorage.removeItem(AUTH_STORAGE_KEY);
        }
      }

      function guestCartPayload() {
        try {
          const raw = localStorage.getItem(GUEST_CART_STORAGE_KEY);
          if (!raw) {
            return {};
          }
          return JSON.parse(raw) || {};
        } catch (_error) {
          localStorage.removeItem(GUEST_CART_STORAGE_KEY);
          return {};
        }
      }

      function saveGuestCartPayload(payload) {
        localStorage.setItem(GUEST_CART_STORAGE_KEY, JSON.stringify(payload));
      }

      function clearGuestCartPayload() {
        localStorage.removeItem(GUEST_CART_STORAGE_KEY);
      }

      function saveLastOrderContext() {
        if (!state.lastOrderId) {
          localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
          return;
        }
        localStorage.setItem(LAST_ORDER_STORAGE_KEY, JSON.stringify({
          orderId: state.lastOrderId,
          guestToken: state.lastOrderToken || null
        }));
      }

      function loadLastOrderContext() {
        try {
          const raw = localStorage.getItem(LAST_ORDER_STORAGE_KEY);
          if (!raw) {
            return;
          }
          const parsed = JSON.parse(raw);
          state.lastOrderId = parsed.orderId || null;
          state.lastOrderToken = parsed.guestToken || null;
        } catch (_error) {
          localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
        }
      }

      function formatPrice(value) {
        return `${Number(value || 0).toFixed(2)} EUR`;
      }

      function toast(message) {
        const node = document.getElementById("toast");
        node.innerText = message;
        node.classList.add("visible");
        window.clearTimeout(toast.timer);
        toast.timer = window.setTimeout(() => node.classList.remove("visible"), 2600);
      }

      async function request(url, options = {}) {
        const response = await fetch(url, {
          headers: { "Content-Type": "application/json", ...(options.headers || {}) },
          ...options
        });
        if (!response.ok) {
          const raw = await response.text();
          let message = raw;
          try {
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed.detail === "string") {
              message = parsed.detail;
            } else if (parsed && typeof parsed.message === "string") {
              message = parsed.message;
            }
          } catch (_error) {
            message = raw;
          }
          throw new Error(message || `HTTP ${response.status}`);
        }
        return response.json();
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

      function goToLogin() {
        window.location.href = `/login.html?next=${encodeURIComponent(window.location.pathname || "/")}`;
      }

      function focusAccount() {
        document.getElementById("account").scrollIntoView({ behavior: "smooth", block: "start" });
      }

      function openAccount() {
        if (state.userId) {
          focusAccount();
          return;
        }
        goToLogin();
      }

      function focusCart() {
        document.getElementById("cart").scrollIntoView({ behavior: "smooth", block: "start" });
      }

      function toggleGuestCheckout() {
        const showGuest = !state.userId;
        document.getElementById("guest-checkout-fields").classList.toggle("hidden", !showGuest);
        document.getElementById("guest-note").classList.toggle("hidden", !showGuest);
      }

      function updateUserState() {
        document.getElementById("user-state").innerText = state.email ? state.email : "Vizitator";
        document.getElementById("user-role").innerText = state.role
          ? `Rol: ${state.role}`
          : "Poți cumpăra ca guest sau te poți autentifica pentru un flux mai rapid.";
        document.getElementById("account-button").innerText = state.email ? "Contul meu" : "Login / Cont";
        document.getElementById("logout-button").style.display = state.userId ? "inline-flex" : "none";
        const isAdmin = state.role === "admin";
        document.getElementById("admin-panel").classList.toggle("visible", isAdmin);
        document.getElementById("admin-nav").style.display = isAdmin ? "inline" : "none";
        toggleGuestCheckout();
      }

      function guestCartFromStorage() {
        const payload = guestCartPayload();
        const entries = Object.entries(payload);
        const items = entries.map(([productId, quantity]) => {
          const productIdInt = Number(productId);
          const quantityInt = Number(quantity);
          const product = state.products.find((candidate) => candidate.id === productIdInt);
          const price = product ? Number(product.price) : 0;
          return {
            product_id: productIdInt,
            quantity: quantityInt,
            price,
            name: product ? product.name : `Produs ${productIdInt}`,
            subtotal: price * quantityInt
          };
        }).filter((item) => item.quantity > 0);
        return {
          items,
          total: items.reduce((sum, item) => sum + item.subtotal, 0)
        };
      }

      async function syncGuestCartToServer() {
        if (!state.userId) {
          return;
        }
        const payload = guestCartPayload();
        const entries = Object.entries(payload);
        if (!entries.length) {
          return;
        }
        for (const [productId, quantity] of entries) {
          await request(`${endpoints.cart}/cart/add`, {
            method: "POST",
            headers: { Authorization: `Bearer ${state.token}` },
            body: JSON.stringify({
              user_id: state.userId,
              product_id: Number(productId),
              quantity: Number(quantity)
            })
          });
        }
        clearGuestCartPayload();
      }

      function logout() {
        state.userId = null;
        state.email = null;
        state.token = null;
        state.role = null;
        state.lastOrderId = null;
        state.lastOrderToken = null;
        state.cart = null;
        localStorage.removeItem(AUTH_STORAGE_KEY);
        localStorage.removeItem(LAST_ORDER_STORAGE_KEY);
        document.getElementById("order-output").innerHTML = `<div class="empty">Nu există încă o comandă trimisă din sesiunea curentă.</div>`;
        renderCart(guestCartFromStorage());
        updateUserState();
        toast("Deconectat.");
      }

      function updateCategorySelect() {
        const select = document.getElementById("admin-product-category-id");
        select.innerHTML = `<option value="">Fără categorie</option>`;
        state.categories.forEach((category) => {
          const option = document.createElement("option");
          option.value = category.id;
          option.innerText = `${category.id} - ${category.name}`;
          select.appendChild(option);
        });
      }

      function renderCategories() {
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

      function selectCategory(categoryId) {
        state.selectedCategoryId = categoryId;
        renderCategories();
        renderProducts();
      }

      function filteredProducts() {
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

      function renderFeaturedProducts() {
        const root = document.getElementById("featured-products");
        if (!root) {
          return;
        }
        const items = [...state.products]
          .sort((a, b) => a.price - b.price)
          .slice(0, 4);
        root.innerHTML = "";
        if (!items.length) {
          root.innerHTML = `<div class="panel" style="padding:18px;"><div class="empty">Produsele recomandate vor apărea după încărcarea catalogului.</div></div>`;
          return;
        }
        items.forEach((product) => {
          const node = document.createElement("article");
          node.className = "panel product-card featured-product";
          node.innerHTML = productCardMarkup(product);
          node.querySelector("button").onclick = () => addToCart(product.id);
          root.appendChild(node);
        });
      }

      function renderProducts() {
        const root = document.getElementById("products");
        const items = filteredProducts();
        document.getElementById("catalog-status").innerText = `${items.length} produse`;
        root.innerHTML = "";
        if (!items.length) {
          root.innerHTML = `<div class="panel" style="padding:18px;"><div class="empty">Nu am găsit produse pentru filtrul curent.</div></div>`;
          return;
        }
        items.forEach((product) => {
          const node = document.createElement("article");
          node.className = "panel product-card";
          node.innerHTML = productCardMarkup(product);
          node.querySelector("button").onclick = () => addToCart(product.id);
          root.appendChild(node);
        });
      }

      async function loadCategories() {
        const result = await request(`${endpoints.products}/categories`);
        state.categories = result.items || [];
        updateCategorySelect();
      }

      async function loadProducts() {
        try {
          await loadCategories();
          const result = await request(`${endpoints.products}/products`);
          state.products = result.items || [];
          renderCategories();
          renderFeaturedProducts();
          renderProducts();
          renderCart(state.userId ? (state.cart || { items: [], total: 0 }) : guestCartFromStorage());
        } catch (error) {
          toast(`Nu pot încărca produsele: ${error.message}`);
          document.getElementById("catalog-status").innerText = "Eroare";
        }
      }

      async function resolveRole(token, fallbackRole = null) {
        if (fallbackRole) {
          return fallbackRole;
        }
        if (!token) {
          return null;
        }
        try {
          const session = await request(`${endpoints.auth}/validate/${token}`);
          return session.role || fallbackRole || "customer";
        } catch (_error) {
          return fallbackRole || "customer";
        }
      }

      async function addToCart(productId) {
        if (!state.userId) {
          const payload = guestCartPayload();
          payload[productId] = Number(payload[productId] || 0) + 1;
          saveGuestCartPayload(payload);
          renderCart(guestCartFromStorage());
          toast("Produs adăugat în coșul de guest.");
          return;
        }
        await request(`${endpoints.cart}/cart/add`, {
          method: "POST",
          headers: { Authorization: `Bearer ${state.token}` },
          body: JSON.stringify({ user_id: state.userId, product_id: productId, quantity: 1 })
        });
        await loadCart();
        toast("Produs adăugat în coș.");
      }

      async function loadCart() {
        if (!state.userId) {
          const guestCart = guestCartFromStorage();
          renderCart(guestCart);
          return guestCart;
        }
        const result = await request(`${endpoints.cart}/cart/${state.userId}`, {
          headers: { Authorization: `Bearer ${state.token}` }
        });
        state.cart = result;
        renderCart(result);
        return result;
      }

      function renderCart(cart) {
        const root = document.getElementById("cart-output");
        const count = (cart.items || []).reduce((sum, item) => sum + item.quantity, 0);
        document.getElementById("cart-count").innerText = count;
        if (!cart.items || !cart.items.length) {
          root.innerHTML = `<div class="empty">Coșul este gol.</div>`;
          return;
        }
        const items = cart.items.map((item) => `
          <div class="line-item">
            <div>
              <strong>${item.name}</strong>
              <span>${item.quantity} x ${formatPrice(item.price)}</span>
              <div class="inline-actions">
                <button class="secondary" onclick="changeCartQuantity(${item.product_id}, ${item.quantity - 1})">-</button>
                <button class="secondary" onclick="changeCartQuantity(${item.product_id}, ${item.quantity + 1})">+</button>
                <button class="secondary" onclick="removeFromCart(${item.product_id})">Șterge</button>
              </div>
            </div>
            <strong>${formatPrice(item.subtotal)}</strong>
          </div>
        `).join("");
        root.innerHTML = `
          <div class="cart-items">${items}</div>
          <div class="summary-row">
            <span>Total</span>
            <span class="cart-total">${formatPrice(cart.total)}</span>
          </div>
        `;
      }

      async function placeOrder() {
        try {
          const cart = await loadCart();
          if (!cart.items.length) {
            toast("Coșul este gol.");
            return;
          }
          document.getElementById("catalog-status").innerText = "Trimitem comanda...";
          const items = cart.items.map((item) => ({
            product_id: item.product_id,
            quantity: item.quantity
          }));
          const body = { items };
          const requestOptions = {
            method: "POST",
            body: JSON.stringify(body)
          };
          if (state.userId) {
            requestOptions.headers = { Authorization: `Bearer ${state.token}` };
          } else {
            const customerName = document.getElementById("guest-name").value.trim();
            const customerEmail = document.getElementById("guest-email").value.trim();
            const shippingAddress = document.getElementById("guest-address").value.trim();
            if (!customerName || !customerEmail || !shippingAddress) {
              toast("Completează nume, email și adresă pentru comanda ca guest.");
              return;
            }
            body.customer_name = customerName;
            body.customer_email = customerEmail;
            body.shipping_address = shippingAddress;
            requestOptions.body = JSON.stringify(body);
          }
          const result = await request(`${endpoints.orders}/orders`, requestOptions);
          state.lastOrderId = result.order_id;
          state.lastOrderToken = result.guest_token || null;
          saveLastOrderContext();
          renderOrder(result);
          await clearCart(true);
          if (!state.userId) {
            document.getElementById("guest-name").value = "";
            document.getElementById("guest-email").value = "";
            document.getElementById("guest-address").value = "";
          }
          toast(`Comanda #${result.order_id} a fost plasată.`);
          window.setTimeout(() => {
            loadOrder().catch(() => {});
          }, 1500);
        } catch (error) {
          document.getElementById("catalog-status").innerText = "Eroare la comandă";
          toast(`Comanda nu a fost trimisă: ${error.message}`);
        }
      }

      async function changeCartQuantity(productId, quantity) {
        if (!state.userId) {
          const payload = guestCartPayload();
          if (quantity < 1) {
            delete payload[productId];
          } else {
            payload[productId] = quantity;
          }
          saveGuestCartPayload(payload);
          renderCart(guestCartFromStorage());
          return;
        }
        await request(`${endpoints.cart}/cart/replace`, {
          method: "POST",
          headers: { Authorization: `Bearer ${state.token}` },
          body: JSON.stringify({
            user_id: state.userId,
            product_id: productId,
            quantity
          })
        });
        await loadCart();
      }

      async function removeFromCart(productId) {
        if (!state.userId) {
          const payload = guestCartPayload();
          delete payload[productId];
          saveGuestCartPayload(payload);
          renderCart(guestCartFromStorage());
          toast("Produs scos din coș.");
          return;
        }
        await request(`${endpoints.cart}/cart/${state.userId}/items/${productId}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${state.token}` }
        });
        await loadCart();
        toast("Produs scos din coș.");
      }

      async function clearCart(silent = false) {
        if (!state.userId) {
          clearGuestCartPayload();
          renderCart(guestCartFromStorage());
          if (!silent) {
            toast("Coș golit.");
          }
          return;
        }
        await request(`${endpoints.cart}/cart/${state.userId}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${state.token}` }
        });
        await loadCart();
        if (!silent) {
          toast("Coș golit.");
        }
      }

      async function loadOrder() {
        if (!state.lastOrderId) {
          toast("Nu există o comandă recentă în sesiune.");
          return;
        }
        const url = !state.userId && state.lastOrderToken
          ? `${endpoints.orders}/orders/${state.lastOrderId}?guest_token=${encodeURIComponent(state.lastOrderToken)}`
          : `${endpoints.orders}/orders/${state.lastOrderId}`;
        const options = state.userId
          ? { headers: { Authorization: `Bearer ${state.token}` } }
          : {};
        const result = await request(url, options);
        renderOrder(result);
        if (result.status === "paid") {
          document.getElementById("catalog-status").innerText = "Plata finalizată";
        } else if (result.status === "inventory_failed") {
          document.getElementById("catalog-status").innerText = "Stoc insuficient";
        } else if (result.status === "payment_failed") {
          document.getElementById("catalog-status").innerText = "Plata eșuată";
        } else {
          document.getElementById("catalog-status").innerText = "Comandă în procesare";
        }
      }

      function renderOrder(order) {
        const root = document.getElementById("order-output");
        const items = (order.items || []).map((item) => {
          const product = state.products.find((candidate) => candidate.id === item.product_id);
          const name = product ? product.name : `Produs ${item.product_id}`;
          return `
            <div class="line-item">
              <div>
                <strong>${name}</strong>
                <span>${item.quantity} x ${formatPrice(item.price)}</span>
              </div>
              <strong>${formatPrice(item.quantity * item.price)}</strong>
            </div>
          `;
        }).join("");
        root.innerHTML = `
          <strong>Comanda #${order.order_id}</strong>
          <div class="muted" style="margin-top:4px;">Status: ${order.status}</div>
          <div class="order-items">${items || `<div class="empty">Nu există linii de comandă.</div>`}</div>
          <div class="summary-row">
            <span>Total</span>
            <span>${formatPrice(order.total)}</span>
          </div>
        `;
      }

      async function createCategory() {
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
          await loadProducts();
          toast("Categorie adăugată.");
        } catch (error) {
          toast(`Categoria nu a fost creată: ${error.message}`);
        }
      }

      async function createProduct() {
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
          await loadProducts();
          toast("Produs adăugat.");
        } catch (error) {
          toast(`Produsul nu a fost creat: ${error.message}`);
        }
      }

      async function deleteProduct() {
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
          await loadProducts();
          toast("Produs șters.");
        } catch (error) {
          toast(`Produsul nu a fost șters: ${error.message}`);
        }
      }

      async function bootstrap() {
        loadAuth();
        loadLastOrderContext();
        updateUserState();
        await loadProducts();
        if (state.userId) {
          try {
            state.role = await resolveRole(state.token, state.role);
            saveAuth();
            updateUserState();
            await syncGuestCartToServer();
            await loadCart();
          } catch (_error) {
            logout();
          }
        } else {
          renderCart(guestCartFromStorage());
        }
      }

      bootstrap();
