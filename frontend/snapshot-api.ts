/**
 * Serves the committed snapshot of the verified run (deploy/snapshot/*.json) at the same /api paths the hosted site
 * and the local Python server expose, for `vite` and `vite preview`. The files are read on every request, never
 * copied or edited. To use the live local API instead (`make serve`), start Vite with HP_API=http://127.0.0.1:8000.
 */
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { Connect, Plugin } from "vite";

export const SNAPSHOT_DIR = resolve(import.meta.dirname, "..", "deploy", "snapshot");

/** API path -> snapshot file, the same mapping as the rewrites in vercel.json. */
export const SNAPSHOT_ROUTES: Record<string, string> = {
  "/api/overview": "overview.json",
  "/api/week": "week.json",
  "/api/carbon": "carbon.json",
  "/api/demo/log": "log.json",
};

const handler: Connect.NextHandleFunction = (req, res, next) => {
  const path = (req.url ?? "").split("?")[0] ?? "";
  if (!path.startsWith("/api/")) return next();
  const file = SNAPSHOT_ROUTES[path];
  const send = (status: number, body: string) => {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.end(body);
  };
  if (!file) return send(404, JSON.stringify({ error: `no snapshot for ${path}` }));
  readFile(resolve(SNAPSHOT_DIR, file), "utf-8").then(
    (body) => send(200, body),
    () => send(404, JSON.stringify({ error: `deploy/snapshot/${file} not found` })),
  );
};

export function snapshotApi(): Plugin {
  return {
    name: "hourproof-snapshot-api",
    configureServer(server) {
      server.middlewares.use(handler);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handler);
    },
  };
}
