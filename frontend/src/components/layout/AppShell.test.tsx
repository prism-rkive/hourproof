import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { routes } from "@/router";
import { PAGES } from "@/routes";
import { snapshot } from "@/test/snapshot";

const overview = snapshot("overview") as { demo: { run_id: string } };

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/overview" ? new Response(JSON.stringify(overview)) : new Response("{}", { status: 404 }),
    ),
  );
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.className = "";
});

describe("app shell", () => {
  it("renders every page with its heading, title and an active nav link", async () => {
    for (const page of PAGES) {
      cleanup();
      renderAt(page.path);
      expect(await screen.findByRole("heading", { level: 1, name: page.title })).toBeInTheDocument();
      const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
      expect(within(nav).getByRole("link", { name: page.label })).toHaveAttribute("aria-current", "page");
      expect(document.title).toBe(page.path === "/" ? "HourProof" : `${page.title} · HourProof`);
    }
  });

  it("shows the last run status from the API data", async () => {
    renderAt("/");
    const status = await screen.findByText(`Last run ${overview.demo.run_id} on Base Sepolia: passed`);
    expect(status).toHaveAttribute("role", "status");
  });

  it("shows a 404 page for unknown paths", async () => {
    renderAt("/no-such-page");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });

  it("has a skip link to the main content", async () => {
    renderAt("/");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")).toBeInTheDocument();
  });

  it("toggles and remembers the theme", async () => {
    renderAt("/");
    await screen.findByRole("heading", { level: 1 });
    const toggle = screen.getByRole("button", { name: "Switch to dark theme" });
    await userEvent.click(toggle);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("hp-theme")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("hp-theme")).toBe("light");
  });

  it("opens the mobile menu with every page", async () => {
    renderAt("/carbon");
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const dialog = await screen.findByRole("dialog");
    for (const page of PAGES)
      expect(
        within(dialog).getByRole("link", { name: new RegExp(page.path === "/" ? page.label : page.title) }),
      ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close menu" })).toBeInTheDocument();
  });
});
