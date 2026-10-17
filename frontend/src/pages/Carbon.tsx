import { ChevronDown, Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useLoaderData } from "react-router";
import { ChartCard, DataTable } from "@/components/ChartCard";
import { IntensityChart } from "@/components/charts";
import { HBars } from "@/components/HBars";
import { HourGrid, type GridCell } from "@/components/HourGrid";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScopeTag } from "@/components/ScopeTag";
import { SectionHeading } from "@/components/SectionHeading";
import { Term } from "@/components/Term";
import { getCarbon, getOverview } from "@/lib/api";
import { bps, dayLabel, int, networkName, pct, testScope, weekScope } from "@/lib/format";
import type { Carbon, CarbonData, Overview } from "@/lib/schemas";

export async function loader() {
  const [carbon, overview] = await Promise.all([getCarbon(), getOverview()]);
  return { carbon, overview };
}

const tonnesInt = (t: number) => `${int(t)} t`; // strategy totals: whole tonnes, as on the original page
const t1 = (kg: number) => (kg / 1000).toLocaleString("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const ROBUST_LABEL: Record<string, string> = {
  carbon_model_minus_carbon_persist: "than using last week's intensity",
  carbon_model_minus_shift_for_mwh: "than shifting load for MWh matching",
};

type IntCell = GridCell & { v: number; f: number; forecast: number; shift: number };

/* ------------------------------------------------------------------------------------------------ strategies */

function Strategies({ c }: { c: CarbonData }) {
  const scope = testScope(c.test_period);
  const no = c.strategies.find((s) => s.id === "no_shift")?.emissions_t;
  const max = Math.max(...c.strategies.map((s) => s.emissions_t));
  const red = (e: number) => (no ? 1 - e / no : 0);
  const redTxt = (id: string, e: number) => (id === "no_shift" ? "—" : `−${(100 * red(e)).toFixed(2)}%`);
  return (
    <ChartCard
      scope={scope}
      title="The buyer's location-based emissions, by strategy"
      description={`${c.test_hours.toLocaleString("en-GB")} hours of the IT sector's load. Bars start at zero; the differences are in the right-hand column.`}
      source={
        <>
          Emissions use Energinet's <Term id="location-based">location-based</Term> hourly factors. The reference row
          knows the actual intensity in advance; no real forecast can.
        </>
      }
      table={
        <DataTable
          caption="Emissions by strategy"
          head={["Strategy", "Emissions, t", "vs no shift", "Residual (unmatched), t", "Hourly coverage"]}
          rows={c.strategies.map((s) => [
            s.label,
            int(s.emissions_t),
            redTxt(s.id, s.emissions_t),
            int(s.residual_unmatched_t),
            pct(s.coverage, 2),
          ])}
        />
      }
    >
      <HBars
        label="Emissions by strategy"
        max={max}
        rows={c.strategies.map((s) => ({
          key: s.id,
          label: s.label,
          value: s.emissions_t,
          display: tonnesInt(s.emissions_t),
          extra: s.id === "no_shift" ? undefined : redTxt(s.id, s.emissions_t),
          emphasis: s.id === "carbon_model",
          reference: s.reference,
          badge: !/reference/i.test(s.label),
        }))}
      />
    </ChartCard>
  );
}

