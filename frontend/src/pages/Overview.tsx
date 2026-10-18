import { ArrowRight, BadgeCheck, Bot, FileSignature, Landmark, ShieldCheck } from "lucide-react";
import { Hydrate } from "@/components/Hydrate";
import { useState } from "react";
import { Link, useLoaderData } from "react-router";
import { ChartCard, DataTable } from "@/components/ChartCard";
import { HourlyChart } from "@/components/charts";
import { KpiCard } from "@/components/KpiCard";
import { ScopeTag } from "@/components/ScopeTag";
import { Page } from "@/components/layout/AppShell";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Term } from "@/components/Term";
import { Button } from "@/components/ui/button";
import { WeekHeatmap } from "@/components/WeekHeatmap";
import { useDocumentMeta } from "@/hooks/useDocumentMeta";
import { getOverview, getWeek } from "@/lib/api";
import { bps, dateLabel, FULL_YEAR, int, networkName, pct, pctShort, tonnes, weekScope } from "@/lib/format";
import type { Overview, Week, WeekData } from "@/lib/schemas";
import { hero, overviewForHome, runFigures, runWeekScope, weekView, type WeekMode } from "@/lib/selectors";
import { pageMeta } from "@/routes";

export async function loader() {
  const [overview, week] = await Promise.all([getOverview(), getWeek()]);
  return { overview: overviewForHome(overview), week };
}

const MODES: { value: WeekMode; label: string; explain: string }[] = [
  {
    value: "naive",
    label: "Fixed portfolio",
    explain: "The buyer's yearly wind purchase, spread over the hours as the wind actually blew.",
  },
  {
    value: "agent",
    label: "With the agent",
    explain:
      "The AI agent moves part of the flexible load into windier hours and buys extra certificates for chosen hours.",
  },
];

/* ------------------------------------------------------------------------------------------------ hero */

function Hero({ o }: { o: Overview }) {
  const h = hero(o);
  const annual = o.annual_match;
  const hourly = o.dataset?.hourly_match_of_100pct_annual_wind;
  return (
    <section className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:gap-14">
      <div data-scope={FULL_YEAR}>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-13 font-medium text-brand">Hourly clean-energy claims</p>
          <ScopeTag scope={FULL_YEAR} />
        </div>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
          <span className="block">{h?.annual ?? "Clean over the year."}</span>
          <span className="block text-muted-foreground">{h?.hourly ?? "Hour by hour?"}</span>
        </h1>
        {h && <p className="mt-6 max-w-2xl text-base text-pretty text-muted-foreground sm:text-lg">{h.lede}</p>}
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild variant="brand" size="lg">
            <Link to="/proof">
              See the proof run <ArrowRight aria-hidden />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link to="/method#limits">What this does not claim</Link>
          </Button>
        </div>
      </div>
      {annual != null && hourly != null && (
        <figure data-scope={FULL_YEAR} className="m-0 rounded-xl border border-border bg-card p-6 shadow-sm">
          <figcaption className="flex items-start justify-between gap-3 text-sm font-medium">
            The same purchase, counted two ways
            <ScopeTag scope={FULL_YEAR} />
          </figcaption>
          <div className="mt-6 space-y-5">
            <MatchBar label="Counted over the year" value={annual} />
            <MatchBar label="Counted hour by hour" value={hourly} />
          </div>
          <p className="mt-6 text-13 leading-relaxed text-muted-foreground">
            Over a year the wind purchase equals the buyer's use. With <Term id="hourly-matching">hourly matching</Term>
            , wind that blew in the wrong hour cannot cover use, so a gap appears.
          </p>
        </figure>
      )}
    </section>
  );
}

function MatchBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-13">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular text-lg font-semibold">{pctShort(value)}</span>
      </div>
      <div className="hatch mt-2 h-3 overflow-hidden rounded-full" aria-hidden>
        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, 100 * value)}%` }} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ plain terms */

function InPlainTerms({ o }: { o: Overview }) {
  const network = o.demo ? networkName(o.demo.network) : null;
  const points = [
    {
      title: "The problem",
      body: (
        <>
          Clean-energy purchases are usually counted over a whole year. Buying a year's worth of clean electricity does
          not mean using clean electricity every hour.
        </>
      ),
    },
    {
      title: "What HourProof does",
      body: (
        <>
          It counts clean energy hour by hour, makes sure each hour's <Term id="certificate">certificate</Term> is
          claimed only once, and lets the buyer prove its result without revealing its usage. An AI agent helps cover
          more hours.
        </>
      ),
    },
    {
      title: "How you can check",
      body: network ? (
        <>
          The whole flow ran on{" "}
          {o.demo?.network === "base-sepolia" ? <Term id="base-sepolia">{network}</Term> : network}. Every step links to
          its <Term id="transaction">transaction</Term>, which anyone can look up.
        </>
      ) : (
        <>Run the demo to put every step on a chain, with a link to each transaction.</>
      ),
    },
  ];
  return (
    <section aria-labelledby="plain-h" className="rounded-xl border border-border bg-background-subtle p-6 sm:p-8">
      <h2 id="plain-h" className="text-13 font-medium text-brand">
        In plain terms
      </h2>
      <ol className="mt-5 grid gap-6 md:grid-cols-3 md:gap-8">
        {points.map((p, i) => (
          <li key={p.title} className="flex gap-3">
            <span
              className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border-strong font-mono text-xs text-muted-foreground"
              aria-hidden
            >
              {i + 1}
            </span>
            <div>
              <h3 className="text-sm font-semibold">{p.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-pretty text-muted-foreground">{p.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ key results */

function KeyResults({ o }: { o: Overview }) {
  const f = runFigures(o.demo);
  const hourly = o.dataset?.hourly_match_of_100pct_annual_wind;
  const demo = o.demo;
  const week = runWeekScope(demo) ?? "The run's week";
  return (
    <section aria-labelledby="results-h">
      <SectionHeading
        id="results-h"
        title="Key results"
        sub={
          demo
            ? `Each figure shows the period it covers. The weekly figures come from run ${demo.run_id} on ${networkName(demo.network)}.`
            : "Each figure shows the period it covers."
        }
      />
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KpiCard
          scope={FULL_YEAR}
          label="Clean energy bought, over the year"
          value={o.annual_match != null ? pctShort(o.annual_match) : undefined}
          hint="Wind certificates bought, divided by electricity used, both totalled over the whole year."
          href="/method"
          linkLabel="Data and method"
        />
        <KpiCard
          scope={FULL_YEAR}
          label="Matched hour by hour, over the year"
          value={hourly != null ? pct(hourly) : undefined}
          hint={
            <>
              The share of use met by wind produced in the same hour. This is the gap{" "}
              <Term id="hourly-matching">hourly matching</Term> reveals.
            </>
          }
          href="/agent"
          linkLabel="How the agent narrows it"
        />
        <KpiCard
          emphasis
          scope={week}
          label="Coverage proven on-chain"
          qualifier="≥"
          value={f.provenBps != null ? bps(f.provenBps) : undefined}
          hint={
            <>
              For the run's week, the buyer proved its hourly <Term id="coverage">coverage</Term> is at least this, with
              a <Term id="zk-proof">zero-knowledge proof</Term>. Its usage stays private.
            </>
          }
          href="/proof"
          linkLabel="See the proof"
        />
        <KpiCard
          scope={week}
          label="True coverage (private)"
          value={f.truePrivateBps != null ? bps(f.truePrivateBps) : undefined}
          hint="The exact figure, known only to the buyer. Shown here because this demo plays the buyer; the chain only learns the proven bound."
          href="/proof"
          linkLabel="See the proof"
        />
        <KpiCard
          emphasis
          scope={week}
          label="Residual emissions proven"
          qualifier="≤"
          value={f.provenResidualKg != null ? `${tonnes(f.provenResidualKg)} CO₂` : undefined}
          hint={
            <>
              The week's <Term id="residual-emissions">residual emissions</Term>, proven without revealing usage.
              {f.targetResidualKg != null && <> The note's target was ≤ {tonnes(f.targetResidualKg)}.</>}
            </>
          }
          href="/carbon"
          linkLabel="Carbon-aware load"
        />
        <KpiCard
          scope={week}
          label={
            <>
              Note <Term id="coupon">coupon</Term>
            </>
          }
          value={f.couponBps != null ? bps(f.couponBps) : undefined}
          hint={
            f.kpiMet === undefined
              ? "Settles when the note's deadline passes."
              : f.kpiMet
                ? "The proven emissions met the target, so the note paid its base coupon."
                : `No proof showed emissions within the ${f.targetResidualKg != null ? `${tonnes(f.targetResidualKg)} ` : ""}target by the deadline, so the coupon stepped up${f.couponPaid != null && f.notes != null ? `: ${int(f.couponPaid)} tUSD paid on ${int(f.notes)} notes` : ""}.`
          }
          href="/note"
          linkLabel="The note"
        />
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ the week */

function TheWeek({ o, week }: { o: Overview; week: WeekData }) {
  const [mode, setMode] = useState<WeekMode>("naive");
  const v = weekView(week, mode);
  const f = runFigures(o.demo);
  const scope = runWeekScope(o.demo) ?? weekScope(week.window_start_utc);
  const runBps = mode === "agent" ? f.truePrivateBps : f.naiveBps; // the run's figure leads; the heatmap's is in the caption
  const days = Array.from({ length: v.cells.length / 24 }, (_, d) => v.cells.slice(d * 24, d * 24 + 24));
  const explain = MODES.find((m) => m.value === mode)!.explain;
  const hourlyRows = v.cells.map((c) => [`${dateLabel(c.hour)} ${c.hour.slice(11, 16)}`, int(c.cert), int(c.load)]);
  return (
    <section aria-labelledby="week-h" className="space-y-6">
      <SectionHeading
        id="week-h"
        title="One week, hour by hour"
        sub="Each square is one hour of the run's week. The green part is how much of that hour's use was covered by certificates from the same hour."
      />
      <ChartCard
        scope={scope}
        title={
          <>
            <span className="tabular">{runBps != null ? bps(runBps) : pct(v.coverage)}</span>{" "}
            <span className="font-normal text-muted-foreground">of the week's use covered, hour by hour</span>
          </>
        }
        description={
          <>
            {explain} The figure is the run's, from its on-chain certificates
            {mode === "agent" ? " (the buyer's private value; the chain only learns the proven bound)" : ""}.
          </>
        }
        actions={
          <SegmentedControl
            label="Strategy"
            value={mode}
            onChange={setMode}
            options={MODES.map(({ value, label }) => ({ value, label }))}
          />
        }
        source={
          <>
            {v.caption} This heatmap figure uses the backtest's fractional MWh; the run issued certificates in whole
            MWh, so the run's figure above differs slightly.
          </>
        }
        table={
          <DataTable
            caption="Share of each hour's use covered by certificates"
            head={["Day", ...Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`)]}
            rows={days.map((row) => [dateLabel(row[0]!.hour), ...row.map((c) => pct(c.share, 0))])}
          />
        }
      >
        <WeekHeatmap cells={v.cells} label={`One week, hour by hour: ${MODES.find((m) => m.value === mode)!.label}`} />
      </ChartCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          scope={scope}
          title="What the chain sees"
          description="Certificates cancelled per hour, and a proof that coverage is at least the target. Nothing about consumption."
          table={
            <DataTable
              caption="Certificates per hour"
              head={["Hour (UTC)", "Certificates (MWh)"]}
              rows={hourlyRows.map(([h, c]) => [h!, c!])}
            />
          }
          footer={
            <ProofLine
              label="Proven on-chain, by the run (with the agent)"
              value={f.provenBps != null ? `coverage ≥ ${bps(f.provenBps)}` : "no proof on-chain yet"}
            />
          }
        >
          <HourlyChart hours={week.hours} bars={v.cert} barLabel="Certificates" ariaLabel="Certificates per hour" />
        </ChartCard>
        <ChartCard
          scope={scope}
          title="What only the buyer sees"
          description="The metered load. It stays with the buyer and the data hub; only a commitment to it is published."
          table={
            <DataTable
              caption="Certificates and load per hour"
              head={["Hour (UTC)", "Certificates (MWh)", "Load (MWh)"]}
              rows={hourlyRows}
            />
          }
          footer={
            <ProofLine
              label="True coverage, private (the run, with the agent)"
              value={f.truePrivateBps != null ? bps(f.truePrivateBps) : "—"}
              legend
            />
          }
        >
          <HourlyChart
            hours={week.hours}
            bars={v.cert}
            barLabel="Certificates"
            line={v.load}
            lineLabel="Load"
            ariaLabel="The buyer's private hourly load, with certificates per hour"
          />
        </ChartCard>
      </div>
    </section>
  );
}

