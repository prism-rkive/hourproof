import { LayoutTemplate } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { Page } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import type { PagePath } from "@/routes";

/** Phase 2 only: the shell with an empty page. Replaced page by page in Phase 3. */
export function Placeholder({ path, planned }: { path: PagePath; planned: string[] }) {
  return (
    <Page>
      <PageHeader path={path} />
      <EmptyState icon={LayoutTemplate} title="This page is being rebuilt" className="mt-10">
        <p>Coming in the next phase:</p>
        <ul className="mt-3 space-y-1.5 text-left">
          {planned.map((p) => (
            <li key={p} className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-subtle-foreground" aria-hidden />
              {p}
            </li>
          ))}
        </ul>
      </EmptyState>
    </Page>
  );
}
