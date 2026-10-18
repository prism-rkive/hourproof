import type { RouteObject } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { RouteError } from "@/components/ErrorState";
import { getOverview } from "@/lib/api";
import { runInfo, type RunInfo } from "@/lib/selectors";

/** A resolved value when prerendered or hydrated; the shell renders it with <Await> either way. */
export type RootData = { overview: RunInfo | Promise<RunInfo> };

/**
 * The overview is shared by the whole shell (run status, footer) and the pages (same cached request). Fresh on every
 * call, so revalidating while a local run is in progress updates it. Awaited, so the prerendered HTML and the
 * hydration data contain it (the hosted pages are prerendered from the snapshot; see prerender.mjs).
 */
export async function rootLoader(): Promise<RootData> {
  try {
    return { overview: runInfo(await getOverview(true)) };
  } catch (e) {
    const failed = Promise.reject(e);
    failed.catch(() => {}); // shown where it is rendered (<Await errorElement>), the pages still load
    return { overview: failed };
  }
}

export const routes: RouteObject[] = [
  {
    id: "root",
    path: "/",
    loader: rootLoader,
    Component: AppShell,
    HydrateFallback: () => null,
    children: [
      {
        errorElement: <RouteError />,
        children: [
          { index: true, lazy: () => import("@/pages/Overview") },
          { path: "proof", lazy: () => import("@/pages/Proof") },
          { path: "security", lazy: () => import("@/pages/Security") },
          { path: "agent", lazy: () => import("@/pages/Agent") },
          { path: "carbon", lazy: () => import("@/pages/Carbon") },
          { path: "note", lazy: () => import("@/pages/Note") },
          { path: "method", lazy: () => import("@/pages/Method") },
          { path: "*", lazy: () => import("@/pages/NotFound") },
        ],
      },
    ],
  },
];
