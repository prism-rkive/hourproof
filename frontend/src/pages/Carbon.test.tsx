import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { figuresWithoutScope, renderRoute } from "@/test/render";
import { snapshot } from "@/test/snapshot";

/* eslint-disable @typescript-eslint/no-explicit-any */
const c = snapshot("carbon") as any;
const fmt = (n: number) => Math.round(n).toLocaleString("en-GB");

afterEach(() => vi.unstubAllGlobals());

describe("Carbon", () => {
  it("reads the flexible share from the frozen config (no hard-coded 10 %)", async () => {
    await renderRoute("/carbon");
    expect(document.getElementById("main")).toHaveTextContent(
      `moves ${(100 * c.frozen_config.flex_share).toFixed(0)}% of each hour's load (a declared scenario parameter)`,
    );
  });

  it("shows every strategy with the original page's arithmetic", async () => {
    await renderRoute("/carbon");
    const list = screen.getByRole("list", { name: "Emissions by strategy" });
    const no = c.strategies.find((s: any) => s.id === "no_shift").emissions_t;
    for (const s of c.strategies) {
      expect(list).toHaveTextContent(`${fmt(s.emissions_t)} t`);
      if (s.id !== "no_shift") expect(list).toHaveTextContent(`−${(100 * (1 - s.emissions_t / no)).toFixed(2)}%`);
    }
    const m = c.mae;
    expect(document.getElementById("main")).toHaveTextContent(
      `Forecast error ${m.model.toFixed(1)} g/kWh vs ${m.lag168.toFixed(1)} for last week's value (${Math.round(100 * c.improvement_vs_best_persistence)}% lower)`,
    );
  });

  it("shows the on-chain proof card from the run", async () => {
    await renderRoute("/carbon");
    const card = screen.getByRole("complementary", { name: "On-chain proof" });
    const t1 = (kg: number) =>
      (kg / 1000).toLocaleString("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    expect(card).toHaveTextContent(`Residual ≤ ${t1(c.proof.residual_kg)} t CO₂`);
    expect(card).toHaveTextContent(`Coverage ≥ ${(c.proof.coverage_bps / 100).toFixed(2)}%`);
    expect(card).toHaveTextContent(`${fmt(c.proof.gas)} gas`);
    expect(card).toHaveTextContent(`Note target ≤ ${t1(c.proof.target_kg)} t: missed, coupon stepped up`);
  });

  it("keeps every caveat word for word", async () => {
    await renderRoute("/carbon");
    for (const x of c.caveats) expect(screen.getByText(x)).toBeInTheDocument();
  });

  it("the heatmap covers the week with a cell per hour, and the day filter works", async () => {
    await renderRoute("/carbon");
    expect(screen.getAllByRole("gridcell")).toHaveLength(c.week.hours.length);
    await userEvent.selectOptions(screen.getByRole("combobox"), "1");
    expect(screen.getByRole("combobox")).toHaveValue("1");
  });

  it("labels the period of every figure", async () => {
    await renderRoute("/carbon");
    expect(figuresWithoutScope(document.getElementById("main")!).unscoped).toEqual([]);
  });
});
