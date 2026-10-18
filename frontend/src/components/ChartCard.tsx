import { Table2 } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { ScopeTag } from "./ScopeTag";

/**
 * A titled panel for a chart: what it shows in one sentence, the chart, an optional "View as table" with the same
 * numbers (for screen readers and for anyone who prefers to read values), and a source line.
 */
export function ChartCard({
  title,
  description,
  children,
  table,
  source,
  actions,
  footer,
  scope,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  table?: ReactNode;
  source?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  scope?: string; // the period every figure in this card covers
  className?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();
  return (
    <section
      data-scope={scope}
      className={cn("flex flex-col rounded-xl border border-border bg-card shadow-xs", className)}
    >
      <div className="flex flex-col gap-4 p-5 pb-0 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-2xl space-y-1.5">
          {scope && <ScopeTag scope={scope} />}
          <h3 className="text-base font-semibold tracking-tight">{title}</h3>
          {description && <p className="text-sm text-pretty text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
      <div className="flex-1 p-5">{children}</div>
      {footer && <div className="px-5 pb-5">{footer}</div>}
      {(table || source) && (
        <div className="flex flex-col gap-3 border-t border-border px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            {source && <p className="text-xs text-subtle-foreground">{source}</p>}
            {table && (
              <button
                type="button"
                onClick={() => setShowTable((v) => !v)}
                aria-expanded={showTable}
                aria-controls={tableId}
                className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <Table2 className="size-3.5" aria-hidden />
                {showTable ? "Hide table" : "View as table"}
              </button>
            )}
          </div>
          {table && (
            <div id={tableId} hidden={!showTable}>
              {showTable && table /* rendered on demand: keeps the page light to load and hydrate */}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/** A compact, scrollable data table used inside ChartCard. */
export function DataTable({
  caption,
  head,
  rows,
  className,
}: {
  caption: string;
  head: string[];
  rows: (string | number)[][];
  className?: string;
}) {
  return (
    <div className={cn("max-h-80 overflow-auto rounded-md border border-border", className)}>
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-muted text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border">
              {r.map((c, j) =>
                j === 0 ? (
                  <th key={j} scope="row" className="px-3 py-1.5 font-normal whitespace-nowrap text-muted-foreground">
                    {c}
                  </th>
                ) : (
                  <td key={j} className="px-3 py-1.5 whitespace-nowrap">
                    {c}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
