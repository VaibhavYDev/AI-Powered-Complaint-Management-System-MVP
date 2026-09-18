const BASE = import.meta.env.VITE_API_URL ?? "";

async function request(path, options) {
  const res = await fetch(BASE + path, options);
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
