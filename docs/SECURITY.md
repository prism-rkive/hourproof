# Security and data-integrity model

This is the document the organisers ask for: what HourProof protects, against whom, how, what is
tested, and what is out of scope.

## Assets

| Asset | Why it matters |
|---|---|
| One MWh produced in one hour | Must back at most one claim, across every registry |
| A buyer's hourly load | Commercially sensitive (reveals operations, capacity, contracts) |
| The hourly-coverage claim | Drives Scope 2 reporting and the note's coupon |
| The agent's plan | Must not be rewritten after the outcome is known |
| The hourly grid intensity (g/kWh) | Prices every unmatched kWh in the residual-emissions proof and the note's KPI |
| The residual-emissions claim | Drives the RESIDUAL_EMISSIONS note's coupon |

## Actors and trust

| Actor | Trusted for | Not trusted for |
|---|---|---|
| Production oracle (poster role) | Posting metered hourly production (write-once) | Anything else |
| Intensity oracle (oracle role) | Posting Energinet's hourly grid intensity, whole g/kWh, at most 2,000 (write-once) | Anything else; it never sees load |
| Registry operator | Accrediting issuers' ML-DSA keys in its registry | Seeing other registries |
| Issuer | Signing certificate batches | Exceeding metered production (contract caps it) |
| Data hub (DSO/TSO metering) | Attesting a commitment to the buyer's load | Learning anything new: it already holds the meter data |
| Buyer | Nothing | Its own coverage claim (must be proven) |
| Anyone | Reading the chain | Writing outside their role |

The design follows the DSO-centric argument: grid operators already hold the meter data and stay
the anchor of trust for measurement; the chain removes the need to trust them for *counting*.

## Threats, mitigations, tests

