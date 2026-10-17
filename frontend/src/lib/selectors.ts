/** Pure functions from API data to what the UI shows. Every displayed figure is derived here, and tested. */
import { int, networkName, pct, pctShort, utcDateTime, weekScope } from "./format";
import type { DemoState, Overview, Step, WeekData } from "./schemas";

export type Tone = "success" | "warning" | "danger" | "neutral";

/* ------------------------------------------------------------------------------------------------ run status */

export type RunStatusView = {
  tone: Tone;
  short: string; // compact pill text
  full: string; // complete sentence (screen readers, tooltip, mobile menu)
  runId?: string;
  network?: string;
  pulse?: boolean;
};

/** Same rules as the original dashboard header (web/app.js): running, else last run passed / failed, else none. */
export function runStatus(o: Overview): RunStatusView {
  const demo = o.demo;
  if (o.running) return { tone: "warning", short: "Run in progress", full: "A run is in progress", pulse: true };
  if (demo?.status === "done")
    return {
      tone: "success",
      short: "Last run passed",
      full: `Last run ${demo.run_id} on ${networkName(demo.network)}: passed`,
      runId: demo.run_id,
      network: networkName(demo.network),
    };
  if (demo?.status === "failed")
    return {
      tone: "danger",
      short: "Last run failed",
      full: `Last run ${demo.run_id} on ${networkName(demo.network)}: failed`,
      runId: demo.run_id,
      network: networkName(demo.network),
    };
  if (demo) return { tone: "neutral", short: `Run ${demo.status}`, full: `Run ${demo.run_id}: ${demo.status}` };
  return { tone: "neutral", short: "No run yet", full: "No run has been recorded yet" };
}

/** Footer line: when and where the last run finished. */
export function lastRunLine(o: Overview): string | null {
  const demo = o.demo;
  if (!demo) return null;
  const when = demo.finished_utc ?? demo.started_utc;
  return `Last run ${when ? utcDateTime(when) : demo.run_id} on ${networkName(demo.network)}`;
}

/* ------------------------------------------------------------------------------------------------ run figures */

export function step(demo: DemoState | null | undefined, id: string): Step | undefined {
  return demo?.steps.find((s) => s.id === id);
}

/** A numeric metric of a step, or undefined if the run did not record it. */
export function metric(demo: DemoState | null | undefined, stepId: string, key: string): number | undefined {
  const v = step(demo, stepId)?.metrics[key];
  return typeof v === "number" ? v : undefined;
}

export type RunFigures = {
  provenBps?: number; // coverage proven on-chain (lower bound)
  naiveBps?: number; // the run's coverage with the fixed portfolio, private (whole-MWh certificates)
  truePrivateBps?: number; // the buyer's true coverage, private
  provenResidualKg?: number; // residual emissions proven on-chain (upper bound)
  targetResidualKg?: number; // the note's KPI target
  kpiMet?: boolean;
  couponBps?: number;
  couponPaid?: number; // tUSD
  notes?: number; // notes subscribed (from the note contract's totalSupply, recorded in the snapshot)
};

export function runFigures(demo: DemoState | null | undefined): RunFigures {
  const note = step(demo, "note")?.metrics ?? {};
  return {
    provenBps: metric(demo, "prove", "proven_bps"),
    naiveBps: typeof demo?.summary?.coverage_naive_bps === "number" ? demo.summary.coverage_naive_bps : undefined,
    truePrivateBps: metric(demo, "prove", "true_coverage_private_bps"),
    provenResidualKg: metric(demo, "prove_emissions", "proven_residual_kg"),
    targetResidualKg: metric(demo, "note", "target_residual_kg"),
    kpiMet: typeof note.kpi_met === "boolean" ? note.kpi_met : undefined,
    couponBps: metric(demo, "note", "coupon_bps"),
    couponPaid: metric(demo, "note", "coupon_paid_tusd"),
    notes: metric(demo, "note", "notes_subscribed"),
  };
}

/** The scope label of the run's week ("Week of 10–16 Nov"), from the run's own window. */
export function runWeekScope(demo: DemoState | null | undefined): string | undefined {
  const start = (demo as { window?: { window_start_utc?: unknown } } | null | undefined)?.window?.window_start_utc;
  return typeof start === "string" ? weekScope(start) : undefined;
}

/* ------------------------------------------------------------------------------------------------ hero */

export type Hero = { annual: string; hourly: string; lede: string } | null;

/** The headline and lede. Wording of the original page; the annual figure now comes from the data too. */
export function hero(o: Overview): Hero {
  const ds = o.dataset;
  if (!ds || o.annual_match == null) return null;
  const hourly = pct(ds.hourly_match_of_100pct_annual_wind);
  const buyer = ds.buyer_label ? `Denmark's ${ds.buyer_label} sector, as one buyer,` : "A buyer";
  const buys =
    o.annual_match === 1
      ? "buys exactly its yearly consumption"
      : `buys ${pctShort(o.annual_match)} of its yearly consumption`;
  return {
    annual: `${pctShort(o.annual_match)} clean over the year.`,
    hourly: `${hourly} hour by hour.`,
    lede:
      `${buyer} ${buys} in Danish wind${ds.year ? ` (${ds.year})` : ""}. Hour by hour, only ${hourly} of its ` +
      "consumption is met by wind produced in that same hour. HourProof makes each hour's certificate count once, " +
      "proves the hourly match without revealing consumption, and lets an AI agent close the gap.",
  };
}

/* ------------------------------------------------------------------------------------------------ week */

export type WeekMode = "naive" | "agent";

export type HourCell = { i: number; hour: string; load: number; cert: number; share: number; label: string };

/** The 7 x 24 heatmap for one strategy: same arithmetic as web/app.js renderWeek. */
export function weekView(week: WeekData, mode: WeekMode) {
  const load = mode === "agent" ? week.private_agent_load_mwh : week.private_naive_load_mwh;
  const cert = week.base_mwh.map((b, i) => b + (mode === "agent" ? (week.topup_mwh[i] ?? 0) : 0));
  const cells: HourCell[] = week.hours.map((hour, i) => {
    const l = load[i] ?? 0;
    const c = cert[i] ?? 0;
    const share = l > 0 ? Math.min(c / l, 1) : 1;
    return {
      i,
      hour,
      load: l,
      cert: c,
      share,
      label: `${hour.slice(0, 16)} UTC: ${int(Math.min(c, l))} of ${int(l)} MWh covered (${pct(share, 0)})`,
    };
  });
  const coverage = mode === "agent" ? week.coverage_agent : week.coverage_naive;
  return {
    load,
    cert,
    cells,
    coverage,
    caption: `Week of ${week.window_start_utc.slice(0, 10)} (UTC). Hourly coverage this week: ${pct(coverage)}. Source: ${week.source}.`,
  };
}
