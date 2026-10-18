import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
/** Test a deployed site instead of the local build, e.g. HP_BASE_URL=https://hourproof-phi.vercel.app */
const external = process.env.HP_BASE_URL?.replace(/\/$/, "");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: external ?? `http://127.0.0.1:${PORT}`, ...devices["Desktop Chrome"] },
  webServer: [
    // The production build, served with the snapshot API (snapshot-api.ts) and the page routing, like the host.
    ...(external
      ? []
      : [
          {
            command: `npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
            url: `http://127.0.0.1:${PORT}`,
            reuseExistingServer: false,
            timeout: 60_000,
          },
        ]),
  ],
});
