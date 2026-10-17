/** Every page once: the nav, the page headers, document titles and the footer all read from here. */
export type PageMeta = {
  path: string;
  label: string; // navigation
  title: string; // page heading and document title
  description: string; // one line under the heading, and the meta description
};

export const PAGES = [
  {
    path: "/",
    label: "Overview",
    title: "Hourly clean-energy claims, proven",
    description:
      "A buyer's annual clean-energy match against its hour-by-hour match, and how HourProof closes and proves the gap.",
  },
  {
    path: "/proof",
    label: "Proof run",
    title: "Proof run",
    description: "Every step of the last run, with its on-chain transactions and the recorded log.",
  },
  {
    path: "/security",
    label: "Security",
    title: "Attack tests",
    description: "Each attempt to cheat the system, what refused it, and whether a transaction exists.",
  },
  {
    path: "/agent",
    label: "Agent",
    title: "AI agent",
    description: "How the agent moves flexible load and buys hourly certificates, tested walk-forward on real hours.",
  },
  {
    path: "/carbon",
    label: "Carbon",
    title: "Carbon-aware load",
    description: "Shifting flexible load toward low-carbon hours, and proving residual emissions in zero knowledge.",
  },
  {
    path: "/note",
    label: "Note",
    title: "Sustainability-linked note",
    description: "A note whose coupon settles on-chain against the proven emissions KPI.",
  },
  {
    path: "/method",
    label: "Method",
    title: "Methodology & limits",
    description: "What this does not claim, the data sources, the assumptions and the cryptography.",
  },
] as const satisfies readonly PageMeta[];

export type PagePath = (typeof PAGES)[number]["path"];

export function pageMeta(path: PagePath): PageMeta {
  return PAGES.find((p) => p.path === path)!;
}

export const REPO_URL = "https://github.com/prism-rkive/hourproof";
export const DATA_SOURCE_URL = "https://www.energidataservice.dk/";
