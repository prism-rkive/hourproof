/** Pure functions from API data to what the UI shows. Every displayed figure is derived here, and tested. */
import { networkName, utcDateTime } from "./format";
import type { Overview } from "./schemas";

export type Tone = "success" | "warning" | "danger" | "neutral";

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
