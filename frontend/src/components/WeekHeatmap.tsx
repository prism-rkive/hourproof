import { dateLabel, int, pct } from "@/lib/format";
import type { HourCell } from "@/lib/selectors";
import { HourGrid } from "./HourGrid";

/**
 * Hourly coverage for one week. Each square fills from the bottom with the share of that hour's use covered by
 * certificates; the uncovered part is hatched, so the reading never depends on colour alone.
 */
export function WeekHeatmap({ cells, label }: { cells: HourCell[]; label: string }) {
  return (
    <HourGrid
      cells={cells}
      label={label}
      cellClassName={() => "hatch"}
      renderCell={(c) => (
        <div className="absolute inset-x-0 bottom-0 bg-brand" style={{ height: `${(100 * c.share).toFixed(1)}%` }} />
      )}
      idle="Hover over or focus an hour to see its numbers."
      readout={(c) => (
        <>
          <span className="font-medium text-foreground">
            {dateLabel(c.hour)}, {c.hour.slice(11, 16)} UTC
          </span>
          {" · "}
          {int(Math.min(c.cert, c.load))} of {int(c.load)} MWh covered ({pct(c.share, 0)})
        </>
      )}
      legend={
        <>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-[3px] bg-brand" /> Covered by certificates
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="hatch size-3 rounded-[3px]" /> Not covered
          </span>
        </>
      }
    />
  );
}
