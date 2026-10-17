import { useRef, useState, type KeyboardEvent } from "react";
import { dayLabel, int, pct } from "@/lib/format";
import type { HourCell } from "@/lib/selectors";
import { cn } from "@/lib/utils";

const HOURS = 24;

/**
 * One week as 7 rows x 24 hours. Each square fills from the bottom with the share of that hour's use covered by
 * certificates; the uncovered part is hatched, so the reading never depends on colour alone. Keyboard: one tab stop,
 * arrow keys move between hours (ARIA grid). The hovered or focused hour is spelled out below the grid.
 */
export function WeekHeatmap({ cells, label }: { cells: HourCell[]; label: string }) {
  const days = Array.from({ length: Math.floor(cells.length / HOURS) }, (_, d) =>
    cells.slice(d * HOURS, (d + 1) * HOURS),
  );
  const [focusIdx, setFocusIdx] = useState(0);
  const [shown, setShown] = useState<HourCell | null>(null);
  const refs = useRef<(HTMLDivElement | null)[]>([]);

  const move = (to: number) => {
    const i = Math.max(0, Math.min(cells.length - 1, to));
    setFocusIdx(i);
    refs.current[i]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent) => {
    const i = focusIdx;
    const keys: Record<string, number> = {
      ArrowRight: i + 1,
      ArrowLeft: i - 1,
      ArrowDown: i + HOURS,
      ArrowUp: i - HOURS,
      Home: i - (i % HOURS),
      End: i - (i % HOURS) + HOURS - 1,
    };
    if (e.key in keys) {
      e.preventDefault();
      move(keys[e.key]!);
    }
  };

  return (
    <div>
      <div role="grid" aria-label={label} onKeyDown={onKeyDown} className="flex flex-col gap-[2px] sm:gap-[3px]">
        <div
          role="row"
          className="grid grid-cols-[2.75rem_repeat(24,minmax(0,1fr))] gap-[2px] sm:grid-cols-[5.25rem_repeat(24,minmax(0,1fr))] sm:gap-[3px]"
        >
          <span role="columnheader" aria-label="Day" />
          {Array.from({ length: HOURS }, (_, h) => (
            <span
              key={h}
              role="columnheader"
              aria-label={`${String(h).padStart(2, "0")}:00 UTC`}
              className="text-center font-mono text-[10px] leading-4 text-subtle-foreground sm:text-[11px]"
            >
              <span aria-hidden className={cn(h % 6 !== 0 && "invisible", h % 3 === 0 ? "sm:visible" : "sm:invisible")}>
                {String(h).padStart(2, "0")}
              </span>
            </span>
          ))}
        </div>
        {days.map((row, d) => (
          <div
            role="row"
            key={d}
            className="grid grid-cols-[2.75rem_repeat(24,minmax(0,1fr))] items-center gap-[2px] sm:grid-cols-[5.25rem_repeat(24,minmax(0,1fr))] sm:gap-[3px]"
          >
            <span role="rowheader" className="truncate pr-1 text-[11px] text-muted-foreground sm:text-xs">
              <span className="sm:hidden">{dayLabel(row[0]!.hour, true)}</span>
              <span className="hidden sm:inline">{dayLabel(row[0]!.hour)}</span>
            </span>
            {row.map((c) => (
              <div
                role="gridcell"
                key={c.i}
                ref={(el) => {
                  refs.current[c.i] = el;
                }}
                tabIndex={c.i === focusIdx ? 0 : -1}
                aria-label={c.label}
                onFocus={() => {
                  setFocusIdx(c.i);
                  setShown(c);
                }}
                onMouseEnter={() => setShown(c)}
                onMouseLeave={() => setShown(null)}
                onBlur={() => setShown(null)}
                className="hatch relative aspect-square overflow-hidden rounded-[2px] outline-offset-1 focus-visible:z-10 sm:rounded-[3px]"
              >
                <div
                  className="absolute inset-x-0 bottom-0 bg-brand"
                  style={{ height: `${(100 * c.share).toFixed(1)}%` }}
                />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p aria-live="polite" className="tabular min-h-5 text-13 text-muted-foreground">
          {shown ? (
            <>
              <span className="font-medium text-foreground">
                {dayLabel(shown.hour)}, {shown.hour.slice(11, 16)} UTC
              </span>
              {" · "}
              {int(Math.min(shown.cert, shown.load))} of {int(shown.load)} MWh covered ({pct(shown.share, 0)})
            </>
          ) : (
            "Hover over or focus an hour to see its numbers."
          )}
        </p>
        <div className="flex items-center gap-4 text-xs text-muted-foreground" aria-hidden>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-[3px] bg-brand" /> Covered by certificates
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="hatch size-3 rounded-[3px]" /> Not covered
          </span>
        </div>
      </div>
    </div>
  );
}
