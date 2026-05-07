      const AUTH_STORAGE_KEY = "magazon.auth";
      const nextUrl = new URLSearchParams(window.location.search).get("next") || "/";

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
            message = parsed.detail || parsed.message || raw;
          } catch (_error) {
            message = raw;
          }
          throw new Error(message || `HTTP ${response.status}`);
        }
        return response.json();
      }

      function saveAuth(payload) {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload));
      }

      function showTab(name) {
        const loginVisible = name === "login";
        document.getElementById("login-form").classList.toggle("hidden", !loginVisible);
        document.getElementById("register-form").classList.toggle("hidden", loginVisible);
        document.getElementById("login-tab").classList.toggle("active", loginVisible);
        document.getElementById("register-tab").classList.toggle("active", !loginVisible);
      }

      async function login() {
        try {
          const result = await request("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({
              email: document.getElementById("login-email").value.trim(),
              password: document.getElementById("login-password").value
            })
          });
          saveAuth({
            userId: result.user_id,
            email: result.email,
            token: result.token,
            role: result.role || "customer"
          });
          toast("Autentificare reușită.");
          window.setTimeout(() => {
            window.location.href = nextUrl;
          }, 500);
        } catch (error) {
          toast(`Login eșuat: ${error.message}`);
        }
      }

      async function register() {
        try {
          const username = document.getElementById("register-username").value.trim();
          const email = document.getElementById("register-email").value.trim();
          const password = document.getElementById("register-password").value;
          const address = document.getElementById("register-address").value.trim();

          if (!username || !email || !password || !address) {
            toast("Completează user, email, parolă și adresă.");
            return;
          }

          await request("/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ username, email, password, address })
          });
          document.getElementById("login-email").value = email;
          document.getElementById("login-password").value = password;
          showTab("login");
          toast("Cont creat. Te autentific imediat.");
          await login();
        } catch (error) {
          toast(`Crearea contului a eșuat: ${error.message}`);
        }
      }
