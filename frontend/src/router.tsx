import { createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { RouteError } from "@/components/ErrorState";
import { fetchOverview } from "@/lib/api";
import type { Overview } from "@/lib/schemas";

export type RootData = { overview: Promise<Overview> };

/** The overview is shared by the whole shell (run status, footer). Not awaited: the shell renders immediately. */
export function rootLoader({ request }: { request: Request }): RootData {
  const overview = fetchOverview(request.signal);
  overview.catch(() => {}); // handled where it is rendered (<Await errorElement>)
  return { overview };
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

export const router = createBrowserRouter(routes);
