import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { figuresWithoutScope, renderRoute } from "@/test/render";
import { snapshot } from "@/test/snapshot";

/* eslint-disable @typescript-eslint/no-explicit-any */
const o = snapshot("overview") as any;
const attacks: any[] = o.demo.attacks;

afterEach(() => vi.unstubAllGlobals());

describe("Security", () => {
  it("computes the refused count from the attacks", async () => {
    await renderRoute("/security");
    const refused = attacks.filter((a) => a.status === "blocked").length;
    expect(refused).toBe(o.demo.summary.attacks_blocked);
    expect(
      screen.getByRole("heading", { level: 2, name: `${refused} of ${attacks.length} refused` }),
    ).toBeInTheDocument();
  });

  it("lists every attack with what was expected and observed, and never invents a transaction", async () => {
    await renderRoute("/security");
    const main = document.getElementById("main")!;
    for (const a of attacks) {
      expect(screen.getByRole("heading", { level: 3, name: a.title })).toBeInTheDocument();
      expect(main).toHaveTextContent(a.observed);
    }
    const prover = attacks.filter((a) => a.observed === "ProverRefused").length;
    expect(screen.getAllByText("Refused by the prover · no transaction")).toHaveLength(prover);
    expect(screen.getAllByText("Refused before broadcast · no transaction")).toHaveLength(attacks.length - prover);
    // the only linked transaction is the legitimate set-up of the double claim
    const setup = o.demo.steps.find((s: any) => s.id === "attacks_supply").txs;
    expect([...document.querySelectorAll<HTMLAnchorElement>("a[data-tx]")].map((a) => a.dataset.tx)).toEqual(
      setup.map((t: any) => t.hash),
    );
  });

  it("filters by search", async () => {
    await renderRoute("/security");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search the attacks" }), "signature");
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toContain(attacks.find((a) => a.id === "forged_signature").title);
    expect(titles.length).toBeLessThan(attacks.length);
    expect(screen.getByText(`${titles.length} of ${attacks.length} attempts match.`)).toBeInTheDocument();
  });

  it("labels the period of every figure", async () => {
    await renderRoute("/security");
    expect(figuresWithoutScope(document.getElementById("main")!).unscoped).toEqual([]);
  });
});