function Robustness({ c }: { c: CarbonData }) {
  const scope = testScope(c.test_period);
  const entries = Object.entries(c.robustness).filter(([k]) => ROBUST_LABEL[k]);
  if (!entries.length) return null;
  return (
    <div data-scope={scope} className="grid gap-4 md:grid-cols-2">
      {entries.map(([k, r]) => {
        const t = r.tonnes as number;
        const ci = r.tonnes_ci95 as [number, number];
        const share = r.share_of_resamples_above_zero as number;
        return (
          <div key={k} className="rounded-xl border border-border bg-card p-5 shadow-xs">
            <div className="flex flex-wrap-reverse items-start justify-between gap-2">
              <p className="min-w-[10rem] flex-1 text-13 text-muted-foreground">
                The learned forecast cuts more emissions {ROBUST_LABEL[k]}
              </p>
              <ScopeTag scope={scope} />
            </div>
            <p className="tabular mt-2 text-2xl font-semibold tracking-tight">{tonnesInt(t)} less</p>
            <p className="mt-1.5 text-13 text-muted-foreground">
              95 % interval {int(ci[0])}–{int(ci[1])} t; above zero in {pct(share, 0)} of resamples.
            </p>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ proof */

function ProofCard({ c, scope }: { c: CarbonData; scope: string }) {
  const p = (c.proof ?? null) as Record<string, unknown> | null;
  if (!p) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
        No emissions proof yet.
      </div>
    );
  }
  const num = (k: string) => (typeof p[k] === "number" ? (p[k] as number) : undefined);
  const residual = num("residual_kg");
  const target = num("target_kg");
  return (
    <aside
      data-scope={scope}
      aria-labelledby="proof-h"
      className="flex flex-col rounded-xl border border-brand/40 bg-brand-subtle/40 p-5 shadow-xs"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 id="proof-h" className="flex items-center gap-1.5 text-13 font-medium text-brand">
          <ShieldCheck className="size-4" aria-hidden /> On-chain proof
        </h3>
        <ScopeTag scope={scope} />
      </div>
      {residual != null && (
        <p className="tabular mt-4 text-2xl font-semibold tracking-tight">Residual ≤ {t1(residual)} t CO₂</p>
      )}
      {num("coverage_bps") != null && <p className="tabular mt-1 text-base">Coverage ≥ {bps(num("coverage_bps")!)}</p>}
      <p className="mt-3 inline-flex w-fit items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground">
        <Lock className="size-3" aria-hidden /> Hourly load: private
      </p>
      <p className="mt-4 text-13 leading-relaxed text-muted-foreground">
        {typeof p.fixture_week === "string"
          ? `Real proof over the week of ${p.fixture_week} (Solidity test fixture).`
          : `${p.zk_mode === "mock" ? "MOCK verifier (test mode, not a real proof)" : "UltraHonk proof"} on ${
              p.network === "base-sepolia"
                ? "Base Sepolia"
                : typeof p.network === "string"
                  ? networkName(p.network)
                  : "a local replay chain"
            }${num("gas") ? `, ${int(num("gas")!)} gas` : ""}.`}{" "}
        {target != null &&
          `Note target ≤ ${t1(target)} t: ${p.kpi_met ? "met, base coupon" : "missed, coupon stepped up"}. `}
        The hourly intensities are public; the contract rebuilds them from the intensity oracle.
      </p>
    </aside>
  );
}

/* ------------------------------------------------------------------------------------------------ the week */

function TheWeek({ c }: { c: CarbonData }) {
  const w = c.week!;
  const scope = weekScope(w.hours[0]!);
  const days = Array.from({ length: Math.floor(w.hours.length / 24) }, (_, d) => d);
  const [day, setDay] = useState<number | "all">("all");
  const sl = (a: number[]) => (day === "all" ? a : a.slice(day * 24, day * 24 + 24));
  const lo = Math.min(...w.intensity);
  const hi = Math.max(...w.intensity);
  const cells: IntCell[] = w.hours.map((hour, i) => {
    const v = w.intensity[i]!;
    const sh = w.shift_mwh[i] ?? 0;
    const plan = Math.abs(sh) > 0.05 ? `; plan ${sh > 0 ? "+" : "−"}${Math.abs(sh).toFixed(1)} MWh` : "";
    return {
      i,
      hour,
      v,
      f: hi > lo ? (v - lo) / (hi - lo) : 0,
      forecast: w.forecast[i]!,
      shift: sh,
      label: `${hour.slice(0, 16)} UTC: ${Math.round(v)} g/kWh actual, ${Math.round(w.forecast[i]!)} forecast${plan}`,
    };
  });
  const mae = w.mae
    ? ` Forecast error this week ${w.mae.model!.toFixed(1)} g/kWh (last week's value: ${w.mae.lag168!.toFixed(1)}).`
    : "";
  return (
    <section aria-labelledby="wk-h" className="space-y-6">
      <SectionHeading
        id="wk-h"
        title="The run's week, hour by hour"
        sub="How clean the grid was each hour, what the agent expected the day before, and where it moved flexible load."
      />
      <ChartCard
        scope={scope}
        title="Hourly grid intensity: the agent's forecast and the actual"
        description="The actual values are Energinet's location-based intensities, as posted on-chain. The forecast was made the day before."
        actions={
          <label className="flex items-center gap-2 text-13 text-muted-foreground">
            Show
            <span className="relative">
              <select
                value={day}
                onChange={(e) => setDay(e.target.value === "all" ? "all" : Number(e.target.value))}
                className="h-8 appearance-none rounded-md border border-input bg-background pr-8 pl-3 text-13 text-foreground"
              >
                <option value="all">Whole week</option>
                {days.map((d) => (
                  <option key={d} value={d}>
                    {dayLabel(w.hours[d * 24]!)}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2"
                aria-hidden
              />
            </span>
          </label>
        }
        footer={
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-hidden>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 bg-foreground" /> Actual (Energinet, location-based)
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0 w-4 border-t-2 border-dashed border-[var(--series-2)]" /> Agent's day-ahead forecast
            </span>
          </div>
        }
        source={
          w.mae ? `Week of ${w.hours[0]!.slice(0, 10)} (UTC).${mae} Source: ${w.source}.` : `Source: ${w.source}.`
        }
        table={
          <DataTable
            caption="Hourly intensity, forecast and planned shift"
            head={["Hour (UTC)", "Actual, g/kWh", "Forecast, g/kWh", "Planned shift, MWh"]}
            rows={cells.map((x) => [
              `${dayLabel(x.hour)} ${x.hour.slice(11, 16)}`,
              Math.round(x.v),
              Math.round(x.forecast),
              x.shift.toFixed(1),
            ])}
          />
        }
      >
        <IntensityChart
          hours={day === "all" ? w.hours : w.hours.slice(day * 24, day * 24 + 24)}
          actual={sl(w.intensity)}
          forecast={sl(w.forecast)}
          shift={sl(w.shift_mwh)}
          ariaLabel="Hourly CO2 intensity, forecast and actual"
        />
      </ChartCard>

      <ChartCard
        scope={scope}
        title="The week, shaded by intensity"
        description="Darker squares are dirtier hours. A dot marks an hour into which the agent planned to move flexible load."
        source={`Week of ${w.hours[0]!.slice(0, 10)} (UTC). Shading runs along the scale, from the cleanest hour of the week to the dirtiest.${mae} Source: ${w.source}.`}
      >
        <HourGrid
          cells={cells}
          label="One week, hour by hour, shaded by grid intensity"
          renderCell={(x) => (
            <>
              <div
                className="absolute inset-0"
                style={{ background: `color-mix(in oklab, var(--seq-hi) ${(100 * x.f).toFixed(1)}%, var(--seq-lo))` }}
              />
              {x.shift > 0.05 && (
                <span className="absolute top-1/2 left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground ring-2 ring-background sm:size-2" />
              )}
            </>
          )}
          idle="Hover over or focus an hour to see its numbers."
          readout={(x) => (
            <>
              <span className="font-medium text-foreground">
                {dayLabel(x.hour)}, {x.hour.slice(11, 16)} UTC
              </span>
              {" · "}
              {Math.round(x.v)} g/kWh actual, {Math.round(x.forecast)} forecast
              {Math.abs(x.shift) > 0.05 &&
                `; plan ${x.shift > 0 ? "+" : "−"}${Math.abs(x.shift).toFixed(1)} MWh ${x.shift > 0 ? "moved in" : "deferred"}`}
            </>
          )}
          legend={
            <>
              <span className="inline-flex items-center gap-1.5">
                <span className="tabular">{Math.round(lo)}</span>
                <span
                  className="h-2.5 w-20 rounded-full"
                  style={{ background: "linear-gradient(90deg, var(--seq-lo), var(--seq-hi))" }}
                />
                <span className="tabular">{Math.round(hi)} g/kWh</span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-foreground" /> flexible load moved into this hour
              </span>
            </>
          }
        />
      </ChartCard>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ page */

export function Component() {
  const { carbon: c, overview: o } = useLoaderData() as { carbon: Carbon; overview: Overview };
  if (!c.available) {
    return (
      <Page>
        <PageHeader path="/carbon" />
        <p className="mt-10 text-sm text-muted-foreground">No carbon backtest yet: python -m hourproof agent carbon</p>
      </Page>
    );
  }
  const test = testScope(c.test_period);
  const m = c.mae;
  const proofScope = c.week ? weekScope(c.week.hours[0]!) : o.demo ? "The run's week" : "Test fixture";
  return (
    <Page className="space-y-12 sm:space-y-16">
      <PageHeader path="/carbon" />

      <section data-scope={test} aria-labelledby="idea-h" className="space-y-4">
        <ScopeTag scope={test} />
        <h2 id="idea-h" className="text-2xl font-semibold tracking-tight">
          Move load to cleaner hours, then prove the result
        </h2>
        <p className="max-w-3xl text-sm leading-relaxed text-pretty text-muted-foreground">
          A learned day-ahead forecast of Denmark's hourly grid CO2 intensity moves {pct(c.frozen_config.flex_share, 0)}{" "}
          of each hour's load (a declared scenario parameter) into cleaner hours of the same day. Test{" "}
          {c.test_period[0]} to {c.test_period[1]}, run once with choices frozen on validation. Forecast error{" "}
          {m.model!.toFixed(1)} g/kWh vs {m.lag168!.toFixed(1)} for last week's value (
          {Math.round(100 * c.improvement_vs_best_persistence)}% lower).
        </p>
        <p className="max-w-3xl text-sm leading-relaxed text-pretty text-muted-foreground">
          The buyer then proves its <Term id="residual-emissions">residual emissions</Term> with a{" "}
          <Term id="zk-proof">zero-knowledge proof</Term>, using the intensities posted on-chain and the same commitment
          to its load as the coverage proof.
        </p>
      </section>

      <section aria-labelledby="res-h" className="space-y-5">
        <SectionHeading id="res-h" title="Emissions by strategy" sub="Lower is better." />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)]">
          <Strategies c={c} />
          <ProofCard c={c} scope={proofScope} />
        </div>
        <Robustness c={c} />
      </section>

      {c.week && <TheWeek c={c} />}

      <section data-scope={test} aria-labelledby="cav-h">
        <details className="group rounded-xl border border-border bg-card shadow-xs">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-5 py-4 hover:bg-accent/40">
            <span className="flex flex-wrap items-center gap-3">
              <h2 id="cav-h" className="text-base font-semibold">
                Caveats
              </h2>
              <ScopeTag scope={test} />
            </span>
            <ChevronDown
              className="size-4 text-subtle-foreground transition-transform group-open:rotate-180"
              aria-hidden
            />
          </summary>
          <ul className="space-y-2 border-t border-border px-5 py-4 text-sm text-muted-foreground">
            {c.caveats.map((x) => (
              <li key={x} className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-subtle-foreground" aria-hidden />
                {x}
              </li>
            ))}
          </ul>
        </details>
      </section>
    </Page>
  );
}
