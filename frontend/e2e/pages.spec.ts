/** Full-page screenshots of each built page at 375 and 1440 px, in both themes, for review. */
import { expect, test, type Page } from "@playwright/test";

const SHOTS = "e2e/screenshots";

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

const PAGES = (process.env.HP_PAGES ?? "overview,proof,note,security,agent,carbon,method").split(",");

for (const name of PAGES) {
  for (const theme of ["dark", "light"] as const) {
    for (const width of [375, 1440]) {
      test(`${name} ${width}px ${theme}`, async ({ page }) => {
        const errors: string[] = []; // hydration mismatches and runtime errors are reported here
        page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
        page.on("pageerror", (e) => errors.push(e.message));
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
        await page.goto(name === "overview" ? "/" : `/${name}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect(page.getByText(/Last run .* passed/).first()).toBeAttached();
        await page.evaluate(() => document.fonts.ready);
        await scrollThrough(page); // charts load when near the viewport
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        await page.screenshot({ path: `${SHOTS}/${name}-${width}-${theme}.png`, fullPage: true });
        expect(errors).toEqual([]);
      });
    }
  }
}
