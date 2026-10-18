import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "./index.css";
import { StrictMode } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import { createBrowserRouter, matchRoutes, type HydrationState } from "react-router";
import { RouterProvider } from "react-router/dom";
import { routes } from "./router";

declare global {
  interface Window {
    __staticRouterHydrationData?: HydrationState;
  }
}

const root = document.getElementById("root")!;
const hydrationData = window.__staticRouterHydrationData;

if (hydrationData && root.hasChildNodes()) {
  // A prerendered page (prerender.mjs): load the matched lazy route modules first, so the first client render is the
  // same tree as the HTML, then hydrate with the same data the HTML was rendered from.
  const lazy = (matchRoutes(routes, window.location) ?? []).filter((m) => typeof m.route.lazy === "function");
  await Promise.all(
    lazy.map(async (m) => {
      const mod = await (m.route.lazy as () => Promise<Record<string, unknown>>)();
      Object.assign(m.route, { ...mod, lazy: undefined });
    }),
  );
  const router = createBrowserRouter(routes, { hydrationData });
  hydrateRoot(
    root,
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  );
} else {
  // Development, or a path that was not prerendered: render on the client.
  const router = createBrowserRouter(routes);
  createRoot(root).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  );
}
