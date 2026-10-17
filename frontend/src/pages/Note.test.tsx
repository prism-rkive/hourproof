import { screen } from "@testing-library/react";
import { figuresWithoutScope, renderRoute } from "@/test/render";
import { snapshot } from "@/test/snapshot";

/* eslint-disable @typescript-eslint/no-explicit-any */
const o = snapshot("overview") as any;
const terms = o.demo.note_terms;
const m = o.demo.steps.find((s: any) => s.id === "note").metrics;
const bps = (b: number) => `${(b / 100).toFixed(2)}%`;
const t = (kg: number) => `${(kg / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} t`;

afterEach(() => vi.unstubAllGlobals());

describe("Note", () => {
  it("shows the term sheet from the run's note data", async () => {
    await renderRoute("/note");
    const main = document.getElementById("main")!;
    expect(main).toHaveTextContent(`≤ ${t(m.target_residual_kg)} CO₂`);
    expect(main).toHaveTextContent(`≤ ${t(m.proven_residual_kg)} CO₂`);
    expect(main).toHaveTextContent(bps(terms.base_coupon_bps));
    expect(main).toHaveTextContent(`+${bps(terms.step_up_bps)}`);
    expect(main).toHaveTextContent(bps(m.coupon_bps));
    expect(main).toHaveTextContent(`${m.coupon_paid_tusd} tUSD`);
    expect(main).toHaveTextContent(m.notes_subscribed.toLocaleString("en-GB")); // from the snapshot, not the chain
    expect(main).toHaveTextContent(m.notes_subscribed_source);
    expect(m.kpi_met).toBe(false);
    expect(
      screen.getByRole("heading", { level: 2, name: `Target missed: the coupon stepped up to ${bps(m.coupon_bps)}.` }),
    ).toBeInTheDocument();
  });

  it("coupon = base + step-up when missed, and the target is the rule's mean", () => {
    expect(terms.base_coupon_bps + terms.step_up_bps).toBe(m.coupon_bps);
    const mean = terms.target_basis.reduce((a: number, b: any) => a + b.residual_kg, 0) / terms.target_basis.length;
    expect(Math.floor(mean)).toBe(terms.target_residual_kg);
  });

  it("lists the settlement transactions", async () => {
    await renderRoute("/note");
    const step = o.demo.steps.find((s: any) => s.id === "note");
    const links = [...document.querySelectorAll<HTMLAnchorElement>("a[data-tx]")];
    expect(links.map((a) => a.dataset.tx)).toEqual(step.txs.map((x: any) => x.hash));
  });

  it("labels the period of every figure", async () => {
    await renderRoute("/note");
    expect(figuresWithoutScope(document.getElementById("main")!).unscoped).toEqual([]);
  });
});
