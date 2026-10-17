# Carbon-aware mode: results

Real Energinet data for 2025. The buyer is the Danish IT and telecom sector (DK36 branch JB_JC). A learned
day-ahead forecast of Denmark's hourly grid CO2 intensity decides which hours the buyer's flexible load
moves into. Each plan is made at D-1 17:30 UTC from the forecast and last week's load. The outcome is scored
on the actual load and actual intensity.

**Periods.** TRAIN 2025-01-01..03-31 · VALIDATION 2025-04-01..06-30 (the only place a choice was made) · TEST
2025-07-01..12-30, 183 complete days. 31 Dec has no intensity for 23:00, so it is not a complete day. TEST was run
once, in the carbon kill test (`notebooks/HourProof_carbon_killtest (1).ipynb`). `python -m hourproof agent carbon`
reruns the same frozen procedure in this repository; the numbers below are that rerun, next to the kill test.

## Frozen choices (`data/agent_config.json` → `carbon`)

| Choice | Value | How it was set |
|---|---|---|
| Day-ahead price features | `use_price = true` | VALIDATION MAE 21.65 g/kWh with prices vs 23.82 without (kill test; rerun here: 21.65 vs 23.90) |
| Flexible share of each hour's load | 10 % (`FLEX = 0.10`) | Declared scenario parameter, fixed in advance (same as the procurement agent) |
| Hourly cap | no hour above +25 % of its own load (`CAP = 0.25`) | Fixed in advance |
| Shifting window | within the same UTC day | Fixed in advance |
| Load forecast | last week's value (`lag168`) | Fixed in advance |
| Intensity model | `HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, random_state=0)` | Fixed in advance |
| Retraining | monthly walk-forward; month M trains on hours before M − 6.5 h (D-1 17:30 UTC) | Fixed in advance |

Features: Energinet's day-ahead forecasts by price area and type (`Forecasts_Hour` ForecastDayAhead: DK1/DK2 ×
offshore wind, onshore wind, solar) and their wind total; hour, weekday, month, Danish holiday; intensity
48, 72 and 168 h earlier and the mean of the same hour 2..8 days earlier; the day-ahead price, its rank within
the day and its distance from the day's mean.

Intensity: `DeclarationGridEmission` CO2PerkWh, Version "Final", FuelAllocationMethod "125%", DK1 and DK2 weighted
by `ProductionConsumptionSettlement` GrossConsumptionMWh. Prices: `Elspotprices` SpotPriceEUR up to 2025-09-30, then
`DayAheadPrices` DayAheadPriceEUR averaged over each hour's quarter-hours (mean of DK1 and DK2).

## Results (TEST, Jul-Dec 2025)

**CO2-intensity forecast, mean absolute error (g/kWh), 4,415 hours**

| Forecast | This repo | Kill test |
|---|---:|---:|
| Learned model | **20.30** | 20.28 |
| Same hour last week (lag168) | 38.36 | 38.36 |
| Same hour two days earlier (lag48) | 41.41 | 41.41 |

The learned forecast's error is **47 % lower** than the best persistence baseline (last week).

**Buyer's location-based emissions, 4,392 hours**

| Strategy | Emissions, t | Kill test, t | Reduction vs no shift | Residual (unmatched) emissions, t | Hourly coverage |
|---|---:|---:|---:|---:|---:|
| No shift | 48,840.2 | 48,840.2 | — | 21,837.2 | 70.45 % |
| Shift for MWh matching | 47,889.1 | 47,889.1 | 1.95 % | 20,776.9 | 71.47 % |
| Carbon-aware, persistence forecast | 48,546.5 | 48,546.5 | 0.60 % | 21,737.8 | 70.03 % |
| **Carbon-aware, learned forecast** | **47,633.8** | 47,631.7 | **2.47 %** | 20,598.0 | 71.34 % |
| Carbon-aware, actual intensity (reference) | 46,856.5 | 46,856.5 | 4.06 % | 20,071.8 | 71.37 % |

- Shifting 10 % of the sector's load by the learned forecast cuts its location-based emissions by **2.47 %**,
  about **1,206 t** in six months (kill test: 1,208 t). That is 61 % of the reduction the actual intensity would give.
- With the persistence forecast, carbon-aware shifting cuts only **0.60 %**. That is worse than simply shifting for
  MWh matching (1.95 %). With the learned forecast it is better (2.47 %).
- Hourly coverage with the learned forecast is 0.14 points below MWh-matching shifting (kill test: 0.11).
- "Carbon-aware, actual intensity" uses the realised intensity. It is a reference, not something a planner can do.

**Reproduction.** Every number is within 0.5 % of the kill test (`tests/test_carbon.py` enforces it). The four
strategies that do not use the learned model match to the tonne. The learned model differs slightly: TEST MAE
+0.13 %, emissions +0.004 %. The likely cause is a different scikit-learn/NumPy build: here scikit-learn 1.9.1,
NumPy 2.5.4 and pandas 3.0.6, against the kill test's Colab runtime. No choice was changed.

## Robustness (reported only; never used to choose anything)

Weekly block bootstrap: 27 blocks of 7 consecutive TEST days (the last one has 1 day), 2,000 resamples, seed 0.
Percentile 95 % intervals.

| Difference in emission reduction | Point | 95 % CI | Tonnes (95 % CI) | Resamples > 0 |
|---|---:|---:|---:|---:|
| Learned forecast − MWh shifting | +0.52 pp | [+0.22, +0.83] pp | 255 t [106, 400] | 100 % |
| Learned forecast − persistence forecast | +1.87 pp | [+1.41, +2.44] pp | 913 t [695, 1,162] | 100 % |

