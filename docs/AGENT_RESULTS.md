# Agent results: v1 vs v2

Real Energinet data for 2025, Danish IT/telecom sector as the buyer. Walk-forward with monthly retraining;
decisions use only what was known at D-1 17:30 UTC.

**Periods.** TRAIN 2025-01-01..03-31 · VALIDATION 2025-04-01..06-30 (91 days) · TEST 2025-07-01..12-30 (183 days;
31 Dec has 23 hours in the data and is not a full day). Every v2 choice was made by walk-forward results on
VALIDATION by `agent.select_config`, which drops every row at or after 2025-07-01 as its first statement. The
TEST period was then run **once** with the frozen configuration.

**Headline (TEST).** The agent's hourly coverage goes from **74.20 % (v1) to 75.69 % (v2)**, +1.49 points. Against
a bigger portfolio given exactly the same extra MWh, the gain goes from **+2.88 to +3.97 points**. Almost all of
the improvement comes from one fix, budget pacing (A). It lets the agent spend budget that v1 let expire at
midnight: 4.81 % of test load bought, against 3.23 %. The other four fixes are within noise on validation,
individually and together. **The learned models add little:** with Energinet's raw forecast and last week's
load instead of any model, the same planner reaches 75.28 % on TEST, against 75.69 % for v2 (section 3b).

## 1. v1 vs v2 on the TEST period

