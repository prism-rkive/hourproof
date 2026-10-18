import { CalendarClock, LineChart, ShoppingCart, Shuffle } from "lucide-react";
import { useLoaderData } from "react-router";
import { ChartCard, DataTable } from "@/components/ChartCard";
import { HBars } from "@/components/HBars";
import { KpiCard } from "@/components/KpiCard";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/SectionHeading";
import { Term } from "@/components/Term";
import { TxList } from "@/components/TxList";
import { getOverview } from "@/lib/api";
import { int, pct, testScope, THIS_RUN } from "@/lib/format";
import type { Overview } from "@/lib/schemas";
import { slimOverview, step } from "@/lib/selectors";

export async function loader() {
  return {
    overview: slimOverview(await getOverview(), { backtest: true, steps: ["agent_commit", "agent_reveal"], txs: true }),
  };
}

type Backtest = {
  test_period: [string, string];
  coverage: Record<string, number>;
  params: { flex_share: number; flex_cap: number; topup_share: number };
  extra_share_of_test_load: number;
  gain_vs_same_mwh_pp: number;
  forecast_skill: Record<string, number>;
  note?: string;
};

/** The five strategies, in the original dashboard's order and wording. */
const STRATEGIES: { id: string; label: string; emphasis?: boolean; reference?: boolean }[] = [
  { id: "naive_fixed_portfolio", label: "Fixed portfolio" },
  { id: "bigger_portfolio_same_mwh", label: "Bigger portfolio, same MWh" },
  { id: "agent_shift_only", label: "Agent: moving flexible load" },
  { id: "agent_shift_and_topup", label: "Agent: moving load and buying hours", emphasis: true },
  { id: "perfect_foresight_bound", label: "Perfect foresight (reference)", reference: true },
];

