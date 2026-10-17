import { ArrowLeft } from "lucide-react";
import { Link, useLocation } from "react-router";
import { Page } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { useDocumentMeta } from "@/hooks/useDocumentMeta";
import { PAGES } from "@/routes";

export function Component() {
  const { pathname } = useLocation();
  useDocumentMeta("Page not found", "This page does not exist.");
  return (
    <Page className="pt-20 sm:pt-28">
      <div className="mx-auto max-w-lg text-center">
        <p className="font-mono text-13 text-brand">404</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">Page not found</h1>
        <p className="mt-3 text-muted-foreground">
          Nothing lives at{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-13 break-all">{pathname}</code>.
        </p>
        <Button asChild variant="outline" className="mt-8">
          <Link to="/">
            <ArrowLeft aria-hidden /> Back to the overview
          </Link>
        </Button>
        <ul className="mt-10 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm">
          {PAGES.slice(1).map((p) => (
            <li key={p.path}>
              <Link to={p.path} className="text-muted-foreground hover:text-foreground">
                {p.title}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </Page>
  );
}