function ProofLine({ label, value, legend }: { label: string; value: string; legend?: boolean }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 rounded-lg bg-muted px-4 py-3">
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="tabular text-lg font-semibold">{value}</p>
      </div>
      {legend ? (
        <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-brand/45" /> Certificates
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-3 bg-foreground" /> Load
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground" aria-hidden>
          <span className="size-2.5 rounded-sm bg-brand" /> Certificates
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ how it works */

const STEPS = [
  {
    icon: FileSignature,
    title: "Hourly certificates",
    body: "Metered hourly production becomes certificates. Each daily batch carries a post-quantum signature that a contract checks.",
    href: "/proof",
  },
  {
    icon: ShieldCheck,
    title: "Claimed only once",
    body: "The buyer cancels certificates into its claim. Claiming an hour twice, or more than was produced, is refused.",
    href: "/security",
  },
  {
    icon: BadgeCheck,
    title: "Proven privately",
    body: "The buyer proves its hourly coverage and residual emissions in zero knowledge. Its usage never goes on-chain.",
    href: "/proof",
  },
  {
    icon: Bot,
    title: "Improved by an agent",
    body: "An AI agent shifts flexible load and buys extra hours. Its daily plans are committed on-chain and revealed afterwards for checking.",
    href: "/agent",
  },
  {
    icon: Landmark,
    title: "Settled on the proof",
    body: "A sustainability-linked note sets its coupon on-chain from the proven emissions.",
    href: "/note",
  },
] as const;

function HowItWorks() {
  return (
    <section aria-labelledby="how-h">
      <SectionHeading id="how-h" title="How it works" sub="Five steps, each with its own page." />
      <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <Link
              to={s.href}
              className="group flex h-full flex-col rounded-xl border border-border bg-card p-5 shadow-xs transition-colors hover:border-border-strong"
            >
              <div className="flex items-center justify-between">
                <s.icon className="size-5 text-brand" aria-hidden />
                <span className="font-mono text-xs text-subtle-foreground">0{i + 1}</span>
              </div>
              <h3 className="mt-4 text-sm font-semibold">{s.title}</h3>
              <p className="mt-1.5 flex-1 text-13 leading-relaxed text-muted-foreground">{s.body}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-13 font-medium">
                {pageMeta(s.href).title}
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function SectionHeading({ id, title, sub }: { id: string; title: string; sub?: string }) {
  return (
    <div className="max-w-3xl">
      <h2 id={id} className="text-2xl font-semibold tracking-tight">
        {title}
      </h2>
      {sub && <p className="mt-2 text-sm text-pretty text-muted-foreground">{sub}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ page */

export function Component() {
  const { overview, week } = useLoaderData() as { overview: Overview; week: Week };
  const meta = pageMeta("/");
  useDocumentMeta("HourProof", meta.description);
  return (
    <Page className="space-y-16 sm:space-y-20">
      <Hero o={overview} />
      <Hydrate>
        <InPlainTerms o={overview} />
      </Hydrate>
      <Hydrate>
        <KeyResults o={overview} />
      </Hydrate>
      <Hydrate>
        {week.available ? (
          <TheWeek o={overview} week={week} />
        ) : (
          <p className="text-sm text-muted-foreground">No week of data yet: run the agent backtest, then reload.</p>
        )}
      </Hydrate>
      <Hydrate>
        <HowItWorks />
      </Hydrate>
    </Page>
  );
}