Both intervals exclude zero. They describe week-to-week variation inside this half-year only. They say nothing
about other periods.

## Residual emissions in zero knowledge

`circuits/emissions` proves coverage ≥ τ **and** `Σ (load − min(load, cert)) · intensity ≤ cap_kg · 1000` (grams).
Load is private, and the certificates and the hourly intensity (whole g/kWh) are public. Its output is
`hp_lib::commit_load(load, salt)`, the same commitment the coverage circuit outputs, so one data-hub attestation
serves both proofs. A Noir test checks that this equals the kill test's inline Pedersen form.

| Kill test's week from 2025-08-12 (real data, unshifted load, base certificates) | This repo | Kill test |
|---|---:|---:|
| Coverage threshold proven | 44.76 % | 44.76 % |
| Residual cap proven | 1,842.7 t (1,842,741 kg) | 1,842.7 t |
| Cap 1 kg lower | refused by the prover | refused |
| Circuit size | 62,243 gates | 62,240 gates |
| Proving time | 1.3–1.7 s (WSL) | 6.5 s (Colab) |
| `submitEmissionsProof` gas (339 public inputs) | 4.69 M in the forge test, 5.39 M as a demo transaction | — |

The 3 extra gates come from `assert(threshold_bps <= 10000)`, kept for parity with the coverage circuit.
`ClaimManager` rebuilds all 339 public inputs itself: threshold, cap, the claim's certificates, the intensity
read from `IntensityOracle` (write-once, at most 2,000 g/kWh), and the attested commitment.

## On-chain demo (carbon-aware, week of 2025-11-10)

The same demo-week rule as the procurement demo. The buyer's load follows the committed carbon plans, and the
procurement agent's certificate purchases are kept. Private values, shown here because this is a demo:
residual 615.8 t with no shift, 562.2 t with the procurement agent's MWh shift, and **546.1 t with the carbon
shift**. Proven on-chain: residual ≤ 546.1 t and coverage ≥ 75.00 %. The CO2 forecast's error that week was
15.6 g/kWh, against 40.5 for last week's value.

The note's target is set by a rule written in code before any run (`demo.RESIDUAL_TARGET_RULE`): the mean
residual of the 4 complete weeks that ended at least one week before the window. Here that gave 428.5 t.
The KPI was **missed**, so the coupon stepped up from 5 % to 6 %. The four reference weeks ranged from 47 t to
1,071 t: the weekly residual depends mostly on the wind, so a rule like this is a coin toss week by week.
The result is reported as it came out; the rule was not changed.

## Live mode

`live commit` adds to the committed plan tomorrow's 24 CO2 forecasts, the lag168 persistence forecast (as the
baseline, fixed at commit time) and the planned shift profile. The model is trained on the Final dataset.
The lag features use Energinet's **Initial** version, which is published within about 2 hours. Two deviations
from the backtest, both forced by what is published:

- **Load forecast.** The frozen choice is last week's load, but Energinet's industry consumption feed is paused,
  so live mode has no load. The shift is committed as a share of each hour's own load: the same planner run on a
  flat load profile. The IT sector's load varies by about ±5 % within a day, so the hours chosen are nearly the same.
- **DK1/DK2 weights.** `ProductionConsumptionSettlement` is published about 10 days late (checked 16 Oct 2026:
  it ended at 6 Oct), so each hour is weighted by the same hour n whole weeks earlier, using the smallest n
  that has data. The plan records the n used.

`live score` adds the CO2 MAE of the model and of persistence against Initial as soon as the day is complete.
It adds Final when Energinet publishes it, and records the version and weights used each time.

## Caveats

- **Average, not marginal.** These are average, location-based grid factors (Energinet's declaration, 125 %
  method) for a buyer's accounting. They are not marginal emissions, and nothing here claims physically avoided emissions.
- **The 10 % flexibility is a scenario parameter.** It is declared, not measured. The same holds for the +25 % hourly cap.
- **One test half-year.** Jul-Dec 2025 only. No claim that the results generalise beyond it.
- **Unmatched hours use the hourly grid average,** not a residual-mix factor.
- **Final data used as if available in time.** Training and the lag features use Energinet's Final declaration.
  Final is published later. Live mode therefore uses the Initial version for the lag features (published within
  about 2 hours) and keeps training on Final.
- **Settlement wind for the portfolio.** As in the kill test, the buyer's fixed portfolio is sized on settlement
  wind (`ProductionConsumptionSettlement`), from `data/carbon_hourly.csv`. The procurement agent uses declared wind
  from `data/hourly.csv`, and that file is untouched. The two portfolio shares differ by 0.002 %.
- Nothing here is audited.

## Reproduce

```bash
python -m hourproof data import-carbon hp_ai   # reuse the kill test's downloads (no network)
# or: python -m hourproof data fetch-carbon    # download with the cached, rate-limit-aware client
python -m hourproof agent carbon               # -> data/carbon_backtest.json, data/carbon_backtest.hours.csv,
                                               #    data/carbon_plans/<day>.json
python -m unittest tests.test_carbon           # the 0.5 % regression test (+ the K4 week's proof inputs)
python -m hourproof zk build && python -m hourproof zk fixture   # both verifiers; real proofs incl. the K4 week
python -m hourproof demo                       # the carbon-aware on-chain demo
```

`make e2e` runs all of these.
