import { request } from "../shared/http.js";
import { toast } from "../shared/ui.js";

const nextUrl = new URLSearchParams(window.location.search).get("next") || "/";

function validateRegistration({ username, email, password, address }) {
  if (username.length < 3) {
    return "Userul trebuie să aibă cel puțin 3 caractere.";
  }
  if (username.length > 100) {
    return "Userul poate avea maximum 100 de caractere.";
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return "Introdu o adresă de email validă, de exemplu nume@domeniu.ro.";
  }
  if (password.length < 6) {
    return "Parola trebuie să aibă cel puțin 6 caractere.";
  }
  if (address.length < 5) {
    return "Adresa de livrare trebuie să aibă cel puțin 5 caractere.";
  }
  if (address.length > 255) {
    return "Adresa de livrare poate avea maximum 255 de caractere.";
  }
  return null;
}

export function showTab(name) {
  const loginVisible = name === "login";
  const registerVisible = name === "register";
  const forgotVisible = name === "forgot";
  const states = {
    login: loginVisible,
    register: registerVisible,
    forgot: forgotVisible
  };

  document.getElementById("login-form").classList.toggle("hidden", !loginVisible);
  document.getElementById("register-form").classList.toggle("hidden", !registerVisible);
  document.getElementById("forgot-form").classList.toggle("hidden", !forgotVisible);
  document.getElementById("login-tab").classList.toggle("active", loginVisible);
  document.getElementById("register-tab").classList.toggle("active", registerVisible);
  document.getElementById("forgot-tab").classList.toggle("active", forgotVisible);

  Object.entries(states).forEach(([tabName, isVisible]) => {
    document.getElementById(`${tabName}-tab`).setAttribute("aria-selected", String(isVisible));
  });
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

    const validationError = validateRegistration({ username, email, password, address });
    if (validationError) {
      toast(validationError);
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
