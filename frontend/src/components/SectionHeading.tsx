import type { ReactNode } from "react";
import { ScopeTag } from "./ScopeTag";

export function SectionHeading({
  id,
  title,
  sub,
  scope,
  actions,
}: {
  id: string;
  title: string;
  sub?: ReactNode;
  scope?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        {scope && <ScopeTag scope={scope} className="mb-2" />}
        <h2 id={id} className="text-2xl font-semibold tracking-tight">
          {title}
        </h2>
        {sub && <p className="mt-2 text-sm text-pretty text-muted-foreground">{sub}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
