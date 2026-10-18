import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { screen, within } from "@testing-library/react";
import { GLOSSARY } from "@/content/glossary";
import { LIMITS } from "@/content/limits";
import { figuresWithoutScope, renderRoute } from "@/test/render";
import { snapshot } from "@/test/snapshot";

/* eslint-disable @typescript-eslint/no-explicit-any */
/** The original page's "What this does not claim" block, byte for byte (the original page itself was removed). */
const ORIGINAL = resolve(__dirname, "..", "test", "fixtures", "what-this-does-not-claim.html");

afterEach(() => vi.unstubAllGlobals());

describe("Method", () => {
  it("keeps 'What this does not claim' word for word from the original page", () => {
    const html = readFileSync(ORIGINAL, "utf-8");
    const block = html.slice(html.indexOf('id="limits-h"'), html.indexOf("</ul>", html.indexOf('id="limits-h"')));
    const original = [...block.matchAll(/<li>([\s\S]*?)<\/li>/g)].map((m) => m[1]!.trim());
    expect(original).toHaveLength(7);
    expect([...LIMITS]).toEqual(original);
  });

  it("its test period matches the carbon data", () => {
    const [start, end] = (snapshot("carbon") as any).test_period as [string, string];
    const m = (iso: string) =>
      new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
    expect(start.slice(0, 4)).toBe(end.slice(0, 4));
    expect(LIMITS.join(" ")).toContain(`cover ${m(start)}–${m(end)} ${end.slice(0, 4)} only`);
  });

  it("puts the limits first, under an anchor, every bullet verbatim", async () => {
    await renderRoute("/method");
    const section = document.getElementById("limits")!;
    expect(within(section).getByRole("heading", { name: "What this does not claim" })).toBeInTheDocument();
    expect([...section.querySelectorAll("li")].map((li) => li.textContent)).toEqual([...LIMITS]);
    const main = document.getElementById("main")!;
    expect(main.querySelector("section")).toBe(section); // the first section on the page
  });

  it("lists the whole glossary and every contract of the run", async () => {
    await renderRoute("/method");
    for (const g of Object.values(GLOSSARY)) expect(screen.getByText(g.definition)).toBeInTheDocument();
    const contracts = (snapshot("overview") as any).demo.contracts;
    for (const [name, k] of Object.entries<any>(contracts)) {
      expect(screen.getByRole("link", { name: new RegExp(`^${name} contract ${k.address}`) })).toHaveAttribute(
        "href",
        k.url,
      );
    }
  });

  it("labels the period of every figure", async () => {
    await renderRoute("/method");
    expect(figuresWithoutScope(document.getElementById("main")!).unscoped).toEqual([]);
  });
});
