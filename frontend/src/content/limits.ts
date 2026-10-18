/**
 * "What this does not claim", word for word from the original page (kept as src/test/fixtures/
 * what-this-does-not-claim.html). Do not edit: a test compares it with that fixture, and checks its test period
 * against the carbon data.
 */
export const LIMITS = [
  "Issuers and registries in the demo replay Energinet's published data; they are not accredited bodies.",
  "Production enters the chain through an oracle role. Energinet's declaration and settlement series come from the same settlement data, so they are not two independent sources.",
  "The flexible-load share and the extra certificate budget are declared scenario parameters. Every MWh is real.",
  "The ML-DSA verifier is unaudited research code. UltraHonk is not post-quantum.",
  "Hourly matching is voluntary today; the GHG Protocol's Scope 2 revision is still in progress.",
  "Emission factors are Energinet's average, location-based grid factors for a buyer's accounting. They are not marginal emissions, and nothing here claims physically avoided emissions.",
  "Unmatched hours are valued at the hourly grid average, not a residual-mix factor. The carbon results cover Jul–Dec 2025 only. Nothing here is audited.",
] as const;
