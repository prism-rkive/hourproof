import { Cpu, FileCode2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useLoaderData } from "react-router";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScopeTag } from "@/components/ScopeTag";
import { StatusBadge } from "@/components/StatusBadge";
import { Term } from "@/components/Term";
import { TxList } from "@/components/TxList";
import { getOverview } from "@/lib/api";
import { THIS_RUN } from "@/lib/format";
import type { Attack, Overview, Tx } from "@/lib/schemas";
import { slimOverview, step } from "@/lib/selectors";

export async function loader() {
  return { overview: slimOverview(await getOverview(), { attacks: true, steps: ["attacks_supply"], txs: true }) };
}

/** What each attempt tries and why it fails, in plain words. */
const PLAIN: Record<string, string> = {
  double_claim:
    "A second registry tries to sell clean energy the buyer has already claimed for that hour. The shared ledger counts every hour's MWh once, so the sale is refused.",
  over_issuance:
    "An issuer tries to certify more clean energy than was produced in that hour. The contract compares it with the oracle's metered production.",
  forged_signature:
    "Someone signs a certificate batch with a different key, pretending to be the issuer. The contract checks the post-quantum signature against the issuer's registered key.",
  overclaim:
    "The buyer tries to prove a coverage just above its true value. A false statement has no valid proof, so the prover cannot produce one.",
  replay_higher:
    "The buyer reuses a valid proof but claims a higher coverage. The contract rebuilds the proof's public inputs itself, so the proof no longer matches.",
  residual_understated:
    "The buyer tries to prove emissions just below the truth. The prover cannot produce a proof of a false bound.",
  intensity_repost:
    "The oracle tries to replace an hour's posted grid intensity with a cleaner value. Posted values cannot be changed.",
  fake_intensity:
    "The buyer proves against its own, cleaner intensity data. The contract rebuilds the intensities from the oracle, so the proof fails.",
};

/** Set-up transactions that an attack builds on (legitimate on their own), by attack ID and step. */
const SETUP: Record<string, string> = { double_claim: "attacks_supply" };

type Row = {
  a: Attack;
  refused: boolean;
  where: "prover" | "contract";
  txNote: string;
  setup: Tx[];
};

function rows(o: Overview): Row[] {
  const demo = o.demo;
  return (demo?.attacks ?? []).map((a) => {
    const prover = a.observed === "ProverRefused";
    return {
      a,
      refused: a.status === "blocked",
      where: prover ? "prover" : "contract",
      txNote: prover ? "Refused by the prover · no transaction" : "Refused before broadcast · no transaction",
      setup: SETUP[a.id] ? (step(demo, SETUP[a.id]!)?.txs ?? []) : [],
    };
  });
}

function Where({ where }: { where: Row["where"] }) {
  return where === "prover" ? (
    <span className="inline-flex items-center gap-1.5 text-13">
      <Cpu className="size-3.5 text-subtle-foreground" aria-hidden /> The prover, locally
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-13">
      <FileCode2 className="size-3.5 text-subtle-foreground" aria-hidden /> A contract
    </span>
  );
}

