/**
 * Prerender every page into dist/ so the hosted site shows content before any JavaScript runs.
 *   dist/index.html      the Overview          dist/<page>.html   the other pages (served at /<page>)
 *   dist/spa.html        the plain app shell, for any other path (rendered in the browser, e.g. the 404 page)
 * Pages are rendered by the app itself (dist-server/entry-server.js), from the committed snapshot of the verified run
 * (deploy/snapshot), answered at the same /api paths the browser uses. Nothing is fetched from the network.
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SNAPSHOT = resolve(here, "..", "deploy", "snapshot");
const API = {
  "/api/overview": "overview.json",
  "/api/week": "week.json",
  "/api/carbon": "carbon.json",
  "/api/demo/log": "log.json",
};

globalThis.fetch = async (input) => {
  const path = new URL(typeof input === "string" ? input : input.url, "http://prerender.local").pathname;
  const file = API[path];
  if (!file) return new Response(JSON.stringify({ error: `no snapshot for ${path}` }), { status: 404 });
  return new Response(await readFile(resolve(SNAPSHOT, file), "utf-8"), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
};

const { render, PAGES } = await import(pathToFileURL(resolve(here, "dist-server", "entry-server.js")).href);
let template = await readFile(resolve(here, "dist", "index.html"), "utf-8");
const PRELOAD =
  /\s*<!-- every page's shell reads the run status[^>]*-->\s*<link rel="preload" href="\/api\/overview"[^>]*>/;
const escape = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

if (!template.includes('<div id="root"></div>')) throw new Error("dist/index.html has no empty #root to fill");

// Preload the text font, so it is ready before the first paint and text does not reflow when it arrives.
const inter = (await readdir(resolve(here, "dist", "assets"))).find((f) =>
  /^inter-latin-wght-normal-.*\.woff2$/.test(f),
);
if (!inter) throw new Error("the Inter latin font file is missing from dist/assets");
const fontPreload = `<link rel="preload" href="/assets/${inter}" as="font" type="font/woff2" crossorigin="anonymous" />`;
template = template.replace(
  "</title>",
  `</title>
    ${fontPreload}`,
);
await writeFile(resolve(here, "dist", "spa.html"), template);

for (const page of PAGES) {
  const { html, status } = await render(page.path);
  if (status !== 200) throw new Error(`${page.path}: status ${status}`);
  if (!html.includes("<h1")) throw new Error(`${page.path}: no heading rendered`);
  const title = page.path === "/" ? "HourProof" : `${page.title} · HourProof`;
  const out = template
    .replace('<div id="root"></div>', `<div id="root">${html}</div>`)
    .replace(/<title>[^<]*<\/title>/, `<title>${escape(title)}</title>`)
    .replace(/(<meta\s+name="description"\s+content=")[^"]*(")/, `$1${escape(page.description)}$2`)
    .replace(PRELOAD, ""); // the data is in the page already
  const name = page.path === "/" ? "index.html" : `${page.path.slice(1)}.html`;
  await writeFile(resolve(here, "dist", name), out);
  console.log(`prerendered ${page.path.padEnd(10)} -> dist/${name} (${Math.round(out.length / 1024)} KB)`);
}
