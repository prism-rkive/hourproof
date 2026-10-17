# HourProof

**Carbon-aware hourly clean-energy claims, proven without revealing load.** A learned day-ahead forecast of
Denmark's hourly grid CO2 intensity moves a buyer's flexible load into cleaner hours, and zero-knowledge proofs
show its hourly coverage and its residual emissions on-chain while its hourly consumption stays private. Each
certificate can be claimed only once across registries, issuers sign with post-quantum keys, and the agent
commits its plans on-chain before the day. Built on real Danish grid data.

IEEE ClimateChain Global Hackathon 2026, Track 2 (Renewable Energy & Energy Trading).

**Verified on Base Sepolia.** The full carbon-aware scenario ran on Base Sepolia (chain 84532) with real UltraHonk
proofs and real ML-DSA-44 signatures: 80 transactions, all 8 attacks refused, both ZK proofs re-verified on-chain from
the submitted transactions. Evidence, every transaction and file hash: [`evidence/`](evidence/base-sepolia-20261017T141639Z/README.md);
the two earlier attempts that failed, why, and the fixes: [`docs/BASE_SEPOLIA.md`](docs/BASE_SEPOLIA.md).
Re-check it yourself, read-only, without any key: `make verify-evidence`.

**Live dashboard: https://hourproof-phi.vercel.app**, a static snapshot of that verified run (every transaction
links to BaseScan). See [Deploy the dashboard](#deploy-the-dashboard-vercel).

## Results in one table (real Energinet data, TEST = Jul–Dec 2025, run once)

The buyer is Denmark's IT and telecom sector. 10 % of each hour's load may move within the same UTC day, and
no hour may grow by more than 25 % (declared scenario parameters, not measured flexibility).

| Strategy | Location-based emissions, t | vs no shift | Hourly coverage |
|---|---:|---:|---:|
| No shift | 48,840.2 | — | 70.45 % |
| Shift for MWh matching | 47,889.1 | −1.95 % | 71.47 % |
| Carbon-aware, last week's intensity (persistence) | 48,546.5 | −0.60 % | 70.03 % |
| **Carbon-aware, learned forecast** | **47,631.7** | **−2.47 %** | 71.36 % |
| Carbon-aware, actual intensity (reference) | 46,856.5 | −4.06 % | 71.37 % |

- **The learned CO2 forecast has 47 % lower error than persistence:** 20.28 g/kWh mean absolute error, against
  38.36 for last week's value and 41.41 for two days earlier. `use_price = true` was chosen on validation
  (Apr–Jun: 21.65 vs 23.82) and the test half-year was run once.
- Shifting 10 % of the sector's load by it cuts location-based emissions **2.47 %, about 1,208 t in six
  months**. That compares with 0.60 % using persistence and 4.06 % using the actual intensity (a reference, not a plan).
- **The forecast is what makes it work.** With persistence, carbon-aware shifting does *worse* than simply
  shifting for MWh matching (0.60 % vs 1.95 %). With the learned forecast it does better (2.47 %). A weekly
  block bootstrap puts the learned forecast's advantage at +0.52 points [+0.22, +0.83] over MWh shifting and
  +1.87 [+1.41, +2.44] over persistence (reported only, never used to choose anything).
- **Residual emissions are proven without revealing load.** A week from 2025-08-12: coverage ≥ 44.76 % and
  residual ≤ 1,842.7 t, a 62,243-gate circuit, proven in under 2 s here (6.5 s in Colab). The prover refuses a
  cap 1 kg lower.
- This repository reruns the frozen procedure (`python -m hourproof agent carbon`). Every number is within
  0.5 % of the table, which a regression test enforces. The strategies without the model match exactly;
  the learned model is 0.13 % off on MAE and 0.004 % off on emissions (47,633.8 t, 1,206 t saved), probably
  because of library builds. Details, caveats and reproduction: `docs/CARBON_RESULTS.md`.

## The problem, in one real number

A Danish IT and telecom sector that buys exactly its yearly consumption in Danish wind (2025, Energinet
data) is matched **69.7 %** hour by hour. "100 % renewable" on an annual basis is not 100 % in the hours it
runs. Hourly (24/7) matching and hourly emissions accounting fix the bookkeeping, but bring new problems:

1. **Double counting across registries.** The same MWh-hour can be sold by two registries; nobody sees both.
2. **Privacy.** Proving hourly matching or hourly emissions normally means disclosing hourly load, which is
   commercially sensitive.
3. **Trust in the planner.** Anyone can claim a clever plan after the fact.
4. **Trust in the factors.** A buyer could compute its emissions with a cleaner intensity series than the real one.

## What HourProof does

| Problem | Mechanism | Claim it supports |
|---|---|---|
| Double counting | One shared `SliceLedger`: every MWh of every (zone, hour, asset) is a bit; cancellation by any registry sets it; overlap reverts | A second claim on the same MWh is refused on-chain |
| Ghost issuance | Issuance capped by metered production posted by an oracle role | No certificate beyond what was produced in that hour |
| Forged issuers | Batches signed with ML-DSA-44 (FIPS 204), verified on-chain | Issuer signatures are post-quantum and replay-bound |
| Privacy (coverage) | Noir/UltraHonk proof: `Σ min(load, cert) ≥ τ · Σ load` with load private; the contract rebuilds all public inputs | Coverage ≥ τ is proven; load stays private |
| Privacy (emissions) | Second circuit: coverage ≥ τ **and** `Σ (load − min(load, cert)) · intensity ≤ cap`, over the **same** data-hub commitment | Residual emissions ≤ cap is proven; load stays private |
| Swapped factors | `IntensityOracle` (write-once g/kWh per hour, ≤ 2,000); `ClaimManager` reads the intensity vector itself | The proof uses the posted intensities, not the prover's |
| Carbon-aware planning | A learned CO2-intensity forecast moves 10 % of each hour's load to cleaner hours of the same day | −2.47 % location-based emissions on the test half-year |
| Planner honesty | The agent commits each day's plan hash before the day (certificate purchases, CO2 forecast, planned shift); reveal must match | Plans cannot be rewritten with hindsight |
| Consequences | Sustainability-linked note with a COVERAGE or a RESIDUAL_EMISSIONS KPI: base coupon if a proof meets the target, automatic step-up if not | The KPI is enforced by a proof, not a report |

## The procurement agent (v2, frozen on validation, TEST run once)

From `docs/AGENT_RESULTS.md`:

| TEST, Jul–Dec 2025 | v1 | v2 |
|---|---:|---:|
| Agent hourly coverage (shifting + buying) | 74.20 % | **75.69 %** |
| Gain vs a bigger portfolio with exactly the same extra MWh | +2.88 pp | **+3.97 pp** |
| Perfect foresight (reference) | 75.29 % | 76.73 % |

**The ablation is honest about the ML.** With Energinet's raw wind forecast and last week's load instead of any
learned model, the same planner reaches 75.28 % (+3.56 pp vs the same MWh). About 90 % of v2's advantage needs
no machine learning; most of the improvement over v1 is budget pacing. In the carbon-aware mode it is the
opposite: the learned CO2 forecast is what turns shifting from worse than MWh matching into better.

## Gas (real UltraHonk proofs, local chain)

| Call | Public inputs | Forge test | Demo transaction |
|---|---:|---:|---:|
| `submitProof` (coverage) | 170 | 3.93 M | 4.54 M |
| `submitEmissionsProof` (coverage + residual emissions) | 339 | 4.69 M | 5.39 M |

The forge figure is the gas used inside the call; the demo figure is the whole transaction (incl. calldata for
the 8.8 kB proof). Both verifiers' runtimes are 18,145 B, under the 24,576 B EIP-170 limit.

## Verified before building (kill tests, Colab, 14–15 Oct 2026)

| Test | Result |
|---|---|
| Real data, full year 2025 | 8,759 hours; 100 % annual wind → **69.7 %** hourly (75.3 % with wind+solar+hydro) |
| ZK coverage proof, real week | 72.69 % proven in **10.0 s**; Solidity verify **3.14 M gas**; verifier 18,144 B (fits EIP-170) |
| ML-DSA-44 on a real certificate | verified in the EVM, **1.28 M gas**; tampering rejected |
| Cross-registry double claim | reverts; 1,024-run fuzz: reverts **iff** ranges overlap |
| Carbon: CO2 forecast vs persistence | TEST MAE 20.3 vs 38.4 g/kWh, 47 % lower (bar: 30 %) |
| Carbon: shifting by the forecast | −2.47 % location-based emissions; 61 % of the actual-intensity reference (persistence: 15 %) |
| Carbon: ZK residual-emissions proof | real week: coverage ≥ 44.76 %, residual ≤ 1,842.7 t, 6.5 s, cap 1 kg lower refused |

Honest note from K1: Energinet's declaration and settlement series agreed to 0.00 %, because both come
from the same settlement data. They are **not** two independent sources; the oracles are trusted roles.

## Quick start (Linux, macOS, or Windows via WSL2)

```bash
make setup          # pinned forge/cast/anvil/nargo/bb into ~/.hourproof/bin + .venv + builds
make doctor         # everything green?
make data           # real Energinet data for 2025 (first time ~30-50 min: the API rate-limits; cached after)
.venv/bin/python -m hourproof data import-carbon hp_ai   # the carbon kill test's downloads (no network)
make e2e            # backtests, ZK verifiers, real proofs, all tests, both on-chain demos; prints a checklist
make serve          # dashboard on http://127.0.0.1:8000
```

If Energinet answers HTTP 403, your IP is blocked: the client stops instead of retrying (retrying makes a block
worse). Downloaded months stay cached. Ask Energinet to lift it: https://www.energidataservice.dk/support-service

**Skip the 45-minute download:** if your Colab kill-test runtime is still open, download
`/content/hourproof/data/hourly_2025.csv` and run

```bash
.venv/bin/python -m hourproof data import path/to/hourly_2025.csv --branch "Telekommunikation & IT- og informationstjenester"
```

In VS Code: open the folder, accept the recommended extensions, then *Terminal → Run Task* →
`1. setup`, `2. doctor`, `3. fetch real data`, `4. end-to-end`. A dev container is included.

### On Base Sepolia

```bash
make wallet-new         # creates a THROWAWAY key in .env (git-ignored); prints only the address to fund
make preflight-base     # read-only: chain id must be 84532, balances, ETH needed at the live gas price
make demo-base          # same scenario with real proofs; ends with an independent on-chain verification step
make verify-base        # re-check that run later: receipts, contract code, both proofs re-verified on-chain
make live-commit        # after 18:00 Danish time: commit tomorrow's wind forecast, CO2 forecast and shift profile
make live-score         # after that day: reveal and score (CO2 vs Energinet's Initial now, Final when it appears)
```

Role wallets (oracle, issuer ops, buyer, ghost buyer, data hub, investor, agent) are derived from the
master key and topped up from it. The preflight derives each wallet's need from the gas a real local run of the
same mode and week used, at the fee cap `cast` may charge, with a 3× margin (about 0.004 ETH at 0.006 gwei; one run
spent 0.000685 ETH). It sends nothing unless the master wallet covers all of it, and re-reads every balance after
funding. `make verify-evidence` re-checks the committed public run without any key.

## What `make e2e` checks

1. `doctor`: toolchain, packages, network
2. Python tests: agent and CO2-feature leakage guards, policy invariants, the carbon 0.5 % regression test,
   live-mode scoring, EDS client (backoff, cache, fatal 403), ML-DSA, ZK maths, both local scenarios, and the
   public-chain safeguards (no key in any output, no duplicate transactions, sealed-block reads on a Flashblocks-like
   RPC, bounded retries through network outages, fail-closed funding)
3. Noir tests. Coverage: exact, 1 bp over-claim refused, surplus never counts. Emissions: exact cap, cap 1 kg
   lower fails, threshold 1 bp higher fails, surplus never counts, zero-intensity hours, rounding, and the
   commitment equals `load_commit`'s
4. Procurement agent walk-forward backtest on real data
5. Carbon backtest on real data with the frozen choices
6. `zk build`: both Solidity verifiers generated from the circuits, EIP-170 checked
7. `zk fixture`: a real coverage proof and a real emissions proof over real weeks
8. Solidity tests: ledger, registries, claims, intensity oracle (unit + fuzz), emissions inputs, both note
   KPIs, agent log, **real ML-DSA** (ffi) and **real UltraHonk** for both circuits (fixtures)
9. The original demo (procurement mode): 12 steps, 5 attacks that must all be refused
10. The carbon-aware demo: 15 steps, 8 attacks that must all be refused

## The demo scenario (carbon-aware, `python -m hourproof demo`)

1. Deploy 15 contracts (local anvil replay chain, clock set two days before the replayed week); the note's
   residual-emissions target is set by a rule written in code before the run (the mean of the 4 weeks that
   ended at least a week before the window)
2. The agent commits its 7 daily plans (certificate purchases, CO2 forecast, planned shift) before each day
3. The oracle posts the week's metered production (wind, and other clean) and the hourly grid intensity
4. Issuer A issues the buyer's hourly certificates: one ML-DSA-signed batch per day
5. The buyer opens a claim and cancels every certificate into it
6. **Attacks**: registry B re-sells MWh already claimed → `SliceAlreadyClaimed`; issuance beyond production →
   `ExceedsProduction`; impersonated issuer → `BadIssuerSignature`
7. The data hub attests ONE commitment to the buyer's hourly load (it serves both proofs)
8. The buyer proves coverage ≥ 75 %; **attacks**: 1 bp above the truth → the prover refuses; the proof
   resubmitted for more → `ProofRejected`
9. The buyer proves residual emissions ≤ its true value (rounded up to a kg); **attacks**: 1 kg lower → the
   prover refuses; the oracle re-posts an hour cleaner → `AlreadyPosted`; a valid proof on a 30 % cleaner fake
   intensity vector → `ProofRejected` (the contract rebuilds the vector from the oracle)
10. The note settles on the proven residual, the issuer funds the coupon, the investor claims it
11. The agent reveals its plans; the chain checks them against the commitments

In the last run (week of 2025-11-10) the buyer proved residual ≤ 546.1 t against a target of 428.5 t from
the rule, so the KPI was missed and the coupon stepped up to 6 %. The rule's four reference weeks ranged
from 47 t to 1,071 t, because the residual depends heavily on the wind. `--mode procurement` runs the
original coverage-only scenario.

## Deploy the dashboard (Vercel)

The hosted dashboard is a **static snapshot of the verified Base Sepolia run**: the same `web/` frontend, reading three
JSON files exported by the dashboard's own API code from `evidence/`. It cannot start runs (`make serve` runs the full
dashboard locally, with the run buttons). No secrets, data files or keys are uploaded: `.vercelignore` allows only
`web/`, `deploy/`, `scripts/build_site.sh` and `vercel.json`.

