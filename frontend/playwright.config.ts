import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, ...devices["Desktop Chrome"] },
  // The production build, served with the snapshot API (snapshot-api.ts) and the SPA fallback, like the host.
  webServer: [
    {
      command: `npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
      url: `http://127.0.0.1:${PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    // The original dashboard (web/) on the same snapshot, for the parity test (e2e/parity.spec.ts).
    {
      command: "node e2e/serve-old.mjs 4180",
      url: "http://127.0.0.1:4180",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
