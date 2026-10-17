/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import { snapshotApi } from "./snapshot-api";

const liveApi = process.env.HP_API; // e.g. http://127.0.0.1:8000 while `make serve` runs

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(liveApi ? [] : [snapshotApi()])],
  resolve: { alias: { "@": resolve(import.meta.dirname, "src") } },
  server: liveApi ? { proxy: { "/api": liveApi } } : {},
  preview: liveApi ? { proxy: { "/api": liveApi } } : {},
  build: { target: "es2022", sourcemap: true },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
