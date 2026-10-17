import type { ReactNode } from "react";
import { useDocumentMeta } from "@/hooks/useDocumentMeta";
import { pageMeta, type PagePath } from "@/routes";

/** Eyebrow, H1 and one-line description from the route table; also sets the document title and description. */
export function PageHeader({ path, actions, docTitle }: { path: PagePath; actions?: ReactNode; docTitle?: string }) {
  const meta = pageMeta(path);
  useDocumentMeta(docTitle ?? (path === "/" ? "HourProof" : meta.title), meta.description);
  return (
    <header className="flex flex-col gap-6 border-b border-border pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl space-y-3">
        <p className="text-13 font-medium text-brand">{meta.label}</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{meta.title}</h1>
        <p className="text-base text-pretty text-muted-foreground">{meta.description}</p>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
