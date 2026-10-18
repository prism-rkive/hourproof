import { Suspense } from "react";
import { Await, Link, useRouteLoaderData } from "react-router";
import type { RootData } from "@/router";
import { lastRunLine, type RunInfo } from "@/lib/selectors";
import { DATA_SOURCE_URL, PAGES, REPO_URL } from "@/routes";
import { LogoMark } from "./Logo";

const external = { target: "_blank", rel: "noreferrer" } as const;
const linkCls = "text-muted-foreground transition-colors hover:text-foreground";

function LastRun() {
  const data = useRouteLoaderData("root") as RootData | undefined;
  if (!data) return null;
  return (
    <Suspense fallback={null}>
      <Await resolve={data.overview} errorElement={null}>
        {(o: RunInfo) => {
          const line = lastRunLine(o);
          if (!line) return null;
          const evidence = o.static_snapshot?.evidence;
          return (
            <span>
              {line}
              {evidence && (
                <>
                  {" · "}
                  <a
                    href={`${REPO_URL}/tree/main/${evidence}`}
                    {...external}
                    className={`${linkCls} underline underline-offset-4`}
                  >
                    evidence
                  </a>
                </>
              )}
            </span>
          );
        }}
      </Await>
    </Suspense>
  );
}

export function Footer() {
  return (
    <footer className="mt-24 border-t border-border bg-background-subtle">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.5fr_1fr_1fr]">
        <div className="max-w-sm space-y-3">
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <LogoMark className="size-5" />
            HourProof
          </div>
          <p className="text-sm text-muted-foreground">
            Hourly clean-energy claims that count each certificate once, proven without revealing the buyer's load.
          </p>
        </div>
        <nav aria-label="Footer pages">
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-subtle-foreground">Pages</h2>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm md:grid-cols-1">
            {PAGES.map((p) => (
              <li key={p.path}>
                <Link to={p.path} className={linkCls}>
                  {p.path === "/" ? p.label : p.title}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-subtle-foreground">Project</h2>
          <ul className="space-y-2 text-sm">
            <li>
              <Link to="/method#limits" className={linkCls}>
                What this does not claim
              </Link>
            </li>
            <li>
              <a href={REPO_URL} {...external} className={linkCls}>
                Source on GitHub
              </a>
            </li>
            <li>
              <a href={`${REPO_URL}/blob/main/LICENSE`} {...external} className={linkCls}>
                MIT licence
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-xs text-subtle-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>
            Data:{" "}
            <a href={DATA_SOURCE_URL} {...external} className={`${linkCls} underline underline-offset-4`}>
              Energi Data Service, Energinet
            </a>
            . Contracts, circuits and agent: this repository.
          </span>
          <LastRun />
        </div>
      </div>
    </footer>
  );
}
