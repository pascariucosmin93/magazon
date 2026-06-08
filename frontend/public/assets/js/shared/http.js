function errorMessage(value) {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === "object") {
          const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
          return field ? `${field}: ${item.msg || JSON.stringify(item)}` : item.msg || JSON.stringify(item);
        }
        return String(item);
      })
      .join("; ");
  }
  if (value && typeof value === "object") {
    return value.message || value.msg || JSON.stringify(value);
  }
  return String(value || "");
}

export async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });

  if (!response.ok) {
    const raw = await response.text();
    let message = raw;
    try {
      const parsed = JSON.parse(raw);
      message = errorMessage(parsed.detail || parsed.message || raw);
    } catch (_error) {
      message = raw;
    }
    throw new Error(message || `HTTP ${response.status}`);
  }

  return response.json();
}
