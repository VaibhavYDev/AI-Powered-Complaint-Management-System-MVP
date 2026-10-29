import { beforeEach, describe, expect, it, vi } from "vitest";

function jsonResponse(body, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

async function freshApi() {
  vi.resetModules(); // the module caches the CSRF token for the session
  return import("./api.js");
}

describe("session bootstrap", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("reuses an existing session and sends its CSRF token on writes", async () => {
    const api = await freshApi();
    fetch
      .mockResolvedValueOnce(jsonResponse({ id: 1, csrf_token: "token-abc" }))
      .mockResolvedValueOnce(jsonResponse({ intent: "LOG" }));

    await api.chat("broken tablets", null);

    const [mePath] = fetch.mock.calls[0];
    const [chatPath, chatInit] = fetch.mock.calls[1];
    expect(mePath).toBe("/api/auth/me");
    expect(chatPath).toBe("/api/chat");
    expect(chatInit.headers["X-CSRF-Token"]).toBe("token-abc");
    expect(JSON.parse(chatInit.body)).toEqual({ message: "broken tablets", complaint_id: null });
  });

  it("starts an anonymous workspace when there is no session yet", async () => {
    const api = await freshApi();
    fetch
      .mockResolvedValueOnce(jsonResponse({ detail: "Sign in to continue." }, false, 401))
      .mockResolvedValueOnce(jsonResponse({ id: 2, csrf_token: "token-new" }))
      .mockResolvedValueOnce(jsonResponse({ intent: "LOG" }));

    await api.chat("broken tablets");

    expect(fetch.mock.calls[1]).toEqual(["/api/auth/anonymous", { method: "POST" }]);
    expect(fetch.mock.calls[2][1].headers["X-CSRF-Token"]).toBe("token-new");
  });

  it("does not ask for a token on reads", async () => {
    const api = await freshApi();
    fetch.mockResolvedValueOnce(jsonResponse({ database: "ok" }));

    await api.health();

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("sends the uploaded file as form data with the token", async () => {
    const api = await freshApi();
    fetch
      .mockResolvedValueOnce(jsonResponse({ id: 1, csrf_token: "token-abc" }))
      .mockResolvedValueOnce(jsonResponse({ intent: "EXTRACT" }));

    await api.upload(new File(["%PDF-1.4"], "complaint.pdf", { type: "application/pdf" }));

    const [path, init] = fetch.mock.calls[1];
    expect(path).toBe("/api/upload");
    expect(init.body.get("file").name).toBe("complaint.pdf");
    expect(init.headers["X-CSRF-Token"]).toBe("token-abc");
  });
});

describe("errors", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("surfaces the backend detail", async () => {
    const api = await freshApi();
    fetch.mockResolvedValueOnce(jsonResponse({ detail: "There is no complaint loaded to edit." }, false, 400));

    await expect(api.health()).rejects.toThrow("There is no complaint loaded to edit.");
  });

  it("falls back to the status when there is no detail", async () => {
    const api = await freshApi();
    fetch.mockResolvedValueOnce(jsonResponse({}, false, 502));

    await expect(api.health()).rejects.toThrow("Request failed (502)");
  });

  it("reports a session that cannot be started", async () => {
    const api = await freshApi();
    fetch
      .mockResolvedValueOnce(jsonResponse({}, false, 401))
      .mockResolvedValueOnce(jsonResponse({}, false, 429));

    await expect(api.chat("hi")).rejects.toThrow("Could not start a session.");
  });
});
