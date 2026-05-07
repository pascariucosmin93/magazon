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
      message = parsed.detail || parsed.message || raw;
    } catch (_error) {
      message = raw;
    }
    throw new Error(message || `HTTP ${response.status}`);
  }

  return response.json();
}
