import {
  ChevronDown,
  ChevronsDownUp,
  ChevronsUpDown,
  Download,
  ExternalLink,
  Lightbulb,
  Play,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLoaderData, useRevalidator } from "react-router";
import { CopyButton } from "@/components/CopyButton";
import { Hydrate } from "@/components/Hydrate";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScopeTag } from "@/components/ScopeTag";
import { SectionHeading } from "@/components/SectionHeading";
import { StatusBadge, stepTone } from "@/components/StatusBadge";
import { Term } from "@/components/Term";
import { TxList } from "@/components/TxList";
import { Button } from "@/components/ui/button";
import { getLog, getOverview, startRun } from "@/lib/api";
import { duration, int, networkName, seconds, THIS_RUN, utcDateTime } from "@/lib/format";
import type { DemoState, Overview, RunLog, Step } from "@/lib/schemas";
import { REPO_URL } from "@/routes";
import { cn } from "@/lib/utils";

export async function loader() {
  const [overview, log] = await Promise.all([getOverview(), getLog().catch(() => null)]);
  return { overview, log };
}

/** What each step does, for a reader new to the field. Shown inside the step, under its title. */
const STEP_PLAIN: Record<string, string> = {
  preflight:
    "Checks the chain and the proof tooling, and tops up the demo wallets with test ETH so each role can pay for its transactions.",
  deploy:
    "Puts the contracts on the chain and connects them: who may post data, who may issue certificates, which contract verifies proofs.",
  agent_commit:
    "The AI agent publishes a fingerprint of each day's plan, so it cannot quietly change a plan after seeing what happened.",
  oracle: "Energinet's published hourly production for the week goes on-chain. No certificate can exceed it.",
  intensity: "The grid's hourly CO₂ intensity for the week goes on-chain. A posted value cannot be changed.",
  issue:
    "The issuer creates one certificate per hour and signs each day's batch with a post-quantum signature that the contract checks.",
  claim:
    "The buyer opens its claim for the week and cancels the certificates into it, so they can never be used again.",
  attacks_supply: "Three attempts to create or reuse certificates illegitimately. Each one must be refused.",
  attest:
    "The metering data hub publishes a commitment to the buyer's hourly load. The load itself never goes on-chain.",
  prove:
    "The buyer proves in zero knowledge that its hourly coverage is at least the target, and the contract verifies the proof.",
  attacks_proof: "The buyer tries to claim more coverage than it has. The prover and the contract must refuse.",
  prove_emissions:
    "The buyer proves an upper bound on its residual emissions from the posted intensities and the same commitment.",
  attacks_emissions: "Attempts to understate emissions or to prove on cleaner, fake intensities. Each must be refused.",
  note: "The sustainability-linked note settles: the proven emissions, against its target, set the coupon.",
  agent_reveal:
    "The agent reveals its plans, and the contract checks each one against the fingerprint published earlier.",
  verify:
    "An independent check re-reads every receipt and contract from the chain and re-verifies both proofs from the transactions.",
};

const ATTACK_STEPS = new Set(["attacks_supply", "attacks_proof", "attacks_emissions"]);

/* ------------------------------------------------------------------------------------------------ run buttons */

