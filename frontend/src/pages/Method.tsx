import { AlertTriangle, BookOpen, Database, ExternalLink, KeyRound, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { useLoaderData } from "react-router";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScopeTag } from "@/components/ScopeTag";
import { SectionHeading } from "@/components/SectionHeading";
import { SectorName } from "@/components/SectorName";
import { Term } from "@/components/Term";
import { GLOSSARY } from "@/content/glossary";
import { LIMITS } from "@/content/limits";
import { getCarbon, getOverview } from "@/lib/api";
import { FULL_YEAR, int, pct, shortHash, THIS_RUN } from "@/lib/format";
import type { Carbon, Overview } from "@/lib/schemas";
import { sector } from "@/lib/sector";
import { metric, slimOverview } from "@/lib/selectors";
import { DATA_SOURCE_URL } from "@/routes";

export async function loader() {
  const [overview, carbon] = await Promise.all([getOverview(), getCarbon()]);
  return {
    overview: slimOverview(overview, {
      dataset: true,
      backtest: true,
      zk: true,
      demoKeys: ["contracts"],
      steps: ["prove", "prove_emissions"],
    }),
    carbon,
  };
}

const PARAMS = "Declared parameter";

function Facts({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="divide-y divide-border">
      {rows.map(([k, v], i) => (
        <div key={i} className="grid gap-1 py-3 sm:grid-cols-[14rem_minmax(0,1fr)] sm:gap-6">
          <dt className="text-sm text-muted-foreground">{k}</dt>
          <dd className="tabular text-sm break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Card({
  icon: Icon,
  id,
  title,
  scope,
  children,
}: {
  icon: typeof Database;
  id: string;
  title: string;
  scope?: string;
  children: ReactNode;
}) {
  return (
    <section
      data-scope={scope}
      aria-labelledby={id}
      className="rounded-xl border border-border bg-card p-5 shadow-xs sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="flex items-center gap-2 text-base font-semibold">
          <Icon className="size-4 text-brand" aria-hidden />
          {title}
        </h2>
        {scope && <ScopeTag scope={scope} />}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Component() {
  const { overview: o, carbon: c } = useLoaderData() as { overview: Overview; carbon: Carbon };
  const ds = o.dataset as (Record<string, unknown> & { source?: string; datasets?: string[] }) | null;
  const buyer = ds && sector(ds.buyer_branch, ds.buyer_label);
  const bt = o.backtest as { params?: Record<string, number>; portfolio_share_k?: number } | null;
  const zk = (o as { zk?: { nargo?: string; bb?: string; runtime_bytes?: Record<string, number> } | null }).zk;
  const demo = o.demo;
  const contracts = (demo as { contracts?: Record<string, { address: string; url?: string }> } | null)?.contracts;
  const proofBytes = metric(demo, "prove", "proof_bytes");
  const emInputs = metric(demo, "prove_emissions", "public_inputs");

  return (
    <Page className="space-y-12 sm:space-y-16">
      <PageHeader path="/method" />

      <section
        id="limits"
        aria-labelledby="limits-h"
        className="scroll-mt-24 rounded-xl border border-warning/40 bg-warning-subtle p-6 sm:p-8"
      >
        <h2 id="limits-h" className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <AlertTriangle className="size-5 text-warning" aria-hidden />
          What this does not claim
        </h2>
        <ul className="mt-5 space-y-3">
          {LIMITS.map((l) => (
            <li key={l} className="flex gap-3 text-sm leading-relaxed text-pretty sm:text-base">
              <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
              <span>{l}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {ds && (
          <Card icon={Database} id="data-h" title="Data" scope={FULL_YEAR}>
            <Facts
              rows={[
                [
                  "Source",
                  <a
                    href={DATA_SOURCE_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 underline underline-offset-4"
                  >
                    {String(ds.source ?? "Energi Data Service")}
                    <ExternalLink className="size-3" aria-hidden />
                  </a>,
                ],
                ["Datasets", (ds.datasets ?? []).join(", ")],
                ["Period", `${String(ds.first)} to ${String(ds.last)} UTC (${int(Number(ds.hours))} hours)`],
                [
                  "Buyer",
                  buyer ? (
                    <>
                      <SectorName sector={buyer} /> (Energinet branch {buyer.code})
                    </>
                  ) : (
                    `${String(ds.buyer_label)} (Energinet branch ${String(ds.buyer_branch)})`
                  ),
                ],
                ["Annual load", `${int(Number(ds.annual_load_mwh))} MWh`],
                ["Declaration version", String(ds.declaration_version)],
                ["Synthetic data", ds.synthetic ? "Yes" : "No: every hour is published Energinet data"],
                ["Note on sources", String(ds.note_on_sources ?? "")],
              ]}
            />
          </Card>
        )}

        <Card icon={SlidersHorizontal} id="params-h" title="Scenario parameters" scope={PARAMS}>
          <p className="mb-2 text-sm text-muted-foreground">
            Scenario parameters, declared up front and frozen before the test period. Everything else is measured data.
          </p>
          <Facts
            rows={[
              ...(bt?.params
                ? ([
                    [
                      <>
                        <Term id="flexible-load">Flexible load</Term> share (agent)
                      </>,
                      `${pct(bt.params.flex_share!, 0)} of each hour's load`,
                    ],
                    ["Hourly cap on moved load (agent)", `+${pct(bt.params.flex_cap!, 0)}`],
                    ["Extra certificate budget (agent)", `${pct(bt.params.topup_share!, 0)} of load`],
                  ] as [ReactNode, ReactNode][])
                : []),
              ...(c.available
                ? ([
                    ["Flexible share (carbon-aware)", `${pct(c.frozen_config.flex_share, 0)} of each hour's load`],
                    ["Hourly cap on moved load (carbon-aware)", `+${pct(c.frozen_config.flex_cap, 0)}`],
                  ] as [ReactNode, ReactNode][])
                : []),
            ]}
          />
        </Card>

        <Card icon={KeyRound} id="crypto-h" title="Cryptography" scope={THIS_RUN}>
          <Facts
            rows={[
              [
                <>Certificate signatures</>,
                <>
                  <Term id="ml-dsa">ML-DSA-44</Term>, one signature per daily batch, verified on-chain by a Solidity
                  verifier (unaudited research code).
                </>,
              ],
              [
                "Zero-knowledge proofs",
                <>
                  <Term id="ultrahonk">UltraHonk</Term>, circuits in Noir
                  {zk?.nargo ? ` (${zk.nargo.replace("nargo version = ", "nargo ")})` : ""}
                  {zk?.bb ? `, proved with bb ${zk.bb}` : ""}. Not post-quantum.
                </>,
              ],
              ...(zk?.runtime_bytes
                ? ([
                    [
                      "Coverage verifier contract",
                      `${int(zk.runtime_bytes["HonkVerifier.sol:HonkVerifier"] ?? 0)} bytes`,
                    ],
                    [
                      "Emissions verifier contract",
                      `${int(zk.runtime_bytes["EmissionsHonkVerifier.sol:EmissionsHonkVerifier"] ?? 0)} bytes`,
                    ],
                  ] as [ReactNode, ReactNode][])
                : []),
              ...(proofBytes != null ? ([["Proof size", `${int(proofBytes)} bytes`]] as [ReactNode, ReactNode][]) : []),
              ...(emInputs != null
                ? ([["Public inputs of the emissions proof", `${int(emInputs)}, rebuilt by the contract`]] as [
                    ReactNode,
                    ReactNode,
                  ][])
                : []),
              [
                "What stays private",
                <>
                  The buyer's hourly load. Only a <Term id="commitment">commitment</Term> to it is published.
                </>,
              ],
            ]}
          />
        </Card>

        {contracts && (
          <Card icon={BookOpen} id="contracts-h" title="Contracts of this run" scope={THIS_RUN}>
            <ul className="divide-y divide-border">
              {Object.entries(contracts).map(([name, k]) => (
                <li key={name} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0 truncate">{name}</span>
                  {k.url ? (
                    <a
                      href={k.url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`${name} contract ${k.address} on the block explorer (opens in a new tab)`}
                      className="inline-flex shrink-0 items-center gap-1 font-mono text-xs underline-offset-4 hover:underline"
                    >
                      {shortHash(k.address, 4, 4)}
                      <ExternalLink className="size-3 text-subtle-foreground" aria-hidden />
                    </a>
                  ) : (
                    <span className="font-mono text-xs">{shortHash(k.address, 4, 4)}</span>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <section id="glossary" aria-labelledby="glossary-h" className="scroll-mt-24 space-y-5">
        <SectionHeading
          id="glossary-h"
          title="Glossary"
          sub="The terms underlined on these pages, in plain words. Tap or hover an underlined word anywhere to see its definition."
        />
        <dl data-definitions className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          {Object.entries(GLOSSARY).map(([id, g]) => (
            <div key={id}>
              <dt className="text-sm font-semibold">{g.term}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">{g.definition}</dd>
            </div>
          ))}
        </dl>
      </section>
    </Page>
  );
}
