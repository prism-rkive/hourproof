/** Full-page screenshots of each built page at 375 and 1440 px, in both themes, for review. */
import { expect, test } from "@playwright/test";

const SHOTS = "e2e/screenshots";
const PAGES = (process.env.HP_PAGES ?? "proof,note,security,agent,carbon,method").split(",");

for (const name of PAGES) {
  for (const theme of ["dark", "light"] as const) {
    for (const width of [375, 1440]) {
      test(`${name} ${width}px ${theme}`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
        await page.goto(`/${name}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect(page.getByText(/Last run .* passed/).first()).toBeAttached();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300); // lazily loaded charts
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        await page.screenshot({ path: `${SHOTS}/${name}-${width}-${theme}.png`, fullPage: true });
      });
    }
  }
}
