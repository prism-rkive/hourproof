"""Carbon-aware mode: a learned day-ahead forecast of Denmark's hourly grid CO2 intensity steers the buyer's
flexible load into cleaner hours.

Ported from the carbon kill test (notebooks/HourProof_carbon_killtest (1).ipynb, cells 4-5); every choice
below was made there on VALIDATION (Apr-Jun 2025) and is frozen in data/agent_config.json under "carbon".
TEST (Jul-Dec 2025) is the one reported run. Nothing here may be re-chosen on TEST.

  * intensity: DeclarationGridEmission CO2PerkWh (Final, 125 %), DK1/DK2 weighted by gross consumption (g/kWh)
  * forecast:  gradient-boosted trees on Energinet's day-ahead wind/solar forecasts by area and type, calendar,
               intensity lags >= 48 h, and (frozen: use_price=True) the day-ahead price and its rank in the day.
               Walk-forward: the model for month M is trained on hours before M - 6.5 h (D-1 17:30 UTC).
  * shifting:  FLEX = 10 % of each hour's load may move within the same UTC day, no hour above +25 %; the plan
               uses only the forecast and last week's load; the outcome uses the actual load and intensity.
  * strategies: no_shift, shift_for_mwh (the MWh-matching shift), carbon_persist (intensity a week ago),
               carbon_model (the learned forecast), carbon_perfect (the actual intensity; a reference, not a plan).
Emission factors are AVERAGE, location-based grid factors for a buyer's accounting, not marginal emissions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .agent import DK_HOLIDAYS
from .config import AGENT_CONFIG_JSON, CARBON_BACKTEST_JSON, CARBON_PLANS_DIR

CARBON_AGENT_ID = "hourproof-carbon-v1"
VAL_START, TEST_START, TEST_END = pd.Timestamp("2025-04-01"), pd.Timestamp("2025-07-01"), pd.Timestamp("2026-01-01")
STRATEGIES = ("no_shift", "shift_for_mwh", "carbon_persist", "carbon_model", "carbon_perfect")
PRIORITY = {"no_shift": None, "shift_for_mwh": "mwh", "carbon_persist": "I_persist", "carbon_model": "I_model",
            "carbon_perfect": "I_perfect"}

# The choices frozen on VALIDATION in the kill test (notebook cell 4: MAE 23.82 without, 21.65 with prices).
FROZEN = {
    "use_price": True,
    "flex_share": 0.10,
    "flex_cap": 0.25,
    "load_forecast": "lag168",
    "model": {"kind": "HistGradientBoostingRegressor", "max_iter": 400, "learning_rate": 0.05, "max_leaf_nodes": 31,
              "l2_regularization": 1.0, "random_state": 0},
    "retrain": "monthly walk-forward; the model for month M is trained on hours before M - 6.5 h (D-1 17:30 UTC)",
    "train_cutoff_hours": 6.5,
    "selected_on": ["2025-04-01", "2025-07-01"],
    "selection_rule": "use_price = (walk-forward VALIDATION MAE with prices < without); everything else fixed in advance",
    "validation_mae_g_per_kwh": {"use_price_false": 23.821407172429762, "use_price_true": 21.654475678856883},
    "source": "carbon kill test notebook, real Energinet data; TEST Jul-Dec 2025 run once",
}

# The kill test's TEST results, reproduced by `agent carbon` (tests/test_carbon.py checks 0.5 %).
KILLTEST_REFERENCE = {
    "mae": {"model": 20.277003240953952, "lag168": 38.36066062105363, "lag48": 41.40545328501187},
    "emissions_t": {"no_shift": 48840.187048520536, "shift_for_mwh": 47889.07857748548,
                    "carbon_persist": 48546.49597207288, "carbon_model": 47631.72098854285,
                    "carbon_perfect": 46856.46146780743},
    "coverage": {"no_shift": 0.7045260432051597, "shift_for_mwh": 0.7147440540316787,
                 "carbon_persist": 0.7002617782459712, "carbon_model": 0.7136157018173496,
                 "carbon_perfect": 0.7137008092906354},
}

CAVEATS = [
    "Average, location-based grid emission factors (Energinet's declaration, 125 % method) for a buyer's "
    "accounting; not marginal emissions and not physically avoided emissions.",
    "The 10 % flexible share (and the +25 % hourly cap) is a declared scenario parameter, not a measured property "
    "of the IT sector's load.",
    "One test half-year (Jul-Dec 2025); no claim that the results generalise beyond it.",
    "Training uses Energinet's Final declaration as if it were available at decision time; Final is published "
    "later (live mode uses the Initial version for the lag features).",
    "Unmatched hours are valued at the hourly grid average intensity, not a residual-mix factor.",
    "Nothing here is audited.",
]


# ------------------------------------------------------------------ frozen configuration
def frozen_config() -> dict:
    """The carbon choices from data/agent_config.json; written there once (from FROZEN) if absent."""
    j = json.loads(AGENT_CONFIG_JSON.read_text()) if AGENT_CONFIG_JSON.exists() else {}
    if "carbon" not in j:
        j["carbon"] = FROZEN | {"frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        AGENT_CONFIG_JSON.write_text(json.dumps(j, indent=2))
    cfg = j["carbon"]
    drift = {k: (cfg.get(k), v) for k, v in FROZEN.items() if cfg.get(k) != v}
    if drift:
        raise SystemExit(f"{AGENT_CONFIG_JSON} 'carbon' differs from the frozen kill-test choices: {drift}")
    return cfg


def gbr(cfg: dict = FROZEN) -> HistGradientBoostingRegressor:
    m = cfg["model"]
    return HistGradientBoostingRegressor(max_iter=m["max_iter"], learning_rate=m["learning_rate"],
                                         max_leaf_nodes=m["max_leaf_nodes"], l2_regularization=m["l2_regularization"],
                                         random_state=m["random_state"])


def model_tag(cfg: dict = FROZEN) -> str:
    m = cfg["model"]
    return (f"co2-hgbr|it={m['max_iter']}|lr={m['learning_rate']}|leaves={m['max_leaf_nodes']}|"
            f"l2={m['l2_regularization']}|price={cfg['use_price']}")


# ------------------------------------------------------------------ CO2-intensity forecast
def fc_columns(E: pd.DataFrame) -> list[str]:
    return [c for c in E.columns if c.startswith("fc_")]


def co2_features(E: pd.DataFrame, idx: pd.DatetimeIndex, use_price: bool) -> pd.DataFrame:
    """Features for target hours `idx`: published day-ahead forecasts, calendar, intensity >= 48 h old,
    and the day-ahead price (published ~13:00 CET on D-1, before the 17:30 UTC decision)."""
    I = E["co2_g_per_kwh"]
    fc_cols = fc_columns(E)
    F = pd.DataFrame(index=idx)
    for c in fc_cols:
        F[c] = E[c].reindex(idx).to_numpy()
    F["fc_wind_total"] = F[[c for c in fc_cols if "wind" in c]].sum(axis=1, min_count=1)
    F["hour"], F["dow"], F["month"] = idx.hour, idx.dayofweek, idx.month
    F["holiday"] = [d in DK_HOLIDAYS for d in idx.strftime("%Y-%m-%d")]
    for lag in (48, 72, 168):
        F[f"lag{lag}"] = I.reindex(idx - pd.Timedelta(hours=lag)).to_numpy()
    F["lag_mean_week"] = pd.DataFrame({k: I.reindex(idx - pd.Timedelta(hours=24 * k)).to_numpy() for k in range(2, 9)},
                                      index=idx).mean(axis=1)
    if use_price:
        pr = E["price_eur"].reindex(idx)
        F["price"] = pr.to_numpy()
        F["price_rank_day"] = pr.groupby(idx.normalize()).rank(pct=True).to_numpy()
        F["price_minus_daymean"] = (pr - pr.groupby(idx.normalize()).transform("mean")).to_numpy()
    return F


def fit(E: pd.DataFrame, before: pd.Timestamp, cfg: dict = FROZEN) -> HistGradientBoostingRegressor:
    """The intensity model trained on every hour with a known intensity before `before`."""
    I = E["co2_g_per_kwh"].dropna()
    tr_idx = I.index[I.index < before]
    X = co2_features(E, tr_idx, cfg["use_price"])
    ok = X.notna().sum(axis=1) > 3
    return gbr(cfg).fit(X[ok], I.loc[tr_idx][ok])


def walk_forward(E: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, use_price: bool,
                 cfg: dict = FROZEN) -> pd.Series:
    """Monthly retraining: month M is predicted by a model trained on hours before M - 6.5 h."""
    cfg = cfg | {"use_price": use_price}
    parts = []
    for M in pd.date_range(start, end - pd.Timedelta(days=1), freq="MS"):
        m = fit(E, M - pd.Timedelta(hours=cfg["train_cutoff_hours"]), cfg)
        te = E.index[(E.index >= M) & (E.index < min(M + pd.offsets.MonthBegin(1), end))]
        parts.append(pd.Series(m.predict(co2_features(E, te, use_price)), index=te))
    return pd.concat(parts).astype(float)


def mae(E: pd.DataFrame, pred: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    a = E["co2_g_per_kwh"].loc[start:end - pd.Timedelta(hours=1)]
    return float((pred.reindex(a.index) - a).abs().mean())


# ------------------------------------------------------------------ shifting policy
def plan_shift(load_hat: np.ndarray, prio: np.ndarray, flex: float = FROZEN["flex_share"],
               cap: float = FROZEN["flex_cap"]) -> np.ndarray:
    """Move flexible load from the highest-priority (dirtiest) hours to the lowest; returns the planned shift
    per hour (negative = defer out of the hour, positive = run deferred load in it; sums to 0)."""
    n = len(load_hat)
    shift = np.zeros(n)
    give = flex * np.array(load_hat, float)
    room = cap * np.array(load_hat, float)
    donors = list(np.argsort(-prio))
    receivers = list(np.argsort(prio))
    for d in donors:
        for r in receivers:
            if give[d] <= 1e-9:
                break
            if prio[r] >= prio[d] or room[r] <= 1e-9 or r == d:
                continue
            m = min(give[d], room[r])
            shift[d] -= m
            shift[r] += m
            give[d] -= m
            room[r] -= m
    return shift


def execute(load: np.ndarray, shift: np.ndarray, flex: float = FROZEN["flex_share"]) -> np.ndarray:
    """Apply a plan to the ACTUAL load: deferral limited by the flexible part of actual load, deferred energy
    re-placed in the planned hours in proportion (energy conserved)."""
    out = np.minimum(-np.minimum(shift, 0), flex * load)
    moved = out.sum()
    inc = np.maximum(shift, 0)
    add = inc / inc.sum() * moved if inc.sum() > 0 else np.zeros_like(load)
    return load - out + add


def test_frame(E: pd.DataFrame, pred_I: pd.Series, start: pd.Timestamp = TEST_START) -> tuple[pd.DataFrame, float]:
    """The TEST hours with everything the strategies need; complete days only. k = the annual portfolio share."""
    if len(pd.date_range(E.index.min(), E.index.max(), freq="h")) != len(E):
        raise ValueError("carbon frame must be hourly without gaps (lags are positional, as in the kill test)")
    I = E["co2_g_per_kwh"]
    k = float(E["load_mwh"].sum() / E["wind_mwh"].sum())
    D = E.loc[start:].copy()
    D["base"] = k * D["wind_mwh"]
    D["load_hat"] = E["load_mwh"].shift(168).reindex(D.index)  # last week: the load forecast (frozen: lag168)
    D["I_model"] = pred_I.reindex(D.index)
    D["I_persist"] = I.shift(168).reindex(D.index)
    D["I_perfect"] = D["co2_g_per_kwh"]
    D = D.dropna(subset=["load_mwh", "load_hat", "I_model", "I_persist", "co2_g_per_kwh", "base"])
    D = D[D.groupby(D.index.normalize())["load_mwh"].transform("size") == 24]
    D["fc_wind_total"] = D[[c for c in fc_columns(E) if "wind" in c]].sum(axis=1, min_count=1)
    return D, k


def priority(g: pd.DataFrame, kind: str, k: float) -> np.ndarray:
    if kind == "mwh":  # shift for MWh matching: from forecast shortfall hours to forecast surplus hours
        return -(k * g["fc_wind_total"].fillna(0).to_numpy() - g["load_hat"].to_numpy())
    return g[kind].to_numpy()


def strategy_load(D: pd.DataFrame, k: float, strategy: str, cfg: dict = FROZEN,
                  plans: dict | None = None) -> pd.Series:
    """The buyer's actual hourly load after executing the strategy's day plans."""
    kind = PRIORITY[strategy]
    new = pd.Series(index=D.index, dtype=float)
    for day, g in D.groupby(D.index.normalize()):
        if kind is None:
            new.loc[g.index] = g["load_mwh"].to_numpy()
            continue
        shift = plan_shift(g["load_hat"].to_numpy(), priority(g, kind, k), cfg["flex_share"], cfg["flex_cap"])
        new.loc[g.index] = execute(g["load_mwh"].to_numpy(), shift, cfg["flex_share"])
        if plans is not None:
            plans[day] = shift
    return new


def metrics(new: pd.Series, D: pd.DataFrame) -> dict:
    co2 = D["co2_g_per_kwh"]
    matched = np.minimum(new, D["base"])
    return {"emissions_t": float((new * co2).sum() / 1000),
            "residual_unmatched_t": float(((new - matched) * co2).sum() / 1000),
            "coverage": float(matched.sum() / new.sum())}


# ------------------------------------------------------------------ robustness (reported only)
def block_bootstrap(D: pd.DataFrame, loads: dict[str, pd.Series], pairs: list[tuple[str, str]],
                    resamples: int = 2000, seed: int = 0, block_days: int = 7) -> dict:
    """Weekly block bootstrap 95 % CI for differences in emission reduction (pp of no-shift emissions, and t).
    Blocks are consecutive 7-day stretches of the TEST period (the last one may be shorter)."""
    days = D.index.normalize()
    block = ((days - days[0]).days // block_days).to_numpy()
    nb = int(block.max()) + 1
    hours_per_block = np.bincount(block, minlength=nb)
    em = {s: np.bincount(block, weights=(loads[s] * D["co2_g_per_kwh"]).to_numpy() / 1000, minlength=nb)
          for s in loads}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, nb, size=(resamples, nb))
    out = {"method": f"weekly block bootstrap: {nb} blocks of {block_days} consecutive days, resampled with "
                     "replacement", "resamples": resamples, "seed": seed, "blocks": nb,
           "note": "reported only; never used to choose anything"}
    base_all = em["no_shift"][draws].sum(axis=1)
    scale = len(D) / hours_per_block[draws].sum(axis=1)
    for better, ref in pairs:
        diff_t = em[ref][draws].sum(axis=1) - em[better][draws].sum(axis=1)
        pp = 100 * diff_t / base_all
        point_t = float(em[ref].sum() - em[better].sum())
        out[f"{better}_minus_{ref}"] = {
            "definition": f"emission reduction of {better} minus that of {ref} (positive = {better} cuts more)",
            "reduction_pp": 100 * point_t / float(em["no_shift"].sum()),
            "reduction_pp_ci95": [float(np.percentile(pp, 2.5)), float(np.percentile(pp, 97.5))],
            "tonnes": point_t,
            "tonnes_ci95": [float(np.percentile(diff_t * scale, 2.5)), float(np.percentile(diff_t * scale, 97.5))],
            "share_of_resamples_above_zero": float((diff_t > 0).mean()),
        }
    return out


# ------------------------------------------------------------------ plans (what the agent commits)
def plan_json(day: pd.Timestamp, co2_forecast, shift, load_hat, cfg: dict = FROZEN, extra: dict | None = None) -> bytes:
    """Canonical bytes of a carbon day plan: the CO2 forecast and the planned hourly shift."""
    return json.dumps({
        "agent": CARBON_AGENT_ID, "mode": "carbon", "day_utc": day.strftime("%Y-%m-%d"), "model": model_tag(cfg),
        "co2_forecast_g_per_kwh": [round(float(x), 2) for x in co2_forecast],
        "planned_shift_mwh": [round(float(x), 3) for x in shift],
        "pred_load_mwh": [round(float(x), 3) for x in load_hat],
        "flex_share": cfg["flex_share"], "flex_cap": cfg["flex_cap"],
    } | (extra or {}), separators=(",", ":"), sort_keys=True).encode()


# ------------------------------------------------------------------ live mode (tomorrow's plan, scored later)
# Energinet publishes DeclarationGridEmission Version "Initial" within about 2 hours (verified 15 Oct 2026); Final
# follows weeks later. Live lag features therefore use Initial; the model is still trained on Final (the dataset).
LIVE_LAG_VERSION, LIVE_TRAIN_VERSION = "Initial", "Final"
LIVE_LAG_DAYS = 9  # lag168 and the mean of the same hour 2..8 days earlier need up to 8 days of history


def live_intensity(ge: pd.DataFrame, settlement: pd.DataFrame, hours: pd.DatetimeIndex,
                   version: str) -> tuple[pd.Series, list[int]]:
    """Consumption-weighted DK intensity (g/kWh) for `hours` from one DeclarationGridEmission Version.
    Weights are ProductionConsumptionSettlement GrossConsumptionMWh by area, as in the dataset. Settlement is
    published ~10 days late, so an hour without it is weighted by the same hour n whole weeks earlier (smallest
    n with data); returns the intensity and n per hour (0 = the hour's own consumption)."""
    from .dataset import INTENSITY_METHOD, consumption_by_area
    g = ge[(ge["Version"] == version) & (ge["FuelAllocationMethod"] == INTENSITY_METHOD)]
    inten = g.pivot_table(index="HourUTC", columns="PriceArea", values="CO2PerkWh", aggfunc="mean").reindex(hours)
    cons = consumption_by_area(settlement) if len(settlement) else pd.DataFrame(columns=["DK1", "DK2"])
    cons = cons.reindex(columns=["DK1", "DK2"])
    w = pd.DataFrame(index=hours, columns=["DK1", "DK2"], dtype=float)
    weeks_back = []
    for h in hours:
        n = next((n for n in range(0, 9) if h - pd.Timedelta(weeks=n) in cons.index
                  and cons.loc[h - pd.Timedelta(weeks=n)].notna().all()), None)
        weeks_back.append(-1 if n is None else n)
        if n is not None:
            w.loc[h] = cons.loc[h - pd.Timedelta(weeks=n)].to_numpy(float)
    inten = inten.reindex(columns=["DK1", "DK2"])
    val = (inten * w).sum(axis=1, min_count=2) / w.sum(axis=1, min_count=2)
    return val.where(inten.notna().all(axis=1) & w.notna().all(axis=1)).rename("co2_g_per_kwh"), weeks_back


def live_plan(day: pd.Timestamp, ge: pd.DataFrame, settlement: pd.DataFrame, fc: pd.DataFrame,
              da: pd.DataFrame, E: pd.DataFrame | None = None, cfg: dict | None = None) -> dict:
    """Tomorrow's CO2 forecast (24 values) and planned hourly shift profile, from the frozen model trained on the
    Final dataset and live inputs: Initial intensity for the lags, Forecasts_Hour for the day, DayAheadPrices.
    The live load forecast (lag168) is not available (Energinet's industry consumption feed is paused), so the
    shift is committed as a share of each hour's own load (the plan computed on a flat load profile)."""
    from . import dataset
    cfg = cfg or frozen_config()
    if E is None:
        E, _ = dataset.load_carbon()
    hrs = pd.date_range(day, periods=24, freq="h")
    hist = pd.date_range(day - pd.Timedelta(days=LIVE_LAG_DAYS), day, freq="h", inclusive="left")
    I, weeks_back = live_intensity(ge, settlement, hist, LIVE_LAG_VERSION)
    fcp = dataset.area_forecasts(fc).reindex(index=hrs, columns=dataset.CARBON_FC_COLUMNS)
    if fcp.isna().any().any():
        raise SystemExit(f"Day-ahead forecasts by area and type incomplete for {day:%Y-%m-%d} "
                         f"({int(fcp.isna().any(axis=1).sum())} hours missing; published around 18:00 Danish time)")
    L = pd.DataFrame(index=hist.append(hrs))
    L["co2_g_per_kwh"] = I.reindex(L.index)
    for c in dataset.CARBON_FC_COLUMNS:
        L[c] = fcp[c].reindex(L.index)
    price = dataset.hourly_price(pd.DataFrame(columns=["HourUTC", "PriceArea", "SpotPriceEUR"]), da).reindex(hrs)
    if cfg["use_price"] and price.isna().any():
        raise SystemExit(f"Day-ahead prices incomplete for {day:%Y-%m-%d} (published around 13:00 CET)")
    L["price_eur"] = price.reindex(L.index)
    F = co2_features(L, hrs, cfg["use_price"])
    need = [f"lag{k}" for k in (48, 72, 168)] + ["lag_mean_week"]
    if F[need].isna().any().any():
        raise SystemExit(f"Initial intensity history incomplete before {day:%Y-%m-%d}")
    model = fit(E, E.index.max() + pd.Timedelta(hours=1), cfg)  # everything in the Final dataset
    pred = model.predict(F[list(model.feature_names_in_)])
    persist = I.reindex(hrs - pd.Timedelta(hours=168)).to_numpy()
    share = plan_shift(np.ones(24), pred, cfg["flex_share"], cfg["flex_cap"])
    return {
        "agent": CARBON_AGENT_ID, "model": model_tag(cfg),
        "co2_forecast_g_per_kwh": [round(float(x), 2) for x in pred],
        "persistence_lag168_g_per_kwh": [round(float(x), 2) for x in persist],
        "planned_shift_share_of_hour_load": [round(float(x), 4) for x in share],
        "flex_share": cfg["flex_share"], "flex_cap": cfg["flex_cap"],
        "train_version": LIVE_TRAIN_VERSION, "train_hours": f"{E.index.min():%Y-%m-%d}..{E.index.max():%Y-%m-%d %H:%M}",
        "lag_intensity_version": LIVE_LAG_VERSION,
        "lag_weights_weeks_back": {"min": int(min(weeks_back)), "max": int(max(weeks_back))},
        "load_forecast": "flat (share of each hour's own load): the lag168 load feed is paused",
    }


def live_score(plan: dict, day: pd.Timestamp, ge: pd.DataFrame, settlement: pd.DataFrame) -> dict:
    """CO2 MAE of the committed forecast and of lag168 persistence (also committed) against every version of the
    day's intensity that is complete: Initial first, Final when it appears. Records which version and weights."""
    hrs = pd.date_range(day, periods=24, freq="h")
    out = {}
    for version in (LIVE_LAG_VERSION, LIVE_TRAIN_VERSION):
        actual, weeks_back = live_intensity(ge, settlement, hrs, version)
        if actual.isna().any():
            continue
        a = actual.to_numpy()
        out[version] = {
            "mae_model_g_per_kwh": float(np.mean(np.abs(np.array(plan["co2_forecast_g_per_kwh"]) - a))),
            "mae_lag168_g_per_kwh": float(np.mean(np.abs(np.array(plan["persistence_lag168_g_per_kwh"]) - a))),
            "actual_g_per_kwh": [round(float(x), 2) for x in a],
            "weights": "own hour" if max(weeks_back) == 0 else f"same hour up to {max(weeks_back)} weeks earlier",
        }
    return out


# ------------------------------------------------------------------ the emissions proof's inputs for one week
# The kill test's K4 week: the 43rd complete TEST day (D.index.normalize().unique()[7 * 6]).
K4_WEEK = pd.Timestamp("2025-08-12")
K4_REFERENCE = {"threshold_bps": 4476, "residual_t": 1842.7, "circuit_gates": 62240}


def intensity_g(co2_g_per_kwh) -> list[int]:
    """The integer g/kWh the intensity oracle posts and the circuit uses (kill test: round, clipped at 0)."""
    return np.clip(np.round(np.asarray(co2_g_per_kwh, float)), 0, None).astype(int).tolist()


def zk_week(E: pd.DataFrame, start: pd.Timestamp = K4_WEEK, load_mwh: pd.Series | None = None) -> dict:
    """Integer inputs of the emissions proof for the 168 hours from `start`, exactly as the kill test's K4:
    load in kWh (rounded), certificates = whole MWh of the fixed portfolio k * wind (floored), intensity in whole
    g/kWh, and the tightest threshold (bps, floored) and cap (kg, rounded up) the data supports.
    `load_mwh` overrides the actual load (e.g. the carbon-shifted load)."""
    hrs = pd.date_range(start, periods=168, freq="h")
    wk = E.reindex(hrs)
    load = (load_mwh.reindex(hrs) if load_mwh is not None else wk["load_mwh"])
    if wk[["wind_mwh", "co2_g_per_kwh"]].isna().any().any() or load.isna().any():
        raise ValueError(f"week from {start} is not complete in the carbon dataset")
    k = float(E["load_mwh"].sum() / E["wind_mwh"].sum())
    load_kwh = (load * 1000).round().astype(int).tolist()
    cert_mwh = np.floor(k * wk["wind_mwh"]).astype(int).tolist()
    cert_kwh = [c * 1000 for c in cert_mwh]
    inten = intensity_g(wk["co2_g_per_kwh"])
    matched = sum(min(a, b) for a, b in zip(load_kwh, cert_kwh))
    resid_g = sum((a - min(a, b)) * i for a, b, i in zip(load_kwh, cert_kwh, inten))
    return {"window_start_utc": str(start), "window_start_unix": int(start.tz_localize("UTC").timestamp()),
            "load_kwh": load_kwh, "cert_mwh": cert_mwh, "cert_kwh": cert_kwh, "intensity_g_per_kwh": inten,
            "threshold_bps": matched * 10000 // sum(load_kwh), "residual_g": resid_g, "cap_kg": -(-resid_g // 1000),
            "portfolio_share_k": k}


# ------------------------------------------------------------------ the TEST run
def backtest(E: pd.DataFrame, write: bool = True, cfg: dict | None = None) -> dict:
    cfg = cfg or frozen_config()
    E = E.sort_index()
    # validation re-run, for the record only (the choice use_price is frozen and is NOT re-made here)
    val = {f"use_price_{str(up).lower()}": mae(E, walk_forward(E, VAL_START, TEST_START, up, cfg), VAL_START, TEST_START)
           for up in (False, True)}
    pred_I = walk_forward(E, TEST_START, TEST_END, cfg["use_price"], cfg)  # TEST
    I = E["co2_g_per_kwh"]
    T = pd.DataFrame({"actual": I, "model": pred_I, "lag48": I.shift(48), "lag168": I.shift(168)}).loc[TEST_START:].dropna()
    m_mae = {k: float((T[k] - T["actual"]).abs().mean()) for k in ("model", "lag48", "lag168")}
    best_persist = min(m_mae["lag48"], m_mae["lag168"])

    D, k = test_frame(E, pred_I)
    plans: dict = {}
    loads = {s: strategy_load(D, k, s, cfg, plans if s == "carbon_model" else None) for s in STRATEGIES}
    res = {s: metrics(loads[s], D) for s in STRATEGIES}
    no = res["no_shift"]["emissions_t"]
    for s in STRATEGIES:
        res[s]["reduction_vs_no_shift"] = 1 - res[s]["emissions_t"] / no
    ref = KILLTEST_REFERENCE
    repro = {f"emissions_t.{s}": res[s]["emissions_t"] / ref["emissions_t"][s] - 1 for s in STRATEGIES}
    repro |= {f"coverage.{s}": res[s]["coverage"] / ref["coverage"][s] - 1 for s in STRATEGIES}
    repro |= {f"mae.{s}": m_mae[s] / ref["mae"][s] - 1 for s in m_mae}
    days = sorted(plans)
    out = {
        "mode": "carbon", "agent": CARBON_AGENT_ID, "frozen_config": cfg, "model_tag": model_tag(cfg),
        "periods": {"train_from": str(E.index.min().date()), "validation": [str(VAL_START.date()), str(TEST_START.date())],
                    "test": [str(days[0].date()), str(days[-1].date())]},
        "test_days": len(days), "test_hours": int(len(D)), "portfolio_share_k": k,
        "forecast": {
            "test_mae_g_per_kwh": m_mae, "test_hours_scored": int(len(T)),
            "improvement_vs_best_persistence": 1 - m_mae["model"] / best_persist,
            "validation_mae_frozen": cfg["validation_mae_g_per_kwh"], "validation_mae_rerun": val,
            "use_price": cfg["use_price"],
        },
        "strategies": res,
        "reductions_vs_no_shift": {s: res[s]["reduction_vs_no_shift"] for s in STRATEGIES if s != "no_shift"},
        "tonnes_saved_vs_no_shift": {s: no - res[s]["emissions_t"] for s in STRATEGIES if s != "no_shift"},
        "carbon_model_share_of_perfect_reduction":
            res["carbon_model"]["reduction_vs_no_shift"] / res["carbon_perfect"]["reduction_vs_no_shift"],
        "coverage_cost_vs_shift_for_mwh_pp": 100 * (res["shift_for_mwh"]["coverage"] - res["carbon_model"]["coverage"]),
        "robustness": block_bootstrap(D, loads, [("carbon_model", "shift_for_mwh"), ("carbon_model", "carbon_persist")]),
        "killtest_reference": ref, "reproduction_rel_diff": repro,
        "caveats": CAVEATS,
        "note": "carbon_perfect uses the actual intensity: a reference, not something a planner can achieve.",
    }
    if write:
        CARBON_BACKTEST_JSON.write_text(json.dumps(out, indent=2))
        hours = pd.DataFrame({"hour_utc": D.index, "load": D["load_mwh"].to_numpy(),
                              "carbon_model_load": loads["carbon_model"].to_numpy(), "base_cert": D["base"].to_numpy(),
                              "co2_actual": D["co2_g_per_kwh"].to_numpy(), "co2_forecast": D["I_model"].to_numpy()})
        hours.to_csv(CARBON_BACKTEST_JSON.with_suffix(".hours.csv"), index=False, float_format="%.4f")
        CARBON_PLANS_DIR.mkdir(parents=True, exist_ok=True)
        for day in days:
            g = D.loc[day: day + pd.Timedelta(hours=23)]
            m = day.replace(day=1)
            tag = hashlib.sha256(f"{m:%Y-%m}|{model_tag(cfg)}".encode()).hexdigest()[:16]
            (CARBON_PLANS_DIR / f"{day:%Y-%m-%d}.json").write_bytes(
                plan_json(day, g["I_model"], plans[day], g["load_hat"], cfg, {"month_model": tag}))
    return out


def run(write: bool = True) -> dict:
    from . import dataset
    E, _ = dataset.load_carbon()
    return backtest(E, write=write)
