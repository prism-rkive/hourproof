/**
 * Plain English names for the Energinet industry branches (DK36 codes) the buyer can be. The data keeps Energinet's
 * Danish title exactly as published: "Telekommunikation &It - og informationstjenester" is how Energinet's
 * ConsumptionDK3619IndustryHour dataset spells branch JB_JC (DK36Title), so the site shows the English name and
 * offers the original on demand.
 */
const ENGLISH: Record<string, string> = {
  JB_JC: "Danish telecommunications and IT services sector",
};

export type Sector = { label: string; original: string; code: string };

/** `branch` is the dataset's buyer_branch ("<DK36 code> <Danish title>"), `title` its buyer_label. */
export function sector(branch: unknown, title: unknown): Sector | null {
  if (typeof title !== "string" || !title || typeof branch !== "string") return null;
  const code = branch.split(" ")[0] ?? "";
  const label = ENGLISH[code];
  return label ? { label, original: title, code } : null;
}
