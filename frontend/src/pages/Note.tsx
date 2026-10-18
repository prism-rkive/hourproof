import { Equal, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { useLoaderData } from "react-router";
import { DataTable } from "@/components/ChartCard";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScopeTag } from "@/components/ScopeTag";
import { SectionHeading } from "@/components/SectionHeading";
import { StatusBadge } from "@/components/StatusBadge";
import { Term } from "@/components/Term";
import { TxList } from "@/components/TxList";
import { getOverview } from "@/lib/api";
import { bps, int, THIS_RUN, tonnes, unixUtc, weeksScope } from "@/lib/format";
import type { Overview } from "@/lib/schemas";
import { runFigures, runWeekScope, slimOverview, step } from "@/lib/selectors";
import { cn } from "@/lib/utils";

export async function loader() {
  return {
    overview: slimOverview(await getOverview(), {
      demoKeys: ["note_terms"],
      window: true,
      steps: ["prove", "prove_emissions", "note"],
      txs: true,
    }),
  };
}

type Terms = {
  base_coupon_bps?: number;
  step_up_bps?: number;
  deadline_unix?: number;
  kpi?: string;
  target_rule?: string;
  target_residual_kg?: number;
  target_bps?: number;
  target_basis?: { residual_kg: number; week_utc: string }[];
};

function Row({ label, children, note }: { label: ReactNode; children: ReactNode; note?: ReactNode }) {
  return (
    <div className="grid gap-1 px-5 py-3.5 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd>
        <span className="tabular text-sm font-medium">{children}</span>
        {note && <span className="mt-0.5 block text-xs text-pretty text-subtle-foreground">{note}</span>}
      </dd>
    </div>
  );
}

function CouponMath({ base, stepUp, coupon, met }: { base: number; stepUp: number; coupon: number; met: boolean }) {
  const box = (label: string, value: string, active: boolean) => (
    <div
      className={cn(
        "flex items-center justify-between rounded-lg border px-4 py-3",
        active ? "border-brand/40 bg-brand-subtle" : "border-border bg-muted",
      )}
    >
      <p className="text-13 text-muted-foreground">{label}</p>
      <p className="tabular text-xl font-semibold">{value}</p>
    </div>
  );
  return (
    <div className="flex flex-col items-stretch gap-2">
      {box("Base coupon", bps(base), true)}
      <Plus className="mx-auto size-4 shrink-0 text-subtle-foreground" aria-label="plus" />
      {box(met ? "Step-up (not applied: KPI met)" : "Step-up (applied: KPI missed)", bps(stepUp), !met)}
      <Equal className="mx-auto size-4 shrink-0 text-subtle-foreground" aria-label="equals" />
      {box("Coupon", bps(coupon), true)}
    </div>
  );
}