function AttackCard({ r, index }: { r: Row; index: number }) {
  return (
    <li className="rounded-xl border border-border bg-card p-5 shadow-xs">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between lg:gap-8">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-subtle-foreground">
            <span className="font-mono">{String(index + 1).padStart(2, "0")}</span>
            <StatusBadge tone={r.refused ? "success" : "danger"}>
              {r.refused ? "Refused" : `Not refused (${r.a.status})`}
            </StatusBadge>
          </div>
          <h3 className="mt-2 text-base font-medium text-pretty">{r.a.title}</h3>
          {PLAIN[r.a.id] && <p className="mt-1.5 text-sm text-pretty text-muted-foreground">{PLAIN[r.a.id]}</p>}
          {r.a.note && (
            <p className="mt-2 rounded-md bg-muted px-3 py-2 font-mono text-xs leading-relaxed break-words">
              <span className="font-sans text-muted-foreground">Recorded by the run: </span>
              {r.a.note}
            </p>
          )}
        </div>
        <dl className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-3 text-13 sm:grid-cols-3 lg:w-[26rem] lg:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">Expected</dt>
            <dd className="mt-0.5 font-mono text-xs break-all">{r.a.expected ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Observed</dt>
            <dd className="mt-0.5 font-mono text-xs break-all">{r.a.observed ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Refused by</dt>
            <dd className="mt-0.5">
              <Where where={r.where} />
            </dd>
          </div>
          <div className="col-span-2 sm:col-span-3 lg:col-span-2">
            <dt className="text-xs text-muted-foreground">
              <Term id="transaction">Transaction</Term>
            </dt>
            <dd className="mt-0.5 text-13">{r.txNote}</dd>
          </div>
        </dl>
      </div>
      {r.setup.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs text-muted-foreground">
            Set-up transaction (legitimate on its own; the attack is the re-sale after it):
          </p>
          <TxList txs={r.setup} />
        </div>
      )}
    </li>
  );
}

export function Component() {
  const { overview: o } = useLoaderData() as { overview: Overview };
  const all = useMemo(() => rows(o), [o]);
  const [q, setQ] = useState("");
  const shown = all.filter((r) =>
    `${r.a.title} ${r.a.expected ?? ""} ${r.a.observed ?? ""} ${PLAIN[r.a.id] ?? ""}`
      .toLowerCase()
      .includes(q.trim().toLowerCase()),
  );
  const refused = all.filter((r) => r.refused).length;
  const byProver = all.filter((r) => r.refused && r.where === "prover").length;
  const byContract = refused - byProver;

  return (
    <Page className="space-y-12 sm:space-y-14">
      <PageHeader path="/security" />
      {all.length === 0 ? (
        <p className="text-sm text-muted-foreground">No attacks recorded yet. Run the scenario to see them refused.</p>
      ) : (
        <section
          data-scope={THIS_RUN}
          aria-labelledby="sum-h"
          className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]"
        >
          <div className="rounded-xl border border-success/40 bg-success-subtle p-6">
            <ScopeTag scope={THIS_RUN} />
            <h2 id="sum-h" className="mt-3 text-3xl font-semibold tracking-tight">
              {refused} of {all.length} refused
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {byContract} by a contract, {byProver} by the prover. The run fails if any attempt gets through.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6 shadow-xs">
            <h2 className="text-sm font-semibold">Why most attacks have no transaction</h2>
            <p className="mt-2 text-sm leading-relaxed text-pretty text-muted-foreground">
              Before a transaction is sent, its <Term id="gas">gas</Term> is estimated by simulating it. An attack that
              the contract rejects already fails in that simulation, with the contract's own error, so it is never
              broadcast. Attacks on the proofs fail even earlier: the prover cannot build a proof of a false statement.
              The run then checks on-chain that nothing changed.
            </p>
          </div>
        </section>
      )}

      {all.length > 0 && (
        <section data-scope={THIS_RUN} aria-labelledby="list-h" className="space-y-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <ScopeTag scope={THIS_RUN} className="mb-2" />
              <h2 id="list-h" className="text-2xl font-semibold tracking-tight">
                Every attempt
              </h2>
            </div>
            <label className="relative block w-full sm:w-72">
              <span className="sr-only">Search the attacks</span>
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground"
                aria-hidden
              />
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search, e.g. signature, proof"
                className="h-9 w-full rounded-md border border-input bg-background pr-3 pl-9 text-sm placeholder:text-subtle-foreground focus-visible:outline-2 focus-visible:outline-ring"
              />
            </label>
          </div>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {q
              ? `${shown.length} of ${all.length} attempts match.`
              : `${all.length} attempts, in the order the run made them.`}
          </p>
          <ol className="space-y-3">
            {shown.map((r) => (
              <AttackCard key={r.a.id} r={r} index={all.indexOf(r)} />
            ))}
          </ol>
        </section>
      )}
    </Page>
  );
}
