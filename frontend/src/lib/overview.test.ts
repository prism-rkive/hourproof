/**
 * Every figure the Overview shows, checked against the committed snapshot with independent arithmetic (the rules of
 * the original web/app.js, now in git history), so a presentation change can never change a number.
 */
import { snapshot } from "@/test/snapshot";
import { Overview, Week, type WeekData } from "./schemas";
import { hero, runFigures, weekView } from "./selectors";

/* eslint-disable @typescript-eslint/no-explicit-any */
const raw = snapshot("overview") as any;
const rawWeek = snapshot("week") as any;
const o = Overview.parse(raw);
const week = Week.parse(rawWeek) as WeekData;
const metrics = (id: string) => raw.demo.steps.find((s: any) => s.id === id).metrics;

describe("hero", () => {
  it("reads the annual and hourly match from the data", () => {
    const h = hero(o)!;
    expect(raw.annual_match).toBe(1);
    expect(h.annual).toBe("100% clean over the year.");
    expect(h.hourly).toBe(`${(100 * raw.dataset.hourly_match_of_100pct_annual_wind).toFixed(1)}% hour by hour.`);
    expect(h.lede).toContain(`Denmark's ${raw.dataset.buyer_label} sector, as one buyer, buys exactly its yearly`);
    expect(h.lede).toContain(`(${raw.dataset.year})`);
  });

  it("does not claim 'exactly' if the annual match were not 100 %", () => {
    expect(hero({ ...o, annual_match: 0.95 })!.lede).toContain("buys 95% of its yearly consumption");
  });
});

describe("run figures", () => {
  it("are the run's own metrics", () => {
    const f = runFigures(o.demo);
    expect(f.provenBps).toBe(metrics("prove").proven_bps);
    expect(f.truePrivateBps).toBe(metrics("prove").true_coverage_private_bps);
    expect(f.provenResidualKg).toBe(metrics("prove_emissions").proven_residual_kg);
    expect(f.targetResidualKg).toBe(metrics("note").target_residual_kg);
    expect(f.kpiMet).toBe(metrics("note").kpi_met);
    expect(f.couponBps).toBe(metrics("note").coupon_bps);
    expect(f.couponPaid).toBe(metrics("note").coupon_paid_tusd);
    expect(f.notes).toBe(metrics("note").notes_subscribed); // from the snapshot, never from the chain
  });

  it("agree with the run summary", () => {
    const f = runFigures(o.demo);
    expect(f.provenBps).toBe(raw.demo.summary.proven_bps);
    expect(f.truePrivateBps).toBe(raw.demo.summary.coverage_agent_private_bps);
    expect(f.provenResidualKg).toBe(raw.demo.summary.proven_residual_kg);
    expect(f.targetResidualKg).toBe(raw.demo.summary.residual_target_kg);
  });
});

describe("week", () => {
  for (const mode of ["naive", "agent"] as const) {
    it(`${mode}: 168 hours, the old page's arithmetic`, () => {
      const v = weekView(week, mode);
      expect(v.cells).toHaveLength(168);
      const load = mode === "agent" ? rawWeek.private_agent_load_mwh : rawWeek.private_naive_load_mwh;
      v.cells.forEach((c, i) => {
        const cert = rawWeek.base_mwh[i] + (mode === "agent" ? rawWeek.topup_mwh[i] : 0);
        expect(c.load).toBe(load[i]);
        expect(c.cert).toBeCloseTo(cert, 9);
        expect(c.share).toBeCloseTo(Math.min(cert / load[i], 1), 12);
      });
      expect(v.coverage).toBe(mode === "agent" ? rawWeek.coverage_agent : rawWeek.coverage_naive);
      expect(v.caption).toContain(rawWeek.window_start_utc.slice(0, 10));
      expect(v.caption).toContain(rawWeek.source);
    });
  }
});