| # | Attack | Mitigation | Where it is tested |
|---|---|---|---|
| T1 | Same MWh sold by two registries, claimed twice | Shared `SliceLedger`: key = (zone, hour, asset), MWh slices are a bitmap; overlapping cancellation reverts | `SliceLedger.t.sol` incl. 512-run fuzz *revert iff overlap*; `CertRegistry.t.sol`; demo attack `double_claim` |
| T2 | Issuer certifies more than was produced ("ghost" MWh) | `issueBatch` requires `first + count <= productionOf(hour)` | `test_cannotIssueBeyondMeteredProduction`; demo `over_issuance` |
| T3 | Forged / replayed / cross-registry issuer signature | ML-DSA-44 (FIPS 204) over `chainid ‖ registry ‖ issuerId ‖ nonce ‖ keccak(batch)` | `PQIntegration.t.sol` (real signatures via ffi); demo `forged_signature` |
| T4 | Buyer over-states its hourly coverage | UltraHonk proof of `Σ min(load,cert)·10⁴ ≥ τ·Σ load`; the prover cannot build a witness for a false claim | Noir tests `rejects_overclaim_by_one_basis_point`; demo `overclaim` |
| T5 | Proof made against other certificates or another load | `ClaimManager` rebuilds the public inputs itself: certificate vector from its own records, load commitment from the data hub | `test_proofForDifferentCertsRejected`, `HonkIntegration.t.sol` |
| T6 | Proof replayed for a higher threshold | Threshold is a public input | `test_higherThresholdRejected`; demo `replay_higher` |
| T7 | Load leaked through the proof | Load is a private witness; only a salted Pedersen commitment is public | circuit design; `load_commit` and `coverage` share one `hp_lib::commit_load` |
| T8 | Agent rewrites its plan with hindsight | `AgentCommitLog` stores the plan hash with the block time, write-once; reveal must match | `AgentCommitLog.t.sol`; live mode on Base Sepolia |
| T9 | Oracle overwrites history | Production is write-once per (zone, hour, asset) | `ProductionOracle.post` reverts `AlreadyPosted` |
| T10 | Note settled early or paid twice | KPI only via `bestProvenBps` (COVERAGE) or `bestResidualKgOf` (RESIDUAL_EMISSIONS, the issuer's own proofs only); step-up only after the deadline; one claim per holder; checks-effects-interactions | `SustainabilityLinkedNote.t.sol`; `SustainabilityLinkedNoteResidual.t.sol` (a coverage proof does not meet a residual KPI; another buyer's proof does not count; fuzz: met iff cap <= target) |
| T11 | Forecast data leakage in the agent's backtest | Features are built as-of the decision time (D-1 17:30 UTC) | `tests/test_agent.py` corrupts all later data and checks features are unchanged; `tests/test_carbon.py` checks the same for the CO2 features and the walk-forward training cut-off |
| T12 | Intensity oracle posts a wrong or "cleaner" intensity, or rewrites one | `IntensityOracle`: a trusted oracle role (set by the admin) posts Energinet's `DeclarationGridEmission` CO2PerkWh (125 % method, DK1/DK2 weighted by consumption) in whole g/kWh. Each (zone, hour) is write-once (`AlreadyPosted`), bounded to at most 2,000 g/kWh, and hour-aligned. Energinet revises the series: **Initial** is published within about 2 hours, **Final** later. The demo and the backtest use Final; live mode uses Initial for its forecast features and scores against both. A revision cannot overwrite a posted hour; correcting one would need a dispute process (out of scope) | `IntensityOracle.t.sol` (unit and fuzz: round trip, write-once, range, alignment, role); demo attack `intensity_repost` |
| T13 | Buyer proves its residual against a swapped (cleaner) intensity vector, or against other certificates or another load | `ClaimManager.submitEmissionsProof` rebuilds **all** 339 public inputs itself, in the circuit's order: threshold, cap, the claim's certificate vector, the intensity vector read from `IntensityOracle` for the claim's 168 hours (reverts `NotPosted` if any hour is missing), and the data hub's attested load commitment (the same one the coverage proof uses). The prover chooses only the threshold and the cap, and a cap below the truth has no witness | `ClaimManagerEmissions.t.sol` (layout, fake intensity, fake certificates, missing hour, other zone, fuzz: any intensity change breaks the inputs); `EmissionsIntegration.t.sol` (real proof: a lower cap, a higher threshold, an oracle 1 g/kWh lower in one hour, another claim: all rejected); Noir `rejects_cap_one_kg_lower`; demo attacks `residual_understated`, `fake_intensity` |

## Explicitly out of scope / residual risk

- **Oracle honesty.** One poster role publishes production. Energinet's declaration and settlement series
  derive from the same settlement data (the kill test measured 0.00 % difference), so a second
  "independent" source from the same TSO adds nothing. Production would use the TSO's signed feed
  plus an independent cross-check (e.g. ENTSO-E) with an m-of-n quorum.
- **Post-quantum scope.** Issuer signatures are ML-DSA-44. UltraHonk (BN254 pairings) and secp256k1
  transaction signatures are not post-quantum; a STARK-based prover is the migration path.
- **Unaudited code.** The vendored ML-DSA verifier is research code (Fireblocks, Sept 2026). Nothing
  here is audited.
- **Privacy of certificates.** Certificate cancellations are public (as registry cancellations are
  today). Only the load is private. The hourly intensity is public by design.
- **What the residual figure means.** It is the buyer's unmatched consumption times Energinet's hourly
  *average, location-based* grid factor, for a buyer's accounting. It is not a marginal or a physically avoided
  emission, and unmatched hours are not valued with a residual-mix factor. A proven cap is an upper limit on
  that accounting figure, rounded up to a whole kg.
- **Intensity oracle honesty.** As with production, one trusted role posts the intensity, and the source is
  the same TSO. Initial and Final can differ; whichever is posted first stays on-chain.
- **Role keys on testnet** are derived from one throwaway key for convenience. Never reuse that pattern
  with real value.
