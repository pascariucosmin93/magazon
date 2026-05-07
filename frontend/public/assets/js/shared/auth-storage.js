import { AUTH_STORAGE_KEY } from "./constants.js";

export function saveAuthSession(payload) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload));
}

export function clearAuthSession() {
  localStorage.removeItem(AUTH_STORAGE_KEY);
}

export function loadAuthSession() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_error) {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}
