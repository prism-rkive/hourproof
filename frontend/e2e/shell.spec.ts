/**
 * Phase 2 review: screenshots of the shell (top nav, mobile menu, both themes, one empty page), plus the behaviour a
 * screenshot cannot show (deep links, theme without flash, keyboard skip link, menu focus and Escape).
 */
import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.HP_SHOTS ?? "e2e/screenshots";
const THEMES = ["dark", "light"] as const;

async function ready(page: Page) {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(/Last run .* passed/).first()).toBeAttached();
  await page.evaluate(() => document.fonts.ready);
}

for (const theme of THEMES) {
  test.describe(`${theme} theme`, () => {
    test.use({ colorScheme: theme });

    test(`desktop nav and empty page (${theme})`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto("/proof");
      await ready(page);
      expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(theme === "dark");
      await page.screenshot({ path: `${SHOTS}/desktop-proof-${theme}.png` });
      await page.screenshot({ path: `${SHOTS}/desktop-proof-full-${theme}.png`, fullPage: true });
    });

    test(`mobile bar and menu (${theme})`, async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto("/carbon");
      await ready(page);
      await page.screenshot({ path: `${SHOTS}/mobile-carbon-${theme}.png` });
      await page.screenshot({ path: `${SHOTS}/mobile-carbon-full-${theme}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375); // no sideways scroll
      await page.getByRole("button", { name: "Open menu" }).click();
      const menu = page.getByRole("dialog");
      await expect(menu).toBeVisible();
      await page.waitForTimeout(300); // slide-in animation
      await page.screenshot({ path: `${SHOTS}/mobile-menu-${theme}.png` });
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();
    });
  });
}

test("the toggled theme is remembered over the OS preference", async ({ page }) => {
  // (Chromium has no "no preference" scheme any more; the dark fallback is covered by src/lib/theme.test.ts.)
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await ready(page);
  const isDark = () => page.evaluate(() => document.documentElement.classList.contains("dark"));
  expect(await isDark()).toBe(false);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  expect(await isDark()).toBe(true);
  await page.reload();
  await ready(page);
  expect(await isDark()).toBe(true);
});

test("deep links render their page (SPA fallback) and unknown paths show the 404 page", async ({ page }) => {
  for (const [path, heading] of [
    ["/security", "Attack tests"],
    ["/method", "Methodology & limits"],
    ["/nope", "Page not found"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }
});

test("the skip link is the first tab stop and moves focus to the content", async ({ page }) => {
  await page.goto("/agent");
  await ready(page);
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);
});

test("the run-status pill reads the API and links to the proof run", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const overview = await (await page.request.get("/api/overview")).json();
  await page.goto("/");
  await expect(page.getByRole("status").first()).toHaveText(`Last run ${overview.demo.run_id} on Base Sepolia: passed`);
  await page.getByRole("link", { name: `Last run ${overview.demo.run_id} on Base Sepolia: passed` }).click();
  await expect(page).toHaveURL(/\/proof$/);
});
