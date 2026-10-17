/**
 * Plain-language definitions for the terms a reader new to energy markets, blockchains or cryptography meets on these
 * pages. Used by <Term> (tap or hover on an underlined word) and listed in full on the Methodology page.
 */
export const GLOSSARY = {
  "hourly-matching": {
    term: "Hourly matching",
    definition:
      "Checking clean-energy use hour by hour instead of over a whole year. A yearly total can hide the hours when the buyer actually ran on other power.",
  },
  certificate: {
    term: "Certificate",
    definition:
      "A record that one MWh of clean electricity was produced in a specific hour. A buyer cancels certificates to claim that electricity; each one may be claimed only once.",
  },
  coverage: {
    term: "Coverage",
    definition:
      "The share of the buyer's electricity use that is matched, hour by hour, by certificates from the same hour.",
  },
  "zk-proof": {
    term: "Zero-knowledge proof",
    definition:
      "A cryptographic proof that a statement is true, for example that coverage is at least the target, without revealing the data behind it, here the buyer's hourly use.",
  },
  commitment: {
    term: "Commitment",
    definition:
      "A cryptographic fingerprint of data, published now, that binds its owner to that data without revealing it. Here it fixes the buyer's hourly load before anything is proven about it.",
  },
  "data-hub": {
    term: "Metering data hub",
    definition:
      "The party that holds metered consumption data. In the demo, a role standing in for it publishes the commitment to the buyer's load.",
  },
  "ml-dsa": {
    term: "ML-DSA-44",
    definition:
      "A post-quantum digital signature standard (NIST FIPS 204). Each daily batch of certificates is signed with it, and the signature is checked by a smart contract.",
  },
  ultrahonk: {
    term: "UltraHonk",
    definition:
      "The zero-knowledge proof system used here (Aztec's Barretenberg, with circuits written in Noir). A smart contract verifies the proofs. It is not post-quantum.",
  },
  "base-sepolia": {
    term: "Base Sepolia",
    definition:
      "A public test network of Base, an Ethereum layer-2 blockchain. Its transactions are real and visible to anyone, but its coins have no monetary value.",
  },
  transaction: {
    term: "Transaction",
    definition:
      "A signed instruction recorded on the blockchain. Each has a unique hash that anyone can look up on a block explorer such as BaseScan.",
  },
  gas: {
    term: "Gas",
    definition:
      "The unit of computation a transaction uses on Ethereum-style blockchains. Heavier steps, such as verifying a proof, use more gas.",
  },
  oracle: {
    term: "Oracle",
    definition:
      "An account allowed to post outside data on-chain. Here it posts Energinet's published hourly production and grid intensity, and cannot change a value once posted.",
  },
  "residual-emissions": {
    term: "Residual emissions",
    definition:
      "The emissions from the electricity that clean certificates do not cover, valued with the grid's average emission factor for each hour.",
  },
  "location-based": {
    term: "Location-based emission factor",
    definition:
      "The average CO₂ per kWh of the local grid in a given hour. It describes the grid mix, not the effect of using one more kWh.",
  },
  kpi: {
    term: "KPI",
    definition:
      "Key performance indicator: the measurable target a sustainability-linked note is tied to. Here, the buyer's residual emissions for the week.",
  },
  coupon: {
    term: "Coupon",
    definition: "The interest a note pays its investors, as a percentage of the amount invested.",
  },
  "basis-point": {
    term: "Basis point (bps)",
    definition: "One hundredth of a percent: 100 basis points are 1 %.",
  },
  "test-token": {
    term: "tUSD",
    definition: "A test token that stands in for money in the demo. It has no value.",
  },
  "attack-test": {
    term: "Attack test",
    definition:
      "A deliberate attempt to cheat, run as part of the demo. The run only passes if the contracts or the prover refuse every one.",
  },
  "flexible-load": {
    term: "Flexible load",
    definition:
      "The part of electricity use that can move to another hour without harm, such as batch computing jobs. Its size here is a declared scenario parameter.",
  },
  "walk-forward": {
    term: "Walk-forward test",
    definition:
      "Testing a strategy day by day on past data, using only what was known before each day, the way it would have run live.",
  },
  "perfect-foresight": {
    term: "Perfect foresight",
    definition:
      "A reference strategy that knows the future exactly. No real strategy can reach it; it shows the ceiling.",
  },
} as const;

export type GlossaryId = keyof typeof GLOSSARY;
