import { useEffect, useRef } from "react";
import { Outlet, ScrollRestoration, useLocation, useNavigation } from "react-router";
import { cn } from "@/lib/utils";
import { Footer } from "./Footer";
import { TopNav } from "./TopNav";

function SkipLink() {
  return (
    <a
      href="#main"
      className="fixed left-4 top-3 z-[60] -translate-y-20 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-md transition-transform focus:translate-y-0"
    >
      Skip to content
    </a>
  );
}

function RouteProgress() {
  const busy = useNavigation().state === "loading";
  return (
    <div
      aria-hidden
      className={cn(
        "fixed inset-x-0 top-0 z-[55] h-0.5 origin-left bg-brand transition-[transform,opacity] duration-500",
        busy ? "scale-x-75 opacity-100" : "scale-x-100 opacity-0",
      )}
    />
  );
}

export function AppShell() {
  const { pathname, hash } = useLocation();
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);
  useEffect(() => {
    // After client-side navigation, move focus to the new page so screen readers announce it (not on first load).
    if (first.current) {
      first.current = false;
      return;
    }
    if (!hash) main.current?.focus({ preventScroll: true });
  }, [pathname, hash]);

  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <RouteProgress />
      <TopNav />
      <main id="main" ref={main} tabIndex={-1} className="flex-1 focus:outline-none">
        <Outlet />
      </main>
      <Footer />
      <ScrollRestoration />
    </div>
  );
}

/** Page body container: one max width and gutter for every page. */
export function Page({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-6xl px-4 pt-10 sm:px-6 sm:pt-14", className)}>{children}</div>;
}
