import { Lightbulb } from "lucide-react";
import type { ReactNode } from "react";
import { useDocumentMeta } from "@/hooks/useDocumentMeta";
import { pageMeta, type PagePath } from "@/routes";

/** A one-paragraph explanation for readers new to the field, shown on every page under its heading. */
export function PlainTerms({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-3 rounded-lg border border-border bg-background-subtle px-4 py-3 text-sm">
      <Lightbulb className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
      <p className="text-pretty text-muted-foreground">
        <span className="font-medium text-foreground">In plain terms: </span>
        {children}
      </p>
    </div>
  );
}

/** Eyebrow, H1, one-line description and the plain-terms box from the route table; sets the document title too. */
export function PageHeader({ path, actions, docTitle }: { path: PagePath; actions?: ReactNode; docTitle?: string }) {
  const meta = pageMeta(path);
  useDocumentMeta(docTitle ?? (path === "/" ? "HourProof" : meta.title), meta.description);
  return (
    <header className="flex flex-col gap-6 border-b border-border pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl space-y-3">
        <p className="text-13 font-medium text-brand">{meta.label}</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{meta.title}</h1>
        <p className="text-base text-pretty text-muted-foreground">{meta.description}</p>
        <div className="pt-2">
          <PlainTerms>{meta.plain}</PlainTerms>
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