function RunButtons({ o, onStarted }: { o: Overview; onStarted: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hosted = !!o.static_snapshot;
  const disabled = hosted || busy || o.running;
  const why = hosted
    ? "Static snapshot: run it yourself with make demo (local chain) or make demo-base (Base Sepolia)"
    : o.running
      ? "A run is already in progress"
      : undefined;
  const run = async (network: "local" | "base-sepolia") => {
    setBusy(true);
    setError(null);
    try {
      const err = await startRun(network);
      if (err) setError(err);
      else onStarted();
    } finally {
      setTimeout(() => setBusy(false), 1500);
    }
  };
  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <div className="flex flex-wrap gap-2">
        <Button variant="brand" disabled={disabled} title={why} onClick={() => run("local")}>
          <Play aria-hidden /> Run on local chain
        </Button>
        <Button variant="outline" disabled={disabled} title={why} onClick={() => run("base-sepolia")}>
          Run on Base Sepolia
        </Button>
      </div>
      {hosted && (
        <p className="max-w-xs text-xs text-subtle-foreground sm:text-right">Runs start only on a local server.</p>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ summary */

function Stat({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="tabular text-base font-semibold">{children}</dd>
    </div>
  );
}

function RunSummary({ demo, o }: { demo: DemoState; o: Overview }) {
  const s = (demo.summary ?? {}) as Record<string, unknown>;
  const n = (k: string) => (typeof s[k] === "number" ? (s[k] as number) : undefined);
  const t = stepTone(demo.status);
  const seconds =
    demo.started_utc && demo.finished_utc
      ? (new Date(demo.finished_utc).getTime() - new Date(demo.started_utc).getTime()) / 1000
      : undefined;
  return (
    <section
      data-scope={THIS_RUN}
      aria-labelledby="run-h"
      className="rounded-xl border border-border bg-card p-5 shadow-xs sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 id="run-h" className="truncate font-mono text-sm font-medium">
            Run {demo.run_id}
          </h2>
          <CopyButton value={demo.run_id} label="Copy the run ID" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ScopeTag scope={THIS_RUN} />
          <StatusBadge tone={t.tone}>{demo.status === "done" ? "Passed" : t.label}</StatusBadge>
          {demo.zk_mode === "mock" ? (
            <StatusBadge tone="warning">MOCK verifier (test mode, not a real proof)</StatusBadge>
          ) : (
            <StatusBadge tone="neutral" icon="shield">
              Real proofs
            </StatusBadge>
          )}
        </div>
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Network">
          {demo.network === "base-sepolia" ? (
            <Term id="base-sepolia">{networkName(demo.network)}</Term>
          ) : (
            networkName(demo.network)
          )}
        </Stat>
        <Stat label={<Term id="transaction">Transactions</Term>}>
          {n("transactions") != null ? int(n("transactions")!) : "—"}
        </Stat>
        <Stat label={<Term id="gas">Gas used</Term>}>{n("gas_total") != null ? int(n("gas_total")!) : "—"}</Stat>
        <Stat label="Independent checks">{n("verified_checks") != null ? `${n("verified_checks")} passed` : "—"}</Stat>
        <Stat label={<Term id="attack-test">Attacks refused</Term>}>
          {n("attacks_blocked") != null && n("attacks_total") != null
            ? `${n("attacks_blocked")} of ${n("attacks_total")}`
            : "—"}
        </Stat>
        <Stat label="Duration">{seconds != null ? duration(seconds) : "—"}</Stat>
      </dl>
      {demo.started_utc && (
        <p className="mt-5 text-xs text-subtle-foreground">
          Started {utcDateTime(demo.started_utc)}
          {demo.finished_utc && <>, finished {utcDateTime(demo.finished_utc)}</>}.
        </p>
      )}
      {o.static_snapshot && (
        <div className="mt-5 flex gap-3 rounded-lg border border-success/30 bg-success-subtle px-4 py-3 text-sm">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          <p className="text-pretty text-muted-foreground">
            <span className="font-medium text-foreground">Static snapshot of this verified run</span> (
            {o.static_snapshot.verification}). Every transaction links to its block explorer. The files that prove it
            are in the{" "}
            <a
              href={`${REPO_URL}/tree/main/${o.static_snapshot.evidence}`}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-foreground underline underline-offset-4"
            >
              evidence bundle
            </a>
            . To run the scenario yourself: <code className="font-mono text-xs">make demo</code> (local chain) or{" "}
            <code className="font-mono text-xs">make demo-base</code> (Base Sepolia).
          </p>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ steps */

function VerifyChecks({ step }: { step: Step }) {
  const checks = Array.isArray(step.metrics.checks)
    ? (step.metrics.checks as { check: string; detail?: string; ok: boolean }[])
    : [];
  if (!checks.length) return null;
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2">
      {checks.map((c) => (
        <li key={c.check} className="flex gap-2 rounded-md bg-muted px-3 py-2 text-13">
          <StatusBadge tone={c.ok ? "success" : "danger"} className="h-fit">
            {c.ok ? "Pass" : "Fail"}
          </StatusBadge>
          <span className="min-w-0">
            {c.check}
            {c.detail && <span className="block font-mono text-xs break-all text-subtle-foreground">{c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function StepCard({ step, index, open, onToggle }: { step: Step; index: number; open: boolean; onToggle: () => void }) {
  const t = stepTone(step.status);
  const isVerify = step.id === "verify";
  const bodyId = `step-${step.id}`;
  return (
    <li
      className={cn(
        "rounded-xl border bg-card shadow-xs",
        isVerify ? "border-brand/50 ring-1 ring-brand/20" : "border-border",
      )}
    >
      <h3>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={bodyId}
          className="flex w-full items-start gap-3 rounded-xl px-4 py-3.5 text-left hover:bg-accent/40 sm:items-center sm:px-5"
        >
          <span
            className={cn(
              "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs sm:mt-0",
              step.status === "done" ? "bg-brand-subtle text-brand" : "bg-muted text-muted-foreground",
            )}
            aria-hidden
          >
            {index + 1}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium text-pretty">{step.title}</span>
            <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-subtle-foreground sm:hidden">
              <StatusBadge tone={t.tone}>{t.label}</StatusBadge>
              {step.seconds != null && <span className="tabular">{seconds(step.seconds)}</span>}
              {step.txs.length > 0 && <span>{step.txs.length} tx</span>}
            </span>
          </span>
          <span className="hidden shrink-0 items-center gap-3 text-xs text-subtle-foreground sm:flex">
            {step.txs.length > 0 && (
              <span className="tabular">
                {step.txs.length} {step.txs.length === 1 ? "transaction" : "transactions"}
              </span>
            )}
            {step.seconds != null && <span className="tabular w-16 text-right">{seconds(step.seconds)}</span>}
            <StatusBadge tone={t.tone}>{t.label}</StatusBadge>
          </span>
          <ChevronDown
            className={cn(
              "mt-0.5 size-4 shrink-0 text-subtle-foreground transition-transform sm:mt-0",
              open && "rotate-180",
            )}
            aria-hidden
          />
        </button>
      </h3>
      <div id={bodyId} hidden={!open} className="space-y-4 border-t border-border px-4 py-4 sm:px-5">
        {open && <StepBody step={step} isVerify={isVerify} />}
      </div>
    </li>
  );
}

/** A step's content, rendered when the step is opened (keeps the page light to load and hydrate). */
function StepBody({ step, isVerify }: { step: Step; isVerify: boolean }) {
  return (
    <>
      {STEP_PLAIN[step.id] && (
        <p className="flex gap-2 text-sm text-muted-foreground">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
          <span>{STEP_PLAIN[step.id]}</span>
        </p>
      )}
      {step.detail && (
        <p className="rounded-md bg-muted px-3 py-2 font-mono text-xs leading-relaxed break-words">{step.detail}</p>
      )}
      {isVerify && <VerifyChecks step={step} />}
      {ATTACK_STEPS.has(step.id) && (
        <Link to="/security" className="inline-flex text-13 font-medium underline-offset-4 hover:underline">
          Each attack, what refused it, and why →
        </Link>
      )}
      <TxList txs={step.txs} />
    </>
  );
}

function Steps({ demo }: { demo: DemoState }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(demo.steps[0] ? [demo.steps[0].id] : []));
  const all = open.size === demo.steps.length;
  const txCount = demo.steps.reduce((n, s) => n + s.txs.length, 0);
  return (
    <section data-scope={THIS_RUN} aria-labelledby="steps-h" className="space-y-5">
      <SectionHeading
        id="steps-h"
        scope={THIS_RUN}
        title="Every step"
        sub={
          <>
            {demo.steps.length} steps and {txCount} <Term id="transaction">transactions</Term>, in order. Open a step to
            see what it did and its transactions on the block explorer. The last step re-checks everything from the
            chain.
          </>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => setOpen(all ? new Set() : new Set(demo.steps.map((s) => s.id)))}
          >
            {all ? <ChevronsDownUp aria-hidden /> : <ChevronsUpDown aria-hidden />}
            {all ? "Collapse all" : "Expand all"}
          </Button>
        }
      />
      <ol className="space-y-2.5">
        {demo.steps.map((s, i) => (
          <StepCard
            key={s.id}
            step={s}
            index={i}
            open={open.has(s.id)}
            onToggle={() =>
              setOpen((prev) => {
                const next = new Set(prev);
                if (next.has(s.id)) next.delete(s.id);
                else next.add(s.id);
                return next;
              })
            }
          />
        ))}
      </ol>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ log */

function LogPanel({ log, runId }: { log: RunLog | null; runId?: string }) {
  const pre = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (log?.running && pre.current) pre.current.scrollTop = pre.current.scrollHeight;
  }, [log]);
  if (!log) return null;
  const title = log.recorded ? `Recorded log of run ${log.run_id ?? runId}` : "Run log";
  const download = () => {
    const url = URL.createObjectURL(new Blob([log.log], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `hourproof-${log.run_id ?? "run"}.log`,
    });
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section data-scope={THIS_RUN} aria-labelledby="log-h" className="space-y-4">
      <SectionHeading
        id="log-h"
        scope={THIS_RUN}
        title={title}
        sub={
          log.recorded
            ? "The run's console output, exactly as printed, from the command to its exit status. It was scanned for secrets before it was published."
            : log.running
              ? "Live output of the run in progress."
              : "Output of the last run started from this server."
        }
        actions={
          log.log ? (
            <>
              <CopyButton value={log.log} label="Copy the log" className="size-9 border border-border" />
              <Button variant="outline" size="sm" onClick={download}>
                <Download aria-hidden /> Download
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="overflow-hidden rounded-xl border border-border bg-background-subtle">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2 text-xs text-subtle-foreground">
          <TerminalSquare className="size-3.5" aria-hidden />
          {log.source ?? "console"}
        </div>
        <pre
          ref={pre}
          tabIndex={0}
          aria-label={title}
          className="max-h-[32rem] overflow-auto p-4 font-mono text-xs leading-relaxed whitespace-pre text-foreground"
        >
          {log.log || "No run has been started from this server yet."}
        </pre>
      </div>
      {log.source && (
        <a
          href={`${REPO_URL}/blob/main/${log.source}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-13 text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          The same file in the repository <ExternalLink className="size-3" aria-hidden />
        </a>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ page */

export function Component() {
  const { overview: o, log: initialLog } = useLoaderData() as { overview: Overview; log: RunLog | null };
  const [log, setLog] = useState(initialLog);
  const [polling, setPolling] = useState(o.running && !o.static_snapshot);
  const revalidator = useRevalidator();
  useEffect(() => setLog(initialLog), [initialLog]);
  useEffect(() => {
    // While a local run is in progress: refresh the log and the run state, like the original dashboard.
    if (!polling) return;
    const t = setInterval(async () => {
      const l = await getLog(true).catch(() => null);
      if (l) setLog(l);
      const fresh = await getOverview(true).catch(() => null);
      revalidator.revalidate();
      if (l && !l.running && fresh && !fresh.running) setPolling(false);
    }, 2000);
    return () => clearInterval(t);
  }, [polling, revalidator]);

  const demo = o.demo;
  return (
    <Page className="space-y-12 sm:space-y-16">
      <PageHeader path="/proof" actions={<RunButtons o={o} onStarted={() => setPolling(true)} />} />
      {demo ? (
        <>
          <RunSummary demo={demo} o={o} />
          <Hydrate>
            <Steps demo={demo} />
          </Hydrate>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">No run yet. Start one on a local server with the buttons above.</p>
      )}
      <Hydrate>
        <LogPanel log={log} runId={demo?.run_id} />
      </Hydrate>
    </Page>
  );
}
