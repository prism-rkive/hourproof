/** Every page once: the nav, the page headers, document titles and the footer all read from here. */
export type PageMeta = {
  path: string;
  label: string; // navigation
  title: string; // page heading and document title
  description: string; // one line under the heading, and the meta description
  plain: string; // what the page shows and why it matters, for a reader new to the field (nav tooltip, menu, header)
};

export const PAGES = [
  {
    path: "/",
    label: "Overview",
    title: "Hourly clean-energy claims, proven",
    description:
      "A buyer's annual clean-energy match against its hour-by-hour match, and how HourProof closes and proves the gap.",
    plain: "The short version: the problem, the key results, and where to check each of them.",
  },
  {
    path: "/proof",
    label: "Proof run",
    title: "Proof run",
    description: "Every step of the last run, with its on-chain transactions and the recorded log.",
    plain:
      "The whole system run end to end on a public test blockchain. Every step links to its transaction, so anyone can check that it happened.",
  },
  {
    path: "/security",
    label: "Security",
    title: "Attack tests",
    description: "Each attempt to cheat the system, what refused it, and whether a transaction exists.",
    plain:
      "Deliberate attempts to cheat, such as selling the same clean energy twice or faking a signature, and what stopped each one.",
  },
  {
    path: "/agent",
    label: "Agent",
    title: "AI agent",
    description: "How the agent moves flexible load and buys hourly certificates, tested walk-forward on real hours.",
    plain:
      "An AI agent decides a day ahead when to run flexible work and which extra hourly certificates to buy, so more hours run on clean energy.",
  },
  {
    path: "/carbon",
    label: "Carbon",
    title: "Carbon-aware load",
    description: "Shifting flexible load toward low-carbon hours, and proving residual emissions in zero knowledge.",
    plain:
      "The agent can also move flexible work to hours when the grid is cleaner. The buyer then proves its remaining emissions without revealing its usage.",
  },
  {
    path: "/note",
    label: "Note",
    title: "Sustainability-linked note",
    description: "A note whose coupon settles on-chain against the proven emissions KPI.",
    plain:
      "A bond-like investment whose interest depends on the proven emissions figure: if the target is missed, the coupon steps up and investors are paid more.",
  },
  {
    path: "/method",
    label: "Method",
    title: "Methodology & limits",
    description: "What this does not claim, the data sources, the assumptions and the cryptography.",
    plain:
      "The fine print: what this project does not claim, where the data comes from, and how the cryptography works.",
  },
] as const satisfies readonly PageMeta[];

export type PagePath = (typeof PAGES)[number]["path"];

export function pageMeta(path: PagePath): PageMeta {
  return PAGES.find((p) => p.path === path)!;
}

export const REPO_URL = "https://github.com/prism-rkive/hourproof";
export const DATA_SOURCE_URL = "https://www.energidataservice.dk/";
