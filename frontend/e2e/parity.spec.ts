/**
 * Parity with the original dashboard (web/), both rendering the same committed snapshot:
 *   - every figure the old page shows appears on the new site;
 *   - every transaction link on the old page, and every transaction of the run, is linked on the new site.
 * Skipped once web/ is removed.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const OLD = "http://127.0.0.1:4180";
const ROOT = resolve(import.meta.dirname, "..", "..");
const PAGES = ["/", "/proof", "/security", "/agent", "/carbon", "/note", "/method"];

test.skip(!existsSync(resolve(ROOT, "web", "index.html")), "web/ removed");

/** A figure: a number with its unit, if any ("70.8%", "546.1 t", "114,132,609", "15.6 g/kWh"). */
const FIGURE = /[≥≤−+]?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|t\b|MWh\/h|MWh|g\/kWh|tUSD|points))?/g;
const norm = (s: string) => s.replace(/\u00a0/g, " ").replace(/\s+/g, " ");

async function oldPage(page: Page) {
  await page.goto(OLD);
  await expect(page.locator("#steps li").first()).toBeVisible();
  await expect(page.locator("#co2-bars .hbar").first()).toBeVisible();
  // Not figures: the old page's "+N more" truncation of long transaction lists, and its charts' axis ticks.
  await page.locator("main").evaluate((m) => m.querySelectorAll(".txs .muted, svg").forEach((e) => e.remove()));
  const texts = [norm(await page.locator("main").innerText())];
  await page.locator('.toggle button[data-mode="agent"]').click(); // the heatmap's second view
  texts.push(norm(await page.locator("#week-caption").innerText()));
  await page.locator("details").evaluateAll((ds) => ds.forEach((d) => ((d as HTMLDetailsElement).open = true)));
  texts.push(norm(await page.locator("#co2-table").innerText()), norm(await page.locator("#co2-caveats").innerText()));
  const links = await page.locator("#steps a[href]").evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href));
  return { text: texts.join("\n"), links };
}

async function newSite(page: Page) {
  const texts: string[] = [];
  const links = new Set<string>();
  for (const path of PAGES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    for (const b of await page.getByRole("button", { name: /Expand all/ }).all()) await b.click();
    const tables = page.getByRole("button", { name: "View as table" }); // each turns into "Hide table" when opened
    while (await tables.count()) await tables.first().click();
    await page.locator("details").evaluateAll((ds) => ds.forEach((d) => ((d as HTMLDetailsElement).open = true)));
    texts.push(norm(await page.locator("main").innerText()));
    const agent = page.getByRole("radio", { name: "With the agent" });
    if (await agent.count()) {
      await agent.click();
      texts.push(norm(await page.locator("main").innerText()));
    }
    for (const h of await page.locator("a[data-tx]").evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href)))
      links.add(h);
  }
  return { text: texts.join("\n"), links };
}

test("every figure and every transaction link of the original page is on the new site", async ({ browser }) => {
  test.setTimeout(120_000);
  const oldCtx = await browser.newContext();
  const old = await oldPage(await oldCtx.newPage());
  const fresh = await newSite(await (await browser.newContext()).newPage());

  const figures = [...new Set(old.text.match(FIGURE) ?? [])].filter((f) => /\d{2}|%|\./.test(f)); // skip lone digits
  const missing = figures.filter((f) => !fresh.text.includes(f));
  expect(figures.length).toBeGreaterThan(80);
  expect(missing, `figures on the old page that the new site does not show`).toEqual([]);

  expect(old.links.length).toBeGreaterThan(0);
  expect(old.links.filter((h) => !fresh.links.has(h))).toEqual([]);

  const state = JSON.parse(
    readFileSync(resolve(ROOT, "evidence", "base-sepolia-20261017T141639Z", "state.json"), "utf-8"),
  ) as { steps: { txs: { hash: string; url: string }[] }[] };
  const all = state.steps.flatMap((s) => s.txs);
  expect(all).toHaveLength(80);
  expect(all.filter((t) => !fresh.links.has(t.url))).toEqual([]);
  expect(fresh.links.size).toBe(80);
});
