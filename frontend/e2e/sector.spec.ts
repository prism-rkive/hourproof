/**
 * The buyer's sector name: an inline part of its sentence at every width (a long label must wrap with the text, not
 * break out of it), and Energinet's Danish name one key press away.
 */
import { expect, test, type Page } from "@playwright/test";

const LABEL = "Danish telecommunications and IT services sector";
const DANISH = "Telekommunikation &It - og informationstjenester";

async function open(page: Page, path: string, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(path);
  await expect(page.locator("html[data-hydrated]")).toBeAttached();
}

for (const width of [375, 1440]) {
  test(`at ${width}px the sector name flows with the Overview's sentence`, async ({ page }) => {
    await open(page, "/", width);
    const name = page.getByRole("button", { name: new RegExp(`^${LABEL}`) });
    expect(await name.evaluate((el) => getComputedStyle(el).display)).toBe("inline");
    // "The" and the start of the label sit on the same line
    const [the, label] = await name.evaluate((el) => {
      const r = document.createRange();
      r.selectNodeContents(el.previousSibling!);
      return [r.getClientRects()[0]!.top, el.getClientRects()[0]!.top];
    });
    expect(Math.abs(the - label)).toBeLessThan(4);
  });
}

test("the Danish name opens from the keyboard, on the Overview and the Method page", async ({ page }) => {
  for (const path of ["/", "/method"]) {
    await open(page, path, 1440);
    const name = page.getByRole("button", { name: new RegExp(`^${LABEL}`) });
    await name.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toContainText(DANISH);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
});
