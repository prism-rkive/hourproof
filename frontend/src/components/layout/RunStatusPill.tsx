import { Suspense, useEffect } from "react";
import { Await, Link, useRevalidator, useRouteLoaderData } from "react-router";
import type { RootData } from "@/router";
import { runStatus, type RunInfo, type Tone } from "@/lib/selectors";
import { cn } from "@/lib/utils";

const DOT: Record<Tone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-subtle-foreground",
};

const POLL_MS = 4000; // while a local run is in progress, refresh the status like the original dashboard did

function Pill({ overview, variant }: { overview: RunInfo; variant: "bar" | "menu" }) {
  const s = runStatus(overview);
  const revalidator = useRevalidator();
  useEffect(() => {
    if (!overview.running) return;
    const t = setInterval(() => revalidator.state === "idle" && revalidator.revalidate(), POLL_MS);
    return () => clearInterval(t);
  }, [overview.running, revalidator]);

  return (
    <Link
      to="/proof"
      title={s.full}
      className={cn(
        "group inline-flex items-center gap-2 border border-border text-13 text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
        variant === "bar" ? "h-8 rounded-full px-3" : "w-full rounded-lg px-3.5 py-2.5",
      )}
    >
      <span className="relative flex size-2 shrink-0" aria-hidden>
        {s.pulse && <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", DOT[s.tone])} />}
        <span className={cn("relative size-2 rounded-full", DOT[s.tone])} />
      </span>
      <span role="status" aria-live="polite" className="sr-only">
        {s.full}
      </span>
      {variant === "menu" ? (
        <span aria-hidden className="flex min-w-0 flex-col">
          <span className="text-foreground">{s.short}</span>
          {s.runId && (
            <span className="truncate font-mono text-xs text-subtle-foreground">
              {s.runId} · {s.network}
            </span>
          )}
        </span>
      ) : (
        <span aria-hidden className="truncate">
          {s.short}
          {s.runId && (
            <span className="ml-1.5 hidden font-mono text-xs text-subtle-foreground xl:inline">{s.runId}</span>
          )}
        </span>
      )}
    </Link>
  );
}

function Placeholder({ variant, text }: { variant: "bar" | "menu"; text: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border text-13 text-subtle-foreground",
        variant === "bar" ? "h-8 px-3" : "h-9 w-full px-3.5",
      )}
    >
      <span className="size-2 rounded-full bg-border-strong" aria-hidden />
      <span role="status" aria-live="polite">
        {text}
      </span>
    </span>
  );
}

/** "Last run … passed", driven by /api/overview (live locally, the verified-run snapshot when hosted). */
export function RunStatusPill({ variant = "bar" }: { variant?: "bar" | "menu" }) {
  const data = useRouteLoaderData("root") as RootData | undefined;
  if (!data) return null;
  return (
    <Suspense fallback={<Placeholder variant={variant} text="Loading run status" />}>
      <Await resolve={data.overview} errorElement={<Placeholder variant={variant} text="Run status unavailable" />}>
        {(o: RunInfo) => <Pill overview={o} variant={variant} />}
      </Await>
    </Suspense>
  );
}