```bash
make site                       # python -m hourproof site export (-> deploy/snapshot/*.json) + bash scripts/build_site.sh
npx vercel login                # once
npx vercel deploy               # preview: Vercel runs scripts/build_site.sh and serves site/ (see vercel.json)
npx vercel deploy --prod        # production, after checking the preview
```

Or import the GitHub repository in the Vercel dashboard: `vercel.json` sets the build command, the output directory
and the `/api/*` rewrites; no environment variables are needed.

## Layout

```
contracts/   Foundry: src/ (8 contracts; generated verifiers are built by `make zk`), test/ (unit, fuzz, ML-DSA ffi,
             UltraHonk fixtures), lib/ (vendored forge-std and evm-ml-dsa-verifier, with their licences)
circuits/    Noir workspace: hp_lib (shared commitment), coverage, emissions, load_commit (data hub)
hourproof/   Python: eds, dataset, agent, carbon, zk, pq, chain (cast), demo, live, verify, site, server, CLI
web/         Dashboard frontend (no build step)
tests/       Python unittest suite
docs/        SECURITY.md (threat model), ARCHITECTURE.md, AGENT_RESULTS.md, CARBON_RESULTS.md, BASE_SEPOLIA.md
evidence/    The verified Base Sepolia run (state, plans, submitted proofs, verification logs) and the two failed attempts
data/        Frozen choices and results only (agent_config.json, experiment records, backtest summaries, the two
             processed hourly datasets); raw downloads, keys and run logs stay local
hp_ai/       Carbon kill-test inputs: hourly dataset, price downloads (for `data import-carbon hp_ai`), results, circuit
deploy/      Static dashboard snapshot (deploy/snapshot/*.json); vercel.json, .vercelignore at the root
notebooks/   The carbon kill test
scripts/     install_tools.sh (pinned toolchain), check_public_run.py (independent cast-only checker), build_site.sh
```

## Data and licences

Energi Data Service (Energinet), keyless public API: `DeclarationProduction`, `ConsumptionDK3619IndustryHour`,
`Forecasts_Hour`, `ProductionConsumptionSettlement`, `DeclarationGridEmission` (Final; live: Initial),
`Elspotprices` (to 2025-09-30) and `DayAheadPrices` (from 2025-10-01). The processed hourly datasets in `data/`
and `hp_ai/` are derived from Energinet's open data (credit: Energinet, Energi Data Service). Vendored code keeps its
own licences: forge-std (MIT or Apache-2.0), evm-ml-dsa-verifier (MIT, Fireblocks, unaudited). The Solidity verifiers
that `bb` generates (Apache-2.0, Aztec) are not committed; `make zk` builds them. This repository: MIT.
