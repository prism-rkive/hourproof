import { CalendarRange } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * What period a figure covers ("Full year", "Week of 10–16 Nov"). Every figure on a page sits inside an element with
 * `data-scope` that also shows this tag, so near-identical numbers are never read against the wrong period.
 */
export function ScopeTag({ scope, className }: { scope: string; className?: string }) {
  return (
    <span
      data-scope-tag
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap text-muted-foreground",
        className,
      )}
    >
      <CalendarRange className="size-3" aria-hidden />
      {scope}
    </span>
  );
}
