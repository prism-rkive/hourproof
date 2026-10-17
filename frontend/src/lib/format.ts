/**
 * Presentation-only formatting. Never changes a value, only how it is written. The rules match the original
 * dashboard (web/app.js) so every figure reads the same: percentages with one decimal, basis points as a percentage
 * with two, tonnes with at most one decimal, MWh and gas as rounded integers with thousands separators.
 */

const NETWORK_NAMES: Record<string, string> = {
  "base-sepolia": "Base Sepolia",
  local: "local chain",
};

export function networkName(id: string): string {
  return NETWORK_NAMES[id] ?? id;
}

/** 0.6971 -> "69.7%" (web/app.js pct). */
export function pct(x: number, digits = 1): string {
  return `${(100 * x).toFixed(digits)}%`;
}

/** Like pct, but drops a trailing ".0": 1 -> "100%", 0.6971 -> "69.7%". For headline figures. */
export function pctShort(x: number): string {
  return `${(100 * x).toLocaleString("en-GB", { maximumFractionDigits: 1 })}%`;
}

/** 7500 -> "75.00%" (web/app.js bps). */
export function bps(b: number): string {
  return `${(b / 100).toFixed(2)}%`;
}

/** 546125 kg -> "546.1 t" (web/app.js note). */
export function tonnes(kg: number): string {
  return `${(kg / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} t`;
}

/** 114132609 -> "114,132,609" (web/app.js fmt). */
export function int(n: number): string {
  return Math.round(n).toLocaleString("en-GB");
}

/** "17 Oct 2026, 14:31 UTC" — always UTC, so every visitor sees the same time as the evidence files. */
export function utcDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  return `${date}, ${time} UTC`;
}

/** Dataset hour strings are UTC without a zone ("2025-11-10 00:00:00"). */
export function utcHour(hour: string): Date {
  return new Date(hour.replace(" ", "T") + "Z");
}

/** "Mon 10 Nov" / short "Mon 10" (UTC). */
export function dayLabel(hour: string, short = false): string {
  return utcHour(hour).toLocaleDateString(
    "en-GB",
    short
      ? { weekday: "short", day: "numeric", timeZone: "UTC" }
      : { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" },
  );
}

/** "Week of 10–16 Nov" (or "Week of 28 Nov – 4 Dec") for the 7 days starting at a dataset hour string, UTC. */
export function weekScope(startHour: string): string {
  const start = utcHour(startHour);
  const end = new Date(start.getTime() + 6 * 86_400_000);
  const d = (x: Date) => x.getUTCDate();
  const m = (x: Date) => x.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
  return m(start) === m(end)
    ? `Week of ${d(start)}–${d(end)} ${m(end)}`
    : `Week of ${d(start)} ${m(start)} – ${d(end)} ${m(end)}`;
}

export const FULL_YEAR = "Full year";

/** "Mon" (UTC). */
export function weekday(hour: string): string {
  return utcHour(hour).toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" });
}

/** "10 Nov 2025" (UTC). */
export function dayDate(hour: string): string {
  return utcHour(hour).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
