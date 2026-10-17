/** Presentation-only formatting. Never changes a value, only how it is written. */

const NETWORK_NAMES: Record<string, string> = {
  "base-sepolia": "Base Sepolia",
  local: "local chain",
};

export function networkName(id: string): string {
  return NETWORK_NAMES[id] ?? id;
}

/** "17 Oct 2026, 14:31 UTC" — always UTC, so every visitor sees the same time as the evidence files. */
export function utcDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  return `${date}, ${time} UTC`;
}
