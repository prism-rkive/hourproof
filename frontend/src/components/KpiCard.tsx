import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "@/lib/utils";

/**
 * One headline figure: what it is, the value, and a sentence on what it means. `qualifier` is the proof's direction
 * ("≥" for a proven lower bound, "≤" for an upper bound), shown small so it is never mistaken for part of the number.
 */
export function KpiCard({
  label,
  value,
  qualifier,
  hint,
  href,
  linkLabel = "Details",
  emphasis = false,
  className,
}: {
  label: ReactNode;
  value: string | undefined;
  qualifier?: string;
  hint: ReactNode;
  href?: string;
  linkLabel?: string;
  emphasis?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border border-border bg-card p-5 shadow-xs",
        emphasis && "border-brand/40 bg-brand-subtle/40",
        className,
      )}
    >
      <div className="text-13 text-muted-foreground">{label}</div>
      <div className="mt-2 flex items-baseline gap-1.5">
        {qualifier && value && <span className="text-2xl font-medium text-muted-foreground">{qualifier}</span>}
        <span className="tabular text-3xl font-semibold tracking-tight">{value ?? "—"}</span>
      </div>
      <p className="mt-2 flex-1 text-13 leading-relaxed text-pretty text-muted-foreground">{hint}</p>
      {href && (
        <Link
          to={href}
          className="group mt-4 inline-flex items-center gap-1 self-start text-13 font-medium text-foreground underline-offset-4 hover:underline"
        >
          {linkLabel}
          <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </Link>
      )}
    </div>
  );
}
