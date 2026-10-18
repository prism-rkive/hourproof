/**
 * On every page: the run status is in the accessibility tree once (never a visual copy beside a screen-reader copy,
 * never the top bar's and the menu's at the same time), and every date shown carries its year.
 */
import { expect, test, type Page } from "@playwright/test";

const PAGES = ["/", "/proof", "/security", "/agent", "/carbon", "/note", "/method", "/no-such-page"];
const MONTH = "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)";
/** "13 Nov" not followed by a year, unless it opens a range that ends with one ("6 Oct – 2 Nov 2025"). */
const DATE_WITHOUT_YEAR = new RegExp(`\\b\\d{1,2} ${MONTH}\\b(?! \\d{4})(?! – \\d{1,2} ${MONTH} \\d{4})`, "g");

async function open(page: Page, path: string, width: number, menu: boolean) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(path);
  await expect(page.locator("html[data-hydrated]")).toBeAttached();
  if (menu) {
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  }
}

async function runStatuses(page: Page): Promise<string[]> {
  const tree = await page.locator("body").ariaSnapshot();
  return tree
    .split("\n")
    .filter((l) => /status: "?Last run/.test(l))
    .map((l) => l.trim());
}

// One light test per page and check (not one heavy test per page), so each stays far inside the time limit even on
// a busy machine.
for (const path of PAGES) {
  for (const [width, menu] of [
    [1440, false],
    [768, true],
    [375, true],
  ] as const) {
    test(`${path} at ${width}px${menu ? " with the menu open" : ""}: the run status is in the accessibility tree once`, async ({
      page,
    }) => {
      await open(page, path, width, menu);
      const statuses = await runStatuses(page);
      expect(statuses).toHaveLength(1);
      expect(statuses[0]).toMatch(/^- status: "Last run \S+ on Base Sepolia: passed"$/);
      expect(await page.locator("body").innerText()).not.toMatch(/passedLast run|passed\d{8}T/); // no glued copy
    });
  }

  test(`${path}: every date shown carries its year`, async ({ page }) => {
    await open(page, path, 1440, false);
    // open what holds more dates: tables, every step, the carbon day picker's options
    for (const b of await page.getByRole("button", { name: /Expand all/ }).all()) await b.click();
    const tables = page.getByRole("button", { name: "View as table" });
    while (await tables.count()) await tables.first().click();
    const shown = [await page.locator("main").innerText(), await page.locator("footer").innerText()];
    const options = await page.locator("select option").allInnerTexts();
    const charts = await page.locator(".recharts-cartesian-axis-tick").allInnerTexts(); // axis ticks: weekday + day only
    const missing = [...[...shown, ...options].join("\n").matchAll(DATE_WITHOUT_YEAR)]
      .map((m) => m[0])
      .filter((d) => !charts.some((c) => c.includes(d)));
    expect(missing, "dates shown without their year").toEqual([]);
  });
}

test("the heatmap readout names the date with its year", async ({ page }) => {
  await open(page, "/", 1440, false);
  await page
    .locator("[role=gridcell]")
    .nth(24 * 3 + 13)
    .hover();
  await expect(page.getByText(/Thu 13 Nov 2025, 13:00 UTC/)).toBeVisible();
});
