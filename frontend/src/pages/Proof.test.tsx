import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { figuresWithoutScope, renderRoute } from "@/test/render";
import { snapshot } from "@/test/snapshot";

/* eslint-disable @typescript-eslint/no-explicit-any */
const o = snapshot("overview") as any;
const log = snapshot("log") as any;
const txs: any[] = o.demo.steps.flatMap((s: any) => s.txs);

afterEach(() => vi.unstubAllGlobals());

describe("Proof run", () => {
  it("lists every step and every transaction with its explorer link", async () => {
    await renderRoute("/proof");
    expect(txs).toHaveLength(o.demo.summary.transactions);
    expect(screen.getAllByRole("button", { expanded: false }).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /Expand all/ }));
    const links = [...document.querySelectorAll<HTMLAnchorElement>("a[data-tx]")];
    expect(links.map((a) => a.dataset.tx)).toEqual(txs.map((t) => t.hash));
    links.forEach((a, i) => expect(a.href).toBe(txs[i].url));
    for (const s of o.demo.steps) expect(screen.getByText(s.title)).toBeInTheDocument();
  });

  it("shows the run's summary figures", async () => {
    await renderRoute("/proof");
    const sum = o.demo.summary;
    const main = document.getElementById("main")!;
    expect(main).toHaveTextContent(sum.transactions.toLocaleString("en-GB"));
    expect(main).toHaveTextContent(sum.gas_total.toLocaleString("en-GB"));
    expect(main).toHaveTextContent(`${sum.verified_checks} passed`);
    expect(main).toHaveTextContent(`${sum.attacks_blocked} of ${sum.attacks_total}`);
  });

  it("shows the recorded log verbatim, labelled with its run", async () => {
    await renderRoute("/proof");
    expect(screen.getByRole("heading", { name: `Recorded log of run ${o.demo.run_id}` })).toBeInTheDocument();
    const pre = document.querySelector("pre")!;
    expect(pre.textContent).toBe(log.log);
  });

  it("keeps the run buttons, disabled on the hosted snapshot", async () => {
    await renderRoute("/proof");
    for (const name of ["Run on local chain", "Run on Base Sepolia"]) {
      expect(screen.getByRole("button", { name: new RegExp(name) })).toBeDisabled();
    }
  });

  it("labels the period of every figure", async () => {
    await renderRoute("/proof");
    await userEvent.click(screen.getByRole("button", { name: /Expand all/ }));
    expect(figuresWithoutScope(document.getElementById("main")!).unscoped).toEqual([]);
  });
});