export function Component() {
  const { overview: o } = useLoaderData() as { overview: Overview };
  const bt = o.backtest as Backtest | null;
  const demo = o.demo;
  const commit = step(demo, "agent_commit");
  const reveal = step(demo, "agent_reveal");

  if (!bt) {
    return (
      <Page>
        <PageHeader path="/agent" />
        <p className="mt-10 text-sm text-muted-foreground">No backtest yet: python -m hourproof agent backtest</p>
      </Page>
    );
  }
  const scope = testScope(bt.test_period);
  const sk = bt.forecast_skill;
  const rows = STRATEGIES.filter((s) => bt.coverage[s.id] != null).map((s) => ({
    key: s.id,
    label: s.id === "perfect_foresight_bound" ? <Term id="perfect-foresight">{s.label}</Term> : s.label,
    value: bt.coverage[s.id]!,
    display: pct(bt.coverage[s.id]!),
    emphasis: s.emphasis,
    reference: s.reference,
    badge: false, // the label already says "(reference)"
  }));

  return (
    <Page className="space-y-12 sm:space-y-16">
      <PageHeader path="/agent" />

      <section aria-labelledby="how-h" className="space-y-5">
        <SectionHeading
          id="how-h"
          title="What the agent does"
          sub={
            <>
              Every day, before the day starts, the agent makes two decisions for the next day. It is tested{" "}
              <Term id="walk-forward">walk-forward</Term> on real hours it never trained on.
            </>
          }
        />
        <ol className="grid gap-4 md:grid-cols-3">
          {[
            {
              icon: LineChart,
              title: "Forecast",
              body: "It forecasts tomorrow's hourly wind production and the buyer's load, using only data published by the decision time.",
            },
            {
              icon: Shuffle,
              title: "Move flexible load",
              body: (
                <>
                  It moves part of the <Term id="flexible-load">flexible load</Term> into hours with more wind.
                </>
              ),
            },
            {
              icon: ShoppingCart,
              title: "Buy hours",
              body: "It buys extra certificates for the hours its own portfolio will not cover, within a fixed budget.",
            },
          ].map((s) => (
            <li key={s.title} className="rounded-xl border border-border bg-card p-5 shadow-xs">
              <s.icon className="size-5 text-brand" aria-hidden />
              <h3 className="mt-3 text-sm font-semibold">{s.title}</h3>
              <p className="mt-1.5 text-13 leading-relaxed text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
        {bt.note && (
          <p className="flex gap-2 rounded-lg border border-border bg-background-subtle px-4 py-3 text-13 text-muted-foreground">
            <CalendarClock className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
            <span>
              <span className="font-medium text-foreground">Method note from the backtest: </span>
              {bt.note}
            </span>
          </p>
        )}
      </section>

      <section aria-labelledby="res-h" className="space-y-5">
        <SectionHeading
          id="res-h"
          title="Hourly coverage by strategy"
          sub="The share of the buyer's use covered by certificates from the same hour, over the test half-year. Higher is better."
        />
        <ChartCard
          scope={scope}
          title="On the second half of the year"
          description={`Walk-forward on real hours, ${bt.test_period[0]} to ${bt.test_period[1]}. Flexible share ${pct(bt.params.flex_share, 0)} of each hour's load (scenario parameter); extra certificates ${pct(bt.extra_share_of_test_load)} of load, and the comparison portfolio gets exactly the same extra MWh.`}
          source="Bars start at zero. Perfect foresight uses the same policy and budget fed with the actual load, wind and availability; no real strategy can reach it."
          table={
            <DataTable
              caption="Hourly coverage by strategy"
              head={["Strategy", "Hourly coverage"]}
              rows={STRATEGIES.filter((s) => bt.coverage[s.id] != null).map((s) => [s.label, pct(bt.coverage[s.id]!)])}
            />
          }
        >
          <HBars rows={rows} max={1} label="Hourly coverage by strategy" />
        </ChartCard>
      </section>

      <section aria-labelledby="skill-h" className="space-y-5">
        <SectionHeading
          id="skill-h"
          title="How good are its forecasts?"
          sub={`Average error per hour on the test half-year; lower is better.${
            sk.load_mae_model_mwh != null &&
            sk.load_mae_lag168_mwh != null &&
            sk.load_mae_model_mwh > sk.load_mae_lag168_mwh
              ? " The agent's load forecast is less accurate than simply repeating last week's load."
              : ""
          }`}
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            scope={scope}
            emphasis
            label="Gain over the same MWh"
            value={`${bt.gain_vs_same_mwh_pp >= 0 ? "+" : ""}${bt.gain_vs_same_mwh_pp.toFixed(1)} points`}
            hint="Agent's hourly coverage minus a bigger fixed portfolio that gets exactly the same extra MWh."
          />
          <KpiCard
            scope={scope}
            label="Wind error, published forecast"
            value={sk.wind_mae_raw_forecast_mwh != null ? `${int(sk.wind_mae_raw_forecast_mwh)} MWh/h` : undefined}
            hint="Energinet's own day-ahead wind forecast, as a baseline."
          />
          <KpiCard
            scope={scope}
            label="Wind error, agent's model"
            value={sk.wind_mae_model_mwh != null ? `${int(sk.wind_mae_model_mwh)} MWh/h` : undefined}
            hint="The agent's own wind model."
          />
          <KpiCard
            scope={scope}
            label="Load error, agent vs last week"
            value={
              sk.load_mae_model_mwh != null && sk.load_mae_lag168_mwh != null
                ? `${sk.load_mae_model_mwh.toFixed(1)} vs ${sk.load_mae_lag168_mwh.toFixed(1)} MWh/h`
                : undefined
            }
            hint="The agent's load forecast against simply repeating last week's load."
          />
        </div>
      </section>

      {(commit || reveal) && (
        <section data-scope={THIS_RUN} aria-labelledby="chain-h" className="space-y-5">
          <SectionHeading
            id="chain-h"
            scope={THIS_RUN}
            title="Its plans, on-chain"
            sub={
              <>
                Each daily plan is committed as a <Term id="commitment">commitment</Term> and revealed afterwards; the
                contract checks that every revealed plan matches its commitment.
              </>
            }
          />
          <div className="grid gap-4 lg:grid-cols-2">
            {[commit, reveal].map(
              (s) =>
                s && (
                  <div key={s.id} className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-xs">
                    <h3 className="text-sm font-semibold text-pretty">{s.title}</h3>
                    {s.detail && (
                      <p className="rounded-md bg-muted px-3 py-2 font-mono text-xs leading-relaxed break-words">
                        {s.detail}
                      </p>
                    )}
                    <TxList txs={s.txs} />
                  </div>
                ),
            )}
          </div>
          {commit?.detail?.includes("late") && (
            <p className="text-xs text-pretty text-subtle-foreground">
              The run replays a past week, so on a public chain its plans can only be committed after the fact. They
              still cannot change between commitment and reveal; committing ahead of time is what the live mode is for.
            </p>
          )}
        </section>
      )}
    </Page>
  );
}
