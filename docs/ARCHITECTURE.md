# Architecture

```
 Energinet (Energi Data Service)                         buyer (private)
 ├─ DeclarationProduction ──► oracle role ─► ProductionOracle (write-once MWh per zone/hour/asset)
 ├─ Forecasts_Hour ───────────┐                    │ caps issuance
 └─ ConsumptionDK3619Industry ─┤                    ▼
                               │   issuer (ML-DSA-44 key) ─► CertRegistry A ─┐
              AI agent ◄───────┘   issuer (ML-DSA-44 key) ─► CertRegistry B ─┤─► SliceLedger (shared bitmap:
   plans (shift load, buy hours)                                             │   each MWh-hour claimed once)
        │ hash before the day                                                │
        ▼                                                                    ▼ cancellations
   AgentCommitLog                      data hub ─ commitment ─►  ClaimManager ◄── UltraHonk proof
                                                                    │  (rebuilds public inputs itself)
                                                                    ▼  bestProvenBps
                                                       SustainabilityLinkedNote (coupon step-up)
```

### Carbon-aware flow

```
 Energinet                                                                 buyer (private)
 ├─ DeclarationGridEmission (Final; live: Initial) ─► oracle role ─► IntensityOracle
 │     CO2PerkWh, 125 %, DK1/DK2 weighted by consumption                  (write-once g/kWh per zone/hour, <= 2,000)
 ├─ Forecasts_Hour (DK1/DK2 x offshore/onshore/solar) ─┐                    │ intensity[168]
 └─ day-ahead prices (Elspot / DayAheadPrices) ────────┤                    ▼
                                                       │     ClaimManager.submitEmissionsProof(claim, τ, cap, proof)
   CO2 model (gradient-boosted trees, monthly walk-forward)  rebuilds [τ, cap, cert[168], intensity[168], commitment]
        │ tomorrow's 24 forecasts                            │ the same data-hub commitment as the coverage proof
        ▼                                                    ▼ bestProvenResidualKg / bestResidualKgOf
   plan: move 10 % of each hour's load into cleaner   SustainabilityLinkedNote, KPI = RESIDUAL_EMISSIONS
   hours of the same day (no hour above +25 %)        (base coupon iff a proven cap <= target kg)
        │ hash before the day (one document with the procurement plan)
        ▼
   AgentCommitLog
```

The emissions circuit (`circuits/emissions`) proves, with `load[168]` and `salt` private:
`Σ min(load, cert) · 10⁴ ≥ τ · Σ load` **and** `Σ (load − min(load, cert)) · intensity ≤ cap_kg · 1000`
(grams), and outputs `hp_lib::commit_load(load, salt)`. One data-hub attestation therefore serves both the
coverage proof and the emissions proof.

## Contracts (`contracts/src`)

| Contract | Role |
|---|---|
| `ProductionOracle` | Write-once metered production per hour |
| `SliceLedger` | Shared double-claim stop across registries |
| `CertRegistry` | PQ-signed batch issuance, capped by production; cancellation into claims |
| `ClaimManager` | Claims, load attestations, ZK coverage proofs, ZK residual-emissions proofs |
| `IntensityOracle` | Write-once hourly grid CO2 intensity (whole g/kWh, at most 2,000) per zone and hour |
| `AgentCommitLog` | Commit-before-the-day, reveal-after for the agent's plans |
| `SustainabilityLinkedNote` + `TestUSD` | KPI-linked coupon on proven hourly coverage (COVERAGE) or proven residual emissions (RESIDUAL_EMISSIONS); test token, no value |
| `generated/HonkVerifier.sol` | Generated from the coverage circuit by `bb` (`python -m hourproof zk build`) |
| `generated/EmissionsHonkVerifier.sol` | Generated from the emissions circuit; every contract and library is renamed `Emissions…` so both verifiers coexist (runtime 18,145 B, under EIP-170) |
| `lib/evm-ml-dsa-verifier` | Vendored FIPS 204 ML-DSA-44 verifier (MIT, unaudited) |

## Circuit (`circuits/coverage`)

Private `load[168]`, `salt`; public `threshold_bps`, `cert[168]`; output `commit(load, salt)`.
Asserts `Σ min(load_h, cert_h) · 10000 ≥ threshold · Σ load_h`. 111k gates (UltraHonk); proving took
10 s in the Colab kill test. The data hub runs `circuits/load_commit` (same `hp_lib::commit_load`).

## Circuit (`circuits/emissions`)

Private `load[168]`, `salt`; public `threshold_bps`, `cap_kg`, `cert[168]`, `intensity[168]`; output
`commit(load, salt)`. 62,243 gates. On the kill test's week (from 2025-08-12, real data) it proves coverage
≥ 44.76 % and residual ≤ 1,842.7 t in under 2 s here, and the prover refuses a cap 1 kg lower.

## Carbon mode (`hourproof/carbon.py`)

The CO2-intensity forecast and the shifting policy, ported from the carbon kill test. The choices are frozen
on validation in `data/agent_config.json` → `carbon`; see `docs/CARBON_RESULTS.md`. Live mode
(`hourproof/live.py`) commits tomorrow's 24 forecasts and the planned shift profile inside the same plan hash
as the wind forecast.

## Agent (`hourproof/agent.py`)

Two gradient-boosted models (scikit-learn): wind from the day-ahead forecast, load from calendar and
lags ≥ 48 h. A greedy policy moves the flexible share of load into hours with predicted surplus and
water-fills an extra certificate budget into the largest predicted shortfalls. Walk-forward with
monthly retraining; compared against a portfolio that gets exactly the same extra MWh.

## Orchestration (`hourproof/demo.py`)

Two modes. `carbon` (the default): 15 steps and 8 attacks: the procurement scenario's 5, plus a residual
1 kg below the truth (refused by the prover), a re-posted cleaner intensity, and a proof on a fake intensity
vector. `procurement`: the original 12 steps and 5 attacks. Every step is a real transaction via Foundry's `cast`. The local chain is an anvil
"replay chain" whose clock starts two days before the replayed week, so commit-before-the-day can be
shown for a past week; on Base Sepolia that only holds in live mode.
