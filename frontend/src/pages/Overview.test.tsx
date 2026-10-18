import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { snapshot } from "@/test/snapshot";
import { figuresWithoutScope, renderRoute } from "@/test/render";

/* eslint-disable @typescript-eslint/no-explicit-any */
const o = snapshot("overview") as any;
const week = snapshot("week") as any;
const bps = (b: number) => `${(b / 100).toFixed(2)}%`;
const pct = (x: number) => `${(100 * x).toFixed(1)}%`;

afterEach(() => vi.unstubAllGlobals());

describe("Overview", () => {
  it("labels the period of every displayed figure, in both views of the week", { timeout: 20000 }, async () => {
    await renderRoute("/");
    const main = document.getElementById("main")!;
    for (const b of screen.getAllByRole("button", { name: "View as table" })) await userEvent.click(b); // tables too
    let r = figuresWithoutScope(main);
    expect(r.figures.length).toBeGreaterThan(20);
    expect(r.unscoped).toEqual([]);
    await userEvent.click(screen.getByRole("radio", { name: "With the agent" }));
    r = figuresWithoutScope(main);
    expect(r.unscoped).toEqual([]);
  });

  it("uses only the two scopes: full year, and the run's week", async () => {
    await renderRoute("/");
    const scopes = new Set([...document.querySelectorAll<HTMLElement>("[data-scope]")].map((e) => e.dataset.scope));
    expect(scopes).toEqual(new Set(["Full year", "Week of 10–16 Nov 2025"]));
    expect(o.demo.window.window_start_utc.slice(0, 10)).toBe("2025-11-10"); // the label comes from this
  });

  it("leads the week with the run's figures; the heatmap's are only in its caption", async () => {
    await renderRoute("/");
    const card = screen.getByRole("radiogroup", { name: "Strategy" }).closest("section")!;
    const title = within(card).getByRole("heading", { level: 3 });
    expect(title).toHaveTextContent(bps(o.demo.summary.coverage_naive_bps));
    expect(title).not.toHaveTextContent(pct(week.coverage_naive));
    expect(card).toHaveTextContent(`Hourly coverage this week: ${pct(week.coverage_naive)}`);
    expect(card).toHaveTextContent("fractional MWh");

    await userEvent.click(screen.getByRole("radio", { name: "With the agent" }));
    expect(title).toHaveTextContent(bps(o.demo.summary.coverage_agent_private_bps));
    expect(title).not.toHaveTextContent(pct(week.coverage_agent));
    expect(card).toHaveTextContent(`Hourly coverage this week: ${pct(week.coverage_agent)}`);

    // the fractional figures appear nowhere outside that caption and the table view
    const outside = document.getElementById("main")!.cloneNode(true) as HTMLElement;
    outside.querySelector("[data-scope] [role=radiogroup]")?.closest("section")?.remove();
    expect(outside.textContent).not.toContain(pct(week.coverage_naive));
    expect(outside.textContent).not.toContain(pct(week.coverage_agent));
  });
});
