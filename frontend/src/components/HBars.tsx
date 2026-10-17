import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type HBarRow = {
  key: string;
  label: ReactNode;
  value: number; // bar length, relative to `max`
  display: string; // the figure as written
  extra?: ReactNode; // a second, smaller figure (e.g. the difference to a baseline)
  emphasis?: boolean; // the strategy the page is about
  reference?: boolean; // an unreachable reference (perfect foresight / actual intensity): hatched, labelled
  badge?: boolean; // show the "Reference" badge (off when the label already says so)
};

/**
 * Horizontal bars from a zero baseline (never truncated, so lengths compare honestly). A reference row is hatched
 * and labelled, never only coloured differently.
 */
export function HBars({ rows, max, label }: { rows: HBarRow[]; max: number; label: string }) {
  return (
    <ul aria-label={label} className="space-y-3">
      {rows.map((r) => (
        <li
          key={r.key}
          className="grid gap-1.5 sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_6.5rem] sm:items-center sm:gap-4"
        >
          <span className={cn("text-13", r.emphasis ? "font-medium text-foreground" : "text-muted-foreground")}>
            {r.label}
            {r.reference && r.badge !== false && (
              <span className="ml-1.5 rounded border border-border px-1 py-px text-[10px] tracking-wide text-subtle-foreground uppercase">
                Reference
              </span>
            )}
          </span>
          <span className="flex items-center gap-3 sm:contents">
            <span className="h-3 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
              <span
                className={cn(
                  "block h-full rounded-full",
                  r.reference ? "hatch border border-brand/60" : r.emphasis ? "bg-brand" : "bg-brand/45",
                )}
                style={{ width: `${Math.max(0, Math.min(100, (100 * r.value) / max)).toFixed(2)}%` }}
              />
            </span>
            <span className="tabular shrink-0 text-right text-sm font-medium sm:text-base">
              {r.display}
              {r.extra && <span className="block text-xs font-normal text-subtle-foreground">{r.extra}</span>}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