export function Component() {
  const { overview: o } = useLoaderData() as { overview: Overview };
  const demo = o.demo;
  const terms = ((demo as { note_terms?: Terms } | null)?.note_terms ?? {}) as Terms;
  const f = runFigures(demo);
  const week = runWeekScope(demo) ?? "The run's week";
  const noteStep = step(demo, "note");
  const source = noteStep?.metrics.notes_subscribed_source;
  const basis = [...(terms.target_basis ?? [])].sort((a, b) => a.week_utc.localeCompare(b.week_utc));
  const residual = terms.kpi === "RESIDUAL_EMISSIONS";

  return (
    <Page className="space-y-12 sm:space-y-16">
      <PageHeader path="/note" />
      {!noteStep || f.couponBps == null ? (
        <p className="text-sm text-muted-foreground">The note has not settled in this run.</p>
      ) : (
        <>
          <section
            data-scope={week}
            aria-labelledby="outcome-h"
            className={cn(
              "rounded-xl border p-6 sm:p-8",
              f.kpiMet ? "border-success/40 bg-success-subtle" : "border-warning/40 bg-warning-subtle",
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={f.kpiMet ? "success" : "warning"}>{f.kpiMet ? "KPI met" : "KPI missed"}</StatusBadge>
              <ScopeTag scope={week} />
            </div>
            <h2 id="outcome-h" className="mt-4 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
              {f.kpiMet
                ? `Target met: the note paid its base coupon of ${bps(f.couponBps)}.`
                : `Target missed: the coupon stepped up to ${bps(f.couponBps)}.`}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-pretty text-muted-foreground sm:text-base">
              {residual && f.targetResidualKg != null
                ? f.kpiMet
                  ? `The emissions proof showed residual emissions of at most ${tonnes(f.provenResidualKg ?? 0)}, within the ${tonnes(f.targetResidualKg)} target fixed by rule before the week, so the note paid its base coupon.`
                  : `No proof showed residual emissions within the ${tonnes(f.targetResidualKg)} target (fixed by rule before the week) by the deadline, so the coupon stepped up automatically.`
                : f.kpiMet
                  ? `The proof met the ${bps(terms.target_bps ?? 0)} target, so the note paid its base coupon.`
                  : `No proof reached the ${bps(terms.target_bps ?? 0)} target by the deadline, so the coupon stepped up automatically.`}
              {residual && !f.kpiMet && f.provenResidualKg != null && (
                <>
                  {" "}
                  The buyer proved ≤ {tonnes(f.provenResidualKg)}, which is above the target; a proof can only state a
                  bound that the true value satisfies.
                </>
              )}
            </p>
          </section>

          <section
            data-scope={week}
            aria-labelledby="terms-h"
            className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"
          >
            <div className="overflow-hidden rounded-xl border border-border bg-card shadow-xs">
              <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
                <h2 id="terms-h" className="text-base font-semibold">
                  Term sheet
                </h2>
                <ScopeTag scope={week} />
              </div>
              <dl className="divide-y divide-border">
                <Row label={<Term id="kpi">KPI</Term>}>
                  {residual ? (
                    <>
                      <Term id="residual-emissions">Residual emissions</Term> of the buyer's week
                    </>
                  ) : (
                    "Hourly coverage"
                  )}
                </Row>
                {f.targetResidualKg != null && (
                  <Row label="Target" note="Fixed by rule before the week; see below.">
                    ≤ {tonnes(f.targetResidualKg)} CO₂
                  </Row>
                )}
                {f.provenResidualKg != null && (
                  <Row label="Proven on-chain" note="By the buyer's zero-knowledge emissions proof.">
                    ≤ {tonnes(f.provenResidualKg)} CO₂
                  </Row>
                )}
                <Row label="KPI met">{f.kpiMet ? "Yes" : "No"}</Row>
                {terms.base_coupon_bps != null && (
                  <Row label={<Term id="coupon">Base coupon</Term>}>{bps(terms.base_coupon_bps)}</Row>
                )}
                {terms.step_up_bps != null && <Row label="Step-up if the KPI is missed">+{bps(terms.step_up_bps)}</Row>}
                <Row label="Coupon">{bps(f.couponBps)}</Row>
                {f.notes != null && (
                  <Row label="Notes subscribed" note={typeof source === "string" ? `Source: ${source}.` : undefined}>
                    {int(f.notes)}
                  </Row>
                )}
                {f.couponPaid != null && (
                  <Row
                    label="Coupon paid"
                    note={
                      <>
                        In <Term id="test-token">tUSD</Term>, a test token with no value.
                      </>
                    }
                  >
                    {int(f.couponPaid)} tUSD
                  </Row>
                )}
                {terms.deadline_unix != null && (
                  <Row
                    label="Deadline"
                    note="Anyone can settle the note: at once if a proof meets the KPI, otherwise after the deadline."
                  >
                    {unixUtc(terms.deadline_unix)} (chain time)
                  </Row>
                )}
              </dl>
            </div>
            <div className="space-y-6">
              {terms.base_coupon_bps != null && terms.step_up_bps != null && (
                <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
                  <h3 className="text-sm font-semibold">How the coupon is set</h3>
                  <p className="mt-1 mb-4 text-13 text-muted-foreground">
                    Investors receive the base coupon if the KPI is proven; otherwise it steps up.
                  </p>
                  <CouponMath
                    base={terms.base_coupon_bps}
                    stepUp={f.kpiMet ? 0 : terms.step_up_bps}
                    coupon={f.couponBps}
                    met={!!f.kpiMet}
                  />
                  {f.couponPaid != null && f.notes != null && (
                    <p className="mt-4 text-13 text-muted-foreground">
                      Paid to the investor:{" "}
                      <span className="tabular font-medium text-foreground">{int(f.couponPaid)} tUSD</span> on{" "}
                      {int(f.notes)} notes.
                    </p>
                  )}
                </div>
              )}
            </div>
          </section>

          {terms.target_rule && basis.length > 0 && f.targetResidualKg != null && (
            <section
              data-scope={weeksScope(basis[0]!.week_utc, basis[basis.length - 1]!.week_utc)}
              aria-labelledby="target-h"
              className="space-y-5"
            >
              <SectionHeading
                id="target-h"
                scope={weeksScope(basis[0]!.week_utc, basis[basis.length - 1]!.week_utc)}
                title="How the target was set"
                sub="The target is computed by a fixed rule from earlier weeks, so it is known before the note is issued and nobody can choose it after the fact."
              />
              <blockquote className="rounded-lg border-l-2 border-brand bg-background-subtle px-4 py-3 text-sm text-pretty text-muted-foreground">
                {terms.target_rule}
              </blockquote>
              <DataTable
                caption="The weeks the target is based on"
                head={["Week starting (UTC)", "Residual emissions"]}
                rows={[
                  ...basis.map((b) => [b.week_utc, tonnes(b.residual_kg)]),
                  ["Target (mean, rounded down to whole kg)", tonnes(f.targetResidualKg)],
                ]}
                className="max-w-xl"
              />
            </section>
          )}

          <section data-scope={THIS_RUN} aria-labelledby="settle-h" className="space-y-5">
            <SectionHeading
              id="settle-h"
              scope={THIS_RUN}
              title="Settlement on-chain"
              sub="Every step of the note, from funding to the investor claiming the coupon, is a transaction you can open on the block explorer."
            />
            <TxList txs={noteStep.txs} />
          </section>
        </>
      )}
    </Page>
  );
}
