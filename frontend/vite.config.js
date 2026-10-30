import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  // Unit tests only; the e2e/ specs are Playwright's and need a running stack.
  test: { include: ["src/**/*.test.js"] },
});
