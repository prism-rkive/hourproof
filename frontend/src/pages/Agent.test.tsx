import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { figuresWithoutScope, renderRoute } from "@/test/render";
import { snapshot } from "@/test/snapshot";

/* eslint-disable @typescript-eslint/no-explicit-any */
const bt = (snapshot("overview") as any).backtest;
const pct = (x: number) => `${(100 * x).toFixed(1)}%`;

afterEach(() => vi.unstubAllGlobals());

describe("Agent", () => {
  it("shows every strategy's coverage, in the original order, with perfect foresight as a reference", async () => {
    await renderRoute("/agent");
    const list = screen.getByRole("list", { name: "Hourly coverage by strategy" });
    const ids = [
      "naive_fixed_portfolio",
      "bigger_portfolio_same_mwh",
      "agent_shift_only",
      "agent_shift_and_topup",
      "perfect_foresight_bound",
    ];
    const items = [...list.querySelectorAll("li")];
    expect(items).toHaveLength(ids.length);
    items.forEach((li, i) => expect(li).toHaveTextContent(pct(bt.coverage[ids[i]!])));
    expect(items[4]).toHaveTextContent(/(reference)/);
  });

  it("shows the forecast skill and the parameters from the backtest", async () => {
    await renderRoute("/agent");
    const main = document.getElementById("main")!;
    const sk = bt.forecast_skill;
    expect(main).toHaveTextContent(`+${bt.gain_vs_same_mwh_pp.toFixed(1)} points`);
    expect(main).toHaveTextContent(`${Math.round(sk.wind_mae_raw_forecast_mwh).toLocaleString("en-GB")} MWh/h`);
    expect(main).toHaveTextContent(`${Math.round(sk.wind_mae_model_mwh).toLocaleString("en-GB")} MWh/h`);
    expect(main).toHaveTextContent(`${sk.load_mae_model_mwh.toFixed(1)} vs ${sk.load_mae_lag168_mwh.toFixed(1)} MWh/h`);
    expect(main).toHaveTextContent(`Flexible share ${(100 * bt.params.flex_share).toFixed(0)}%`);
    expect(main).toHaveTextContent(bt.note);
    expect(bt.gain_vs_same_mwh_pp).toBeCloseTo(
      100 * (bt.coverage.agent_shift_and_topup - bt.coverage.bigger_portfolio_same_mwh),
      9,
    );
  });

  it("labels the period of every figure", async () => {
    await renderRoute("/agent");
    for (const b of screen.getAllByRole("button", { name: "View as table" })) await userEvent.click(b);
    expect(figuresWithoutScope(document.getElementById("main")!).unscoped).toEqual([]);
  });
});
