import { expect, test, type Page } from "@playwright/test";

const SHOTS = "e2e/screenshots";
const PAGES = ["/", "/proof", "/security", "/agent", "/carbon", "/note", "/method"];

/** Scroll through the page so charts that load near the viewport are rendered, then return to the top. */
async function scrollThrough(page: Page) {
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 400) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 60));
    }
    window.scrollTo(0, 0);
  });
}

async function ready(page: Page) {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(/Last run .* passed/).first()).toBeAttached();
  await page.evaluate(() => document.fonts.ready);
}

for (const theme of ["dark", "light"] as const) {
  for (const width of [375, 1440]) {
    test(`overview screenshot ${width}px ${theme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
      await page.goto("/");
      await ready(page);
      await scrollThrough(page);
      await expect(page.locator("figure[role=img] svg.recharts-surface").first()).toBeAttached();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.screenshot({ path: `${SHOTS}/overview-${width}-${theme}.png`, fullPage: true });
    });
  }
}

test("judge aids: nav hint, glossary term, mobile menu", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await ready(page);
  await page.getByRole("link", { name: "Security" }).hover();
  await expect(page.getByRole("tooltip")).toContainText("Deliberate attempts to cheat");
  await page.screenshot({ path: `${SHOTS}/hint-nav-dark.png`, clip: { x: 0, y: 0, width: 1440, height: 220 } });
  await page.mouse.move(0, 400);
  const term = page.getByRole("button", { name: /^zero-knowledge proof: what does this mean/ });
  await term.click();
  await expect(page.getByRole("dialog")).toContainText("without revealing the data behind it");
  const box = (await term.boundingBox())!;
  await page.screenshot({
    path: `${SHOTS}/hint-term-dark.png`,
    clip: { x: Math.max(0, box.x - 260), y: Math.max(0, box.y - 200), width: 600, height: 260 },
  });
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${SHOTS}/mobile-menu-hints-dark.png` });
});

test("the week toggle and keyboard navigation of the heatmap", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const week = await (await page.request.get("/api/week")).json();
  await page.goto("/");
  await ready(page);
  const pct = (x: number) => `${(100 * x).toFixed(1)}%`;
  await expect(page.getByText(`Hourly coverage this week: ${pct(week.coverage_naive)}`)).toBeVisible();
  await page.getByRole("radio", { name: "With the agent" }).click();
  await expect(page.getByText(`Hourly coverage this week: ${pct(week.coverage_agent)}`)).toBeVisible();

  const grid = page.getByRole("grid");
  await grid.getByRole("gridcell").first().focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  const focused = page.locator("[role=gridcell]:focus");
  await expect(focused).toHaveAttribute("aria-label", new RegExp(`^${week.hours[25].slice(0, 16)} UTC: `));
  await expect(page.getByText(/MWh covered \(\d+%\)/).first()).toBeVisible();
  // one tab stop for the whole grid
  expect(await grid.locator("[role=gridcell][tabindex='0']").count()).toBe(1);
});

test("no page requests anything from another origin (the chain is never called)", async ({ page, baseURL }) => {
  const foreign: string[] = [];
  page.on("request", (r) => {
    if (!r.url().startsWith(baseURL!) && !r.url().startsWith("data:")) foreign.push(r.url());
  });
  for (const path of PAGES) {
    await page.goto(path);
    await ready(page);
  }
  expect(foreign).toEqual([]);
});

test("'What this does not claim' is one click away from every page and lands on the section", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/agent");
  await ready(page);
  await page.getByRole("contentinfo").getByRole("link", { name: "What this does not claim" }).click();
  await expect(page).toHaveURL(/\/method#limits$/);
  await expect(page.getByRole("heading", { name: "What this does not claim" })).toBeInViewport();
  await page.goto("/method#limits"); // deep link
  await expect(page.getByRole("heading", { name: "What this does not claim" })).toBeInViewport();
});
