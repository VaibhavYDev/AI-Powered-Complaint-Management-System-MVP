const BASE = import.meta.env.VITE_API_URL ?? "";

let csrfToken = null;

async function session() {
  if (csrfToken) return csrfToken;
  let identity = await fetch(BASE + "/api/auth/me");
  if (!identity.ok) {
    identity = await fetch(BASE + "/api/auth/anonymous", { method: "POST" });
    if (!identity.ok) throw new Error("Could not start a session.");
  }
  csrfToken = (await identity.json()).csrf_token;
  return csrfToken;
}

async function request(path, options = {}) {
  const headers = { ...options.headers };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = await session();

  const res = await fetch(BASE + path, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return body;
}

export const chat = (message, complaintId) =>
  request("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, complaint_id: complaintId ?? null }),
  });

export function upload(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/upload", { method: "POST", body: form });
}

export const health = () => request("/api/health");
