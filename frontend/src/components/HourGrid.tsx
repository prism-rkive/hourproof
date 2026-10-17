import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { dayLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

const HOURS = 24;

export type GridCell = { i: number; hour: string; label: string };

/**
 * One week as 7 rows x 24 hours (an ARIA grid: one tab stop, arrow keys, Home/End). What a square shows is up to
 * `renderCell`; the hovered or focused hour is spelled out by `readout` below the grid, so nothing depends on colour
 * or on hovering alone.
 */
export function HourGrid<C extends GridCell>({
  cells,
  label,
  renderCell,
  readout,
  idle,
  legend,
  cellClassName,
}: {
  cells: C[];
  label: string;
  renderCell: (c: C) => ReactNode;
  readout: (c: C) => ReactNode;
  idle: string;
  legend?: ReactNode;
  cellClassName?: (c: C) => string | undefined;
}) {
  const days = Array.from({ length: Math.floor(cells.length / HOURS) }, (_, d) =>
    cells.slice(d * HOURS, (d + 1) * HOURS),
  );
  const [focusIdx, setFocusIdx] = useState(0);
  const [shown, setShown] = useState<C | null>(null);
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
  const rowCls =
    "grid grid-cols-[2.75rem_repeat(24,minmax(0,1fr))] gap-[2px] sm:grid-cols-[5.25rem_repeat(24,minmax(0,1fr))] sm:gap-[3px]";

  return (
    <div>
      <div role="grid" aria-label={label} onKeyDown={onKeyDown} className="flex flex-col gap-[2px] sm:gap-[3px]">
        <div role="row" className={rowCls}>
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
          <div role="row" key={d} className={cn(rowCls, "items-center")}>
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
                className={cn(
                  "relative aspect-square overflow-hidden rounded-[2px] outline-offset-1 focus-visible:z-10 sm:rounded-[3px]",
                  cellClassName?.(c),
                )}
              >
                {renderCell(c)}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p aria-live="polite" className="tabular min-h-5 text-13 text-muted-foreground">
          {shown ? readout(shown) : idle}
        </p>
        {legend && (
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground" aria-hidden>
            {legend}
          </div>
        )}
      </div>
    </div>
  );
}
