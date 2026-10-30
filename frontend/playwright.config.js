import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The suite drives the deployed arrangement: one origin, the built React app served by the API
// (see Dockerfile), a real database, real sessions and CSRF.
const PORT = 8101;
const STUB_PORT = 8111;
const python = process.env.E2E_PYTHON ?? "python";

// E2E_REAL=1 runs the same suite against the live Groq API; that is how the committed
// screenshots are produced. Without it the provider - and only the provider - is replaced by
// backend/scripts/stub_groq.py, so the suite runs on every pull request without a secret.
const real = process.env.E2E_REAL === "1";
const stubbedProvider = {
  GROQ_API_KEY: "stub-key",
  GROQ_BASE_URL: `http://127.0.0.1:${STUB_PORT}`,
  GROQ_API_BASE: `http://127.0.0.1:${STUB_PORT}`,
};

// Every run starts from an empty database. This file is re-evaluated inside each worker, by
// which time the API holds the database open; only the first evaluation, before the server is
// started, can clear it - and that is the only point at which clearing it is correct.
const db = join(tmpdir(), "aivoa-e2e.db");
try {
  rmSync(db, { force: true });
} catch {
  // Already owned by the server this run started.
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    ...(real
      ? []
      : [{ command: `${python} scripts/stub_groq.py ${STUB_PORT}`, cwd: "../backend", port: STUB_PORT }]),
    {
      command: `${python} -m uvicorn app.main:app --port ${PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${PORT}/api/health`,
      env: {
        ...process.env,
        DATABASE_URL: `sqlite:///${db.replaceAll("\\", "/")}`,
        SESSION_SECRET: "end-to-end-test",
        ...(real ? {} : stubbedProvider),
      },
    },
  ],
});
