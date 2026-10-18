// The original dashboard (web/), served from the same committed snapshot as the hosted site served it, so the parity
// test can compare figures and links. Removed together with web/.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..", "..");
const API = { "/api/overview": "overview", "/api/week": "week", "/api/carbon": "carbon" };
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css" };
const port = Number(process.argv[2] ?? 4180);

createServer(async (req, res) => {
  const path = (req.url ?? "/").split("?")[0];
  try {
    if (API[path]) {
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(await readFile(resolve(ROOT, "deploy", "snapshot", `${API[path]}.json`)));
    }
    const file = path === "/" ? "index.html" : path.startsWith("/static/") ? path.slice("/static/".length) : null;
    if (!file || file.includes("..")) throw new Error("not found");
    res.writeHead(200, { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream" });
    res.end(await readFile(resolve(ROOT, "web", file)));
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
}).listen(port, "127.0.0.1");
