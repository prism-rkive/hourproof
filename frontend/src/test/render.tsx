/** Render a route of the real app against the committed snapshot (fetch is stubbed with the snapshot files). */
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { clearApiCache } from "@/lib/api";
import { routes } from "@/router";
import { snapshot } from "./snapshot";

const FILES: Record<string, "overview" | "week" | "carbon" | "log"> = {
  "/api/overview": "overview",
  "/api/week": "week",
  "/api/carbon": "carbon",
  "/api/demo/log": "log",
};

export async function renderRoute(path: string) {
  clearApiCache();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      FILES[url] ? new Response(JSON.stringify(snapshot(FILES[url]!))) : new Response("{}", { status: 404 }),
    ),
  );
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const result = render(<RouterProvider router={router} />);
  await screen.findByRole("heading", { level: 1 }, { timeout: 5000 });
  return { router, ...result };
}

/** A displayed figure: a number followed by a unit (%, t, MWh, tUSD, g/kWh). */
export const FIGURE = /\d[\d,]*(?:\.\d+)?\s?(?:%|t\b|MWh|tUSD|g\/kWh)/;

/**
 * Every figure under `root` must sit inside an element with `data-scope` that also shows its scope tag, so no number
 * can appear without the period it covers. Returns the figures found, for reporting.
 */
export function figuresWithoutScope(root: HTMLElement): { figures: string[]; unscoped: string[] } {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const figures: string[] = [];
  const unscoped: string[] = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = n.textContent ?? "";
    if (!FIGURE.test(text)) continue;
    figures.push(text.trim());
    const holder = n.parentElement?.closest<HTMLElement>("[data-scope]");
    const tag = holder?.querySelector("[data-scope-tag]")?.textContent;
    if (!holder || !holder.dataset.scope || tag !== holder.dataset.scope) unscoped.push(text.trim());
  }
  return { figures, unscoped };
}