| Metric (TEST, 183 days) | v1 | v2 | v2 - v1 |
|---|---:|---:|---:|
| Naive fixed portfolio | 70.45 % | 70.45 % | +0.00 pp |
| Bigger portfolio, same MWh | 71.32 % | 71.72 % | +0.41 pp |
| Agent: shifting only | 71.32 % | 71.44 % | +0.13 pp |
| **Agent: shifting + buying** | **74.20 %** | **75.69 %** | **+1.49 pp** |
| Perfect-foresight reference (each version's own policy and budget rule) | 75.29 % | 76.73 % | +1.44 pp |
| Extra certificates bought, share of test load | 3.23 % | 4.81 % | +1.57 pp |
| Extra certificates bought, MWh | 28,195 | 41,930 | +13,735 |
| **Gain vs bigger portfolio with the same MWh** | **+2.88 pp** | **+3.97 pp** | **+1.09 pp** |
| Gain vs naive | +3.75 pp | +5.24 pp | +1.49 pp |
| Wind MAE, published day-ahead forecast (MWh/h) | 514.33 | 514.33 | |
| Wind MAE, agent's point forecast (MWh/h) | 411.31 | 381.79 | -29.52 |
| Load MAE, the load forecast the agent used (MWh/h) | 2.27 (v1 model) | 2.33 (selector) | +0.06 |
| Load MAE, last week's value (MWh/h) | 2.09 | 2.09 | |
| Load MAE, v2 residual model alone (MWh/h) | n/a | 2.51 | |
| Load MAE, v2 selector (MWh/h) | n/a | 2.33 | |
| Wind pinball loss, v2 quantile models (MWh/h) | n/a | q0.25: 157.20 · q0.5: 190.21 · q0.75: 165.05 | |

How to read this table:

- **The perfect-foresight reference changed, and it should be compared within a version, not across.** It runs
  the *same* policy family under the *same* budget rule as the agent, fed with actual values. v1's reference is
  the greedy planner with a daily budget that expires at midnight. v2's is the per-day LP with the rolling
  budget at α = 5. The reference rose by 1.44 points mainly because the budget rule now lets the budget be spent.
  The agent stays below its own reference in both versions (v1 1.09 points under, v2 1.04 points under).
- **The bigger-portfolio baseline rose too (+0.41 points),** because it always receives exactly the
  realised extra MWh the agent bought, and v2 bought more. That is why the fair comparison is "gain vs the
  same MWh": +2.88 → +3.97 points.
- **Budget accounting.** The test budget is 232.0 MWh/day × 183 days = 42,459 MWh, which is 4.87 % of test
  load (5 % of annual load per year, unchanged). v2 bought 41,930 MWh, 98.8 % of it. Cumulative purchases
  never exceeded the cumulative budget (maximum overspend over the run: 4.5e-13 MWh, floating-point noise).
- **v1 column check.** After the v2 configuration was frozen and its TEST run done, the v1 configuration was
  re-run on TEST with the new code. All five coverages and the extra MWh came out bit-identical to
  `data/agent_backtest_v1.json`.

## 2. The frozen configuration and how it was chosen

`data/agent_config.json` (frozen 2026-10-14 20:33:49 UTC, validation 2025-04-01..06-30):

| Choice | Frozen value | Searched on validation |
|---|---|---|
| Planner (E) | `lp`: stochastic linear program, HiGHS | `greedy` (v1), `lp` |
| Pacing α (A) | `5` | 1 (= v1), 1.5, 2, 3, 5, 7 |
| Load forecast (B) | `selector`: residual model or last week, re-chosen each month | `lag168`, `selector` (eligible); `v1_gbr`, `residual` (ablation only) |
| Wind features (C) | `area_type`: DK1/DK2 × offshore/onshore day-ahead forecasts + v1 features | `total` (v1), `area_type` |
| Wind quantiles (D) | {0.25, 0.5, 0.75}, three equally weighted scenarios | none (point model, v1), {0.5}, {0.25,0.5,0.75}, {0.1,0.5,0.9}, {0.1,0.3,0.5,0.7,0.9} |

Fixed and not searched: the scenario parameters flex_share 0.10, flex_cap 0.25 and topup_share 0.05; shifting
only within the same UTC day; the balance cap of 7 days of budget; the gradient-boosted-tree hyperparameters
(v1's values, unchanged); the selector look-back of 2 months.

**Selection rule.** Maximise validation coverage (agent, shifting + buying). Ties go to the simpler candidate,
meaning the earlier one in the grid. Eligible: load forecast `selector` or `lag168` whose validation MAE is no
worse than last week's. Grid: 2 × 6 × 4 × 2 × 5 = 480 candidates, 240 eligible, all in
`data/agent_experiments.json`.

**Validation numbers of the frozen config:** agent 70.53 % (v1: 69.23 %), naive 65.02 %, bigger portfolio with
the same MWh 66.68 %, shifting only 66.31 %, reference 72.14 %; extra certificates 4.85 % of validation load; gain vs
the same MWh +3.85 points; load MAE 1.69 MWh/h (last week 1.85, so the guarantee held on validation); wind point
MAE 359 MWh/h. The selector chose last week for April and May and the residual model for June.

Top of the ranking (eligible only). The top candidates are separated by at most 0.02 points, so the exact
winner among them is not meaningful:

| Rank | Config | Validation coverage | Reference |
|---:|---|---:|---:|
| 1 | `lp, α=5, selector, area_type, q=0.25/0.5/0.75` (frozen) | 70.53 % | 72.14 % |
| 2 | `lp, α=7, selector, area_type, q=0.25/0.5/0.75` | 70.53 % | 72.14 % |
| 3 | `lp, α=3, lag168, total, q=0.1/0.5/0.9` | 70.53 % | 72.12 % |
| 4 | `lp, α=5, lag168, total, q=0.1/0.5/0.9` | 70.53 % | 72.14 % |
| 6 | `lp, α=5, lag168, area_type, q=0.25/0.5/0.75` | 70.52 % | 72.14 % |
| 8 | `lp, α=5, selector, total, q=0.25/0.5/0.75` | 70.51 % | 72.14 % |

Best eligible validation coverage by pacing α (the main effect):

| α | greedy | lp |
|---:|---:|---:|
| 1 (= v1 budget) | 69.39 % | 69.90 % |
| 1.5 | 70.10 % | 70.48 % |
| 2 | 70.31 % | 70.51 % |
| 3 | 70.43 % | 70.53 % |
| 5 | 70.47 % | 70.53 % |
| 7 | 70.47 % | 70.53 % |

**The selection was frozen twice. Both freezes happened before any TEST run.** The first freeze let all
four load predictors compete and picked the bare `residual` model (70.54 %, 0.005 points above the selector).
That did not match the brief, which specifies the selector, with its last-week guarantee, as v2's load
forecast. So before running TEST I restricted eligibility to `selector` and `lag168` and re-ran the
selection. All 480 validation results were identical in both runs; only eligibility changed. The first
freeze is kept for audit as `data/agent_config_freeze1_superseded.json` and
`data/agent_experiments_freeze1_superseded.json`. `data/agent_backtest.json` was still the v1 file at that
point; no TEST evaluation had run.

## 3. What helped and what did not (ablation, VALIDATION)

Each fix alone on top of v1 (v1 = greedy, α=1, v1 load model, summed forecast, point wind model):

| Fix alone | Config | Validation coverage | vs v1 |
|---|---|---:|---:|
| v1 | `greedy, α=1, v1_gbr, total, mean` | 69.23 % | |
| **A pacing** (best α = 5) | `greedy, α=5, …` | 70.31 % | **+1.08 pp** |
| B residual load model | `greedy, α=1, residual, …` | 69.26 % | +0.03 pp |
| B selector | `greedy, α=1, selector, …` | 69.26 % | +0.03 pp |
| B last week only | `greedy, α=1, lag168, …` | 69.29 % | +0.06 pp |
| C wind by area/type | `greedy, α=1, …, area_type` | 69.15 % | -0.07 pp |
| D quantiles (best set; greedy uses only the median) | `greedy, α=1, …, q=0.5` | 69.34 % | +0.11 pp |
| E LP (point forecast) | `lp, α=1, …` | 69.11 % | -0.11 pp |

Cumulative, in the order A → E (each step keeps the earlier choices and takes the best value of the new one):

| Step | Config | Validation coverage | vs previous step |
|---|---|---:|---:|
| v1 | `greedy, α=1, v1_gbr, total, mean` | 69.23 % | |
| + A pacing | `greedy, α=5, v1_gbr, total, mean` | 70.31 % | +1.08 pp |
| + B load selector | `greedy, α=5, selector, total, mean` | 70.40 % | +0.08 pp |
| + C wind area/type | `greedy, α=5, selector, area_type, mean` | 70.27 % | -0.12 pp |
| + D quantiles | `greedy, α=5, selector, area_type, q=0.5` | 70.33 % | +0.06 pp |
| + E LP (median only) | `lp, α=5, selector, area_type, q=0.5` | 70.30 % | -0.03 pp |
| + E LP with quantile scenarios re-chosen | `lp, α=5, selector, area_type, q=0.25/0.5/0.75` | 70.53 % | +0.23 pp |

Verdict:

- **A, budget pacing: helped clearly.** It accounts for +1.08 of the +1.30 validation points. On TEST, the
  extra-MWh share rose from 3.23 % to 4.81 % and the gain vs the same MWh rose by 1.09 points.
  Most of the benefit arrives by α = 2–3; 5 and 7 add little.
- **E + D, the LP with wind scenarios: small help, and only together.** The LP with a single point
  forecast is no better than greedy (-0.11 / -0.03 points). With three quantile scenarios it adds about +0.2
  points, because it can buy where wind is uncertain. That is about 0.2 points on 91 days and could be noise.
- **B, the load model: no meaningful effect on coverage.** Every load variant is within 0.1 points. The
  selector's guarantee held on validation (1.69 vs 1.85 MWh/h) but **not on TEST** (2.33 vs 2.09). In
  September it kept the residual model, which had won in July–August, and that month was bad (MAE 3.82 vs 1.80
  for last week); it switched to last week from October. The residual model alone was worse still on TEST
  (2.51). Unchanged from v1: the learned load models do not beat last week's value out of sample.
- **C, wind by area/type: no measurable help to coverage on its own** (-0.07 points alone). The agent's wind
  point error did improve on TEST (411 → 382 MWh/h), but that comes from this feature set *and* the median
  (quantile-loss) model together; no separate TEST ablation was run, by design.

## 3b. What the ML contributes (TEST, frozen config)

The frozen v2 configuration, run on TEST with one part swapped out each time. Nothing was re-selected or
retuned. These runs happened after the freeze, for reporting only: `python -m hourproof agent ablate`, results
in `data/agent_ml_ablation.json`. "Raw forecast" means Energinet's published ForecastDayAhead used directly as
a single point scenario (v1's filling for the 192 missing hours), with no wind model and no quantiles. The LP
planner, α = 5 pacing and the rolling budget stay the same in every row.

| TEST, 183 days | Agent coverage | Gain vs same MWh | Extra MWh, share of test load | vs v2 |
|---|---:|---:|---:|---:|
| **v2 (frozen):** wind model + quantiles, load selector | **75.69 %** | **+3.97 pp** | 4.81 % | |
| (1) wind = raw day-ahead forecast | 75.30 % | +3.58 pp | 4.80 % | -0.39 pp |
| (2) load = last week's value | 75.67 % | +3.95 pp | 4.81 % | -0.02 pp |
| (3) both: no learned model at all | 75.28 % | +3.56 pp | 4.81 % | -0.41 pp |
| *v1, for reference* | *74.20 %* | *+2.88 pp* | *3.23 %* | *-1.49 pp* |

In every row the bigger-portfolio comparator is 71.72 %, because the extra MWh bought are the same to within
0.01 % of load. The perfect-foresight reference is 76.73 %; it uses actual values, so it does not depend on the
forecasts.

**The ML adds little.** Removing every learned model costs 0.41 points of coverage. The gain vs the same MWh
drops from +3.97 to +3.56 points: about 90 % of v2's advantage over the comparator needs no machine learning.
It comes from shifting flexible load, buying into the hours with the largest forecast shortfall, and pacing
the budget, all driven by Energinet's own published forecast. The no-ML variant (75.28 %) already beats v1
(74.20 %) by more than the whole ML contribution. Of the 0.41 points:

- **Wind model and quantile scenarios: +0.39 points.** The model cuts the wind error from 514 to 382
  MWh/h. In coverage terms that is worth under half a point.
- **Load selector: +0.02 points,** which is noise. Its forecast is worse than last week's on TEST (2.33 vs
  2.09 MWh/h). Coverage is insensitive to load error at this level, because flexibility is only 10 % of load.

This is a single half-year with no confidence intervals. A 0.4-point difference should not be presented as
a robust effect of the models.

## 4. Honest caveats

- **One test half-year.** 183 days, July–December 2025, one buyer, one year. There are no confidence
  intervals. Validation is a single spring quarter (91 days), a different season from the test period.
  Among the top validation candidates the differences are about 0.02 points, below anything this design can
  resolve. Of the fixes, only pacing (A) has an effect large enough to call real.
- **Much of the raw gain is spending budget, not forecasting.** v2 spends the budget v1 let expire. That is
  a legitimate policy improvement, and the comparator is given the same MWh. Still, the coverage figure alone
  (+1.49 points) overstates the planning gain. Quote "gain vs the same MWh" (+3.97 points, v1 +2.88).
- **Fixed scenario parameters.** flex_share 10 %, flex_cap 25 % and topup_share 5 % are declared assumptions,
  not measured flexibility, and were not changed or tuned. Results depend on them.
- **The perfect-foresight reference applies to each version's own policy, and is approximate.** It runs the same
  daily policy under the same rolling budget with actual values. Under a rolling budget a day-by-day reference
  is not a strict mathematical maximum over the half-year. Also, as in v1, an executed shift is capped
  by flex_cap times *predicted* load, which can slightly exceed flex_cap times actual load. The agent stayed
  below its reference in every run reported here.
- **Budget timing is as-of.** Each plan reserves its planned purchases at decision time. Purchases that
  could not be made are refunded only after the day has ended, so they become usable two decisions later.
  No plan depends on a day that has not finished; a unit test checks this.
- **Assumptions inherited from v1, not changed:**
  - The day-ahead wind forecast is taken to be published by 18:00 Danish time. The dataset cannot verify
    this, because its `TimestampUTC` field records the last update, not the day-ahead issue time.
  - Models are retrained on Energinet's *Final* declared production up to the decision time. In reality
    Final data is published later. This is a data-availability idealisation and affects v1 and v2 equally.
  - The portfolio share k and the daily budget are computed from the full year's load, as in v1, for the
    TEST run. Inside `select_config` they are computed from January–June only.
- **Data quirks.** 192 hours of 2025 have no day-ahead wind forecast; v1's filling is kept. In 24 further
  hours the onshore forecast is missing, so the summed forecast in those hours is offshore only. This is
  inherited, and the area/type features leave those values missing for the trees to handle.
- **A latent v1 issue, fixed.** When load features still had gaps after forward-filling, v1 filled them with
  that day's *actual* mean load. This never happened in validation or test (0 days), so v1's numbers are
  unaffected. v2 fills with the training mean.
- **Fix F (external weather forecasts, Open-Meteo "previous runs") was skipped.** It would have had to join
  the candidate pool before the freeze, and I could not prove it leakage-free. That API indexes values by
  lead day, not by the issue time of each model run. So I cannot show, hour by hour and including run
  processing delays, that every value used for day D was available before D-1 17:30 UTC.
- **The on-chain agent ID is unchanged.** Plan files keep `"agent": "hourproof-agent-v1"`, because the demo
  commits that identifier, and add `"version": "v2"`, `"config"`, `"budget_balance_mwh"` and
  `"spend_cap_mwh"`.

## 5. Effect on the end-to-end demo

`make e2e` with v2 passes 8/8: 32 Python tests (15 existing, 17 new), 5 Noir and 48 Solidity tests with 0
skipped, and the demo with 5/5 attacks blocked. The ablation in section 3b added one more test (raw forecast
= published forecast only); the Python suite now has 33 tests, all passing. Its backtest step re-ran TEST with the frozen config and
reproduced the outputs bit-identically: same SHA-256 for `agent_backtest.json`, `.hours.csv` and all plan
files.

The demo replays a representative week: the one whose agent coverage is closest to the median weekly
coverage of the test period. With v2 that is the week of **2025-11-10**: agent 77.80 % (private), naive
70.63 %. The proof is for ≥ 75.00 %, the note's target, so the note **meets its KPI** and pays the 5.00 %
base coupon. With v1 it was the week of 2025-09-22 at 74.84 %, which missed the target and triggered the
step-up. These are single-week figures; the half-year results are in section 1.

## Reproduce

```bash
python -m hourproof data fetch          # adds the DK1/DK2 x offshore/onshore forecast columns (from cache)
python -m hourproof agent select        # validation only; writes data/agent_config.json + agent_experiments.json
python -m hourproof agent backtest      # TEST with the frozen config; writes agent_backtest.json, .hours.csv, plans
python -m hourproof agent ablate        # TEST ablations of the frozen config (section 3b); agent_ml_ablation.json
python -m unittest discover -s tests -t .
```

`agent select` refuses to overwrite a frozen config unless `--force` is given. v1's outputs are preserved
read-only in `data/agent_backtest_v1.json`, `data/agent_backtest_v1.hours.csv` and `data/agent_plans_v1/`.
