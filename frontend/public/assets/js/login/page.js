import { request } from "../shared/http.js";
import { toast } from "../shared/ui.js";

const nextUrl = new URLSearchParams(window.location.search).get("next") || "/";

export function showTab(name) {
  const loginVisible = name === "login";
  const registerVisible = name === "register";
  const forgotVisible = name === "forgot";
  document.getElementById("login-form").classList.toggle("hidden", !loginVisible);
  document.getElementById("register-form").classList.toggle("hidden", !registerVisible);
  document.getElementById("forgot-form").classList.toggle("hidden", !forgotVisible);
  document.getElementById("login-tab").classList.toggle("active", loginVisible);
  document.getElementById("register-tab").classList.toggle("active", registerVisible);
  document.getElementById("forgot-tab").classList.toggle("active", forgotVisible);
}

export async function login() {
  try {
    await request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("login-email").value.trim(),
        password: document.getElementById("login-password").value
      })
    });

    toast("Autentificare reușită.");
    window.setTimeout(() => {
      window.location.href = nextUrl;
    }, 500);
  } catch (error) {
    toast(`Login eșuat: ${error.message}`);
  }
}

export async function register() {
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

export async function requestPasswordReset() {
  try {
    await request("/api/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("reset-email").value.trim()
      })
    });
    toast("Dacă emailul există, tokenul de resetare a fost generat.");
  } catch (error) {
    toast(`Reset password eșuat: ${error.message}`);
  }
}

export async function confirmPasswordReset() {
  try {
    await request("/api/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({
        token: document.getElementById("reset-token").value.trim(),
        password: document.getElementById("reset-password").value
      })
    });
    toast("Parola a fost schimbată. Te poți autentifica.");
    showTab("login");
  } catch (error) {
    toast(`Schimbarea parolei a eșuat: ${error.message}`);
  }
}

export function bootstrapLoginPage() {
  Object.assign(window, {
    showTab,
    login,
    register,
    requestPasswordReset,
    confirmPasswordReset
  });
}
