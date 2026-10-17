"""The AI procurement agent.

Each delivery day D the agent decides, BEFORE the day (at 17:30 UTC on D-1, after Energinet's
day-ahead wind forecast is published at 18:00 Danish time):
  1. how to move the buyer's flexible load between hours of D (a declared scenario parameter:
     `flex_share` of each hour's load is deferrable within the same day, e.g. batch compute);
  2. which hours to buy extra hourly certificates in, from a fixed extra budget (`topup_share`
     of annual load), taken from national clean production not already in the buyer's portfolio.
It uses learned models (gradient-boosted trees, scikit-learn):
  * supply model: actual wind per hour from the day-ahead forecast + calendar (v2: optionally by price area
    and offshore/onshore, and as quantile models that give the planner wind scenarios),
  * load model:   the buyer's hourly load from calendar + lags that are >= 48 h old (v2: a residual on last
    week's value, with a monthly selector that falls back to last week when the model has been worse).
v2 also replaces the budget that expired at midnight by a rolling, paced balance, and adds a stochastic
linear program (HiGHS) as an alternative to the greedy planner. Every v2 choice is an `AgentConfig` picked by
`select_config` on the VALIDATION quarter only; the TEST half-year is then run once with the frozen config.
`AgentConfig()` (the defaults) is exactly the v1 agent.
Evaluation is walk-forward on real data (retrain monthly, test on the second half of the year)
against (a) the naive fixed portfolio, (b) a bigger portfolio with EXACTLY the same extra MWh,
and (c) a perfect-foresight reference (same policy and budget rule, actual values). Numbers are reported as measured.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from sklearn.ensemble import HistGradientBoostingRegressor

from .config import AGENT_CONFIG_JSON, AGENT_EXPERIMENTS_JSON, AGENT_ID, BACKTEST_JSON, DATA, PLANS_DIR
from .dataset import FC_AREA_COLUMNS

DECISION_HOUR_UTC = 17.5  # D-1 17:30 UTC: after the day-ahead forecast (18:00 DK) in both seasons
MIN_LAG_H = 48            # load features may only use values at least 48 h old

# Danish public holidays 2025-2026 (fixed list; used as a calendar feature)
DK_HOLIDAYS = {
    "2025-01-01", "2025-04-17", "2025-04-18", "2025-04-20", "2025-04-21", "2025-05-16", "2025-05-29",
    "2025-06-05", "2025-06-08", "2025-06-09", "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31",
    "2026-01-01", "2026-04-02", "2026-04-03", "2026-04-05", "2026-04-06", "2026-05-01", "2026-05-14",
    "2026-05-24", "2026-05-25", "2026-06-05", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
}

# v2 search space (every value is chosen on VALIDATION; see select_config)
BALANCE_CAP_DAYS = 7
ALPHAS = (1.0, 1.5, 2.0, 3.0, 5.0, 7.0)
QUANTILE_SETS = ((), (0.5,), (0.25, 0.5, 0.75), (0.1, 0.5, 0.9), (0.1, 0.3, 0.5, 0.7, 0.9))
LOAD_MODELS = ("v1_gbr", "lag168", "residual", "selector")
# v2's load forecast is the monthly selector (or plain last week); v1_gbr and the bare residual model are
# evaluated on validation for the ablation only and are not eligible for selection
SELECTABLE_LOAD_MODELS = ("lag168", "selector")
WIND_FEATURES = ("total", "area_type")
POLICIES = ("greedy", "lp")
SELECTOR_LOOKBACK_MONTHS = 2
ML_ABLATION_JSON = DATA / "agent_ml_ablation.json"  # TEST-period ablations of the frozen config (reporting only)
_EPS_BUY, _EPS_MOVE = 1e-4, 1e-5  # LP tie-breakers (MWh-equivalents): never buy or move without an expected gain


@dataclass(frozen=True)
class AgentParams:
    flex_share: float = 0.10   # share of each hour's load that can move within the day (scenario parameter)
    flex_cap: float = 0.25     # an hour may rise at most 25 % above its own baseline
    topup_share: float = 0.05  # extra certificate budget = 5 % of annual load (same MWh given to the comparator)


@dataclass(frozen=True)
class AgentConfig:
    """Everything the agent may choose (on VALIDATION). Scenario parameters are in AgentParams and stay fixed."""
    policy: str = "greedy"                  # "greedy" (v1 heuristic) | "lp" (stochastic linear program)
    alpha: float = 1.0                      # pacing: spend_cap = min(balance, alpha * budget_day); 1 == v1
    load_model: str = "v1_gbr"              # "v1_gbr" | "lag168" | "residual" | "selector"
    wind_features: str = "total"            # "total" (summed forecast, v1) | "area_type" (DK1/DK2 x off/onshore)
    wind_quantiles: tuple[float, ...] = ()  # () = squared-error point model (v1); else quantile scenarios

    def to_dict(self) -> dict:
        return asdict(self) | {"wind_quantiles": list(self.wind_quantiles)}

    @staticmethod
    def from_dict(d: dict) -> "AgentConfig":
        return AgentConfig(**(d | {"wind_quantiles": tuple(d.get("wind_quantiles", ()))}))

    def tag(self) -> str:
        q = ",".join(f"{x:g}" for x in self.wind_quantiles) or "mean"
        return f"{self.policy}|alpha={self.alpha:g}|load={self.load_model}|wind={self.wind_features}|q={q}"


V1_CONFIG = AgentConfig()


def periods(df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """TRAIN Jan-Mar, VALIDATION Apr-Jun, TEST Jul-Dec of the dataset's year ([start, end) dates)."""
    y = int(df.index[len(df) // 2].year)
    return {"train": (f"{y}-01-01", f"{y}-04-01"), "validation": (f"{y}-04-01", f"{y}-07-01"),
            "test": (f"{y}-07-01", f"{y + 1}-01-01")}


def decision_time(day: pd.Timestamp) -> pd.Timestamp:
    return day.normalize() - pd.Timedelta(hours=24 - DECISION_HOUR_UTC)


def portfolio_share(df: pd.DataFrame) -> float:
    """Share of national wind sized to 100 % ANNUAL matching (the buyer's fixed portfolio)."""
    return float(df["load_mwh"].sum() / df["wind_mwh"].sum())


def coverage(load: np.ndarray, cert: np.ndarray) -> float:
    load = np.asarray(load, float)
    return float(np.minimum(load, np.asarray(cert, float)).sum() / load.sum())


def pinball(y: np.ndarray, p: np.ndarray, q: float) -> float:
    d = np.asarray(y, float) - np.asarray(p, float)
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


# ------------------------------------------------------------------ features (as-of safe)
def _calendar(idx: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "hour": idx.hour, "dow": idx.dayofweek, "month": idx.month,
        "doy_s": np.sin(2 * np.pi * idx.dayofyear / 365.25), "doy_c": np.cos(2 * np.pi * idx.dayofyear / 365.25),
        "holiday": [d in DK_HOLIDAYS for d in idx.strftime("%Y-%m-%d")],
    }, index=idx)


def _is_holiday(days: pd.DatetimeIndex) -> np.ndarray:
    return np.array([d in DK_HOLIDAYS for d in pd.DatetimeIndex(days).strftime("%Y-%m-%d")])


def load_features(df: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Features for target hours `idx`, using only load values >= MIN_LAG_H old."""
    s = df["load_mwh"]
    f = _calendar(idx)
    for lag in (48, 72, 168, 336):
        f[f"lag{lag}"] = s.reindex(idx - pd.Timedelta(hours=lag)).to_numpy()
    f["lag_mean_week"] = pd.DataFrame({k: s.reindex(idx - pd.Timedelta(hours=24 * k)).to_numpy()
                                       for k in range(2, 9)}, index=idx).mean(axis=1, skipna=True)
    return f


def residual_load_features(df: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """v2 load features for target hours `idx` (the model predicts load_h - load_{h-168}).
    Calendar and holiday flags, plus load values that are all >= MIN_LAG_H old."""
    s = df["load_mwh"]
    f = _calendar(idx)
    day = idx.normalize()
    f["pre_holiday"] = _is_holiday(day + pd.Timedelta(days=1))
    f["post_holiday"] = _is_holiday(day - pd.Timedelta(days=1))
    f["holiday_last_week"] = _is_holiday(day - pd.Timedelta(days=7))  # last week's value was a holiday
    for lag in (48, 72, 168, 336):
        f[f"lag{lag}"] = s.reindex(idx - pd.Timedelta(hours=lag)).to_numpy()
    f["same_hour_mean_2_3d"] = f[["lag48", "lag72"]].mean(axis=1)
    level = s.rolling("72h", min_periods=48).mean()  # mean over (t-72h, t]
    f["level_3d"] = level.reindex(idx - pd.Timedelta(hours=MIN_LAG_H)).to_numpy()  # ends 48 h before the hour
    f["lag168_minus_lag336"] = f["lag168"] - f["lag336"]
    return f


def supply_features(df: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Features for target hours `idx`: the published day-ahead forecast + calendar. No actuals."""
    f = _calendar(idx)
    fc = df["wind_fc_da_mwh"].reindex(idx)
    f["fc"] = fc.to_numpy()
    f["fc_day_mean"] = fc.groupby(idx.normalize()).transform("mean").to_numpy()
    f["fc_ramp"] = fc.diff().fillna(0).to_numpy()
    return f


def supply_features_area(df: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """supply_features plus the day-ahead forecast by price area and offshore/onshore. No actuals."""
    f = supply_features(df, idx)
    for c in FC_AREA_COLUMNS:
        f[c] = df[c].reindex(idx).to_numpy()
    return f


def _supply_X(df: pd.DataFrame, idx: pd.DatetimeIndex, features: str) -> pd.DataFrame:
    """Prediction-time supply features for one day, with v1's fill for the few hours without a forecast."""
    X = supply_features(df, idx) if features == "total" else supply_features_area(df, idx)
    if X["fc"].isna().any():  # a few hours of 2025 have no published forecast
        lag48 = df["wind_mwh"].reindex(idx - pd.Timedelta(hours=48)).to_numpy()  # known before the decision
        X["fc"] = X["fc"].interpolate(limit_direction="both").fillna(pd.Series(lag48, index=idx)).fillna(0)
        X["fc_day_mean"] = X["fc"].mean()
        X["fc_ramp"] = X["fc"].diff().fillna(0)
    if features == "area_type":
        for c in FC_AREA_COLUMNS:  # gaps inside the day are interpolated; whole-day gaps stay NaN for the trees
            X[c] = X[c].interpolate(limit_direction="both")
    return X


def _model(quantile: float | None = None) -> HistGradientBoostingRegressor:
    kw = {"loss": "quantile", "quantile": quantile} if quantile is not None else {}
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=0, **kw)


def _day_index(day: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(day, periods=24, freq="h")


def _month(day: pd.Timestamp) -> pd.Timestamp:
    return day.normalize().replace(day=1)


def _full_days(df: pd.DataFrame, start, end=None) -> list[pd.Timestamp]:
    days = [d for d in pd.date_range(pd.Timestamp(start).normalize(), df.index[-1].normalize(), freq="D")
            if len(df.loc[d: d + pd.Timedelta(hours=23)]) == 24]
    return [d for d in days if end is None or d < pd.Timestamp(end)]


# ------------------------------------------------------------------ walk-forward forecasts
class Forecasts:
    """Day-ahead predictions for `days`, walk-forward: each month's models are trained only on data known
    before that month's first decision. Cached per model, so many configurations share the same fits."""

    def __init__(self, df: pd.DataFrame, days: list[pd.Timestamp]):
        self.df, self.days = df, list(days)
        self._cache: dict = {}
        self.selector_choices: dict[str, dict] = {}
        self.v1_fill_used = 0  # days where v1 load features still had gaps after forward-fill

    # ---- load
    def _lag168(self, idx: pd.DatetimeIndex, asof: pd.Timestamp) -> np.ndarray:
        s = self.df["load_mwh"]
        v = s.reindex(idx - pd.Timedelta(hours=168)).to_numpy()
        v = np.where(np.isnan(v), s.reindex(idx - pd.Timedelta(hours=336)).to_numpy(), v)
        return np.where(np.isnan(v), s[s.index < asof - pd.Timedelta(hours=MIN_LAG_H)].mean(), v)

    def _residual_month(self, m: pd.Timestamp) -> pd.Series:
        """Residual-model predictions for every hour of month m, from a model trained on hours that are
        >= MIN_LAG_H old at the month's first decision."""
        key = ("resid", m)
        if key not in self._cache:
            T = decision_time(m)
            hist = self.df.index[self.df.index < T - pd.Timedelta(hours=MIN_LAG_H)]
            X = residual_load_features(self.df, hist)
            y = self.df["load_mwh"].reindex(hist).to_numpy() - X["lag168"].to_numpy()
            ok = ~np.isnan(y)
            hours = self.df.index[(self.df.index >= m) & (self.df.index < m + pd.DateOffset(months=1))]
            base = self._lag168(hours, T)
            if ok.sum() >= 14 * 24 and len(hours):
                pred = base + _model().fit(X[ok], y[ok]).predict(residual_load_features(self.df, hours))
            else:  # not enough history yet: the residual model is last week's value
                pred = base
            self._cache[key] = pd.Series(np.maximum(pred, 0), index=hours)
        return self._cache[key]

    def _select_load(self, m: pd.Timestamp) -> dict:
        """Residual model or last week's value for month m: whichever had the lower MAE over the previous
        SELECTOR_LOOKBACK_MONTHS months, on hours >= MIN_LAG_H old at the month's first decision."""
        T = decision_time(m) - pd.Timedelta(hours=MIN_LAG_H)
        start = m - pd.DateOffset(months=SELECTOR_LOOKBACK_MONTHS)
        hrs = self.df.index[(self.df.index >= start) & (self.df.index < T)]
        prev = [start + pd.DateOffset(months=i) for i in range(SELECTOR_LOOKBACK_MONTHS + 1)]
        model = pd.concat([self._residual_month(pm) for pm in prev if pm < m] or [pd.Series(dtype=float)]).reindex(hrs)
        lag = self.df["load_mwh"].reindex(hrs - pd.Timedelta(hours=168)).set_axis(hrs)
        actual = self.df["load_mwh"].reindex(hrs)
        ok = model.notna() & lag.notna()
        rec = {"window": [str(start), str(T)], "hours": int(ok.sum())}
        if ok.sum() < 7 * 24:
            return rec | {"choice": "lag168", "reason": "less than a week of out-of-sample history"}
        mae_m = float((model[ok] - actual[ok]).abs().mean())
        mae_l = float((lag[ok] - actual[ok]).abs().mean())
        return rec | {"choice": "residual" if mae_m < mae_l else "lag168", "mae_residual": mae_m, "mae_lag168": mae_l}

    def load(self, kind: str) -> dict[pd.Timestamp, np.ndarray]:
        key = ("load", kind)
        if key in self._cache:
            return self._cache[key]
        out, models = {}, {}
        for day in self.days:
            m, idx = _month(day), _day_index(day)
            if kind == "v1_gbr":
                if m not in models:  # monthly retrain on everything known before the month
                    hist = self.df[self.df.index < decision_time(m)]
                    X, y = load_features(self.df, hist.index), hist["load_mwh"]
                    ok = X.notna().all(axis=1)
                    models[m] = (_model().fit(X[ok], y[ok]), float(y.mean()))
                ml, fill = models[m]
                X = load_features(self.df, idx).ffill(axis=0)
                if X.isna().any().any():
                    self.v1_fill_used += 1
                    X = X.fillna(fill)  # v1 filled with the day's ACTUAL mean here; v2 uses the training mean
                out[day] = np.maximum(ml.predict(X), 0)
            elif kind == "lag168":
                out[day] = self._lag168(idx, decision_time(day))
            elif kind == "residual":
                out[day] = self._residual_month(m).reindex(idx).to_numpy()
            elif kind == "selector":
                if str(m.date()) not in self.selector_choices:
                    self.selector_choices[str(m.date())] = self._select_load(m)
                use = self.selector_choices[str(m.date())]["choice"]
                out[day] = (self._residual_month(m).reindex(idx).to_numpy() if use == "residual"
                            else self._lag168(idx, decision_time(day)))
            else:
                raise ValueError(f"unknown load model {kind}")
        self._cache[key] = out
        return out

    # ---- wind
    def wind(self, features: str, quantile: float | None) -> dict[pd.Timestamp, np.ndarray]:
        key = ("wind", features, quantile)
        if key in self._cache:
            return self._cache[key]
        out, models = {}, {}
        for day in self.days:
            m = _month(day)
            if m not in models:
                hist = self.df[self.df.index < decision_time(m)]
                fx = supply_features if features == "total" else supply_features_area
                X, y = fx(self.df, hist.index), hist["wind_mwh"]
                ok = X["fc"].notna()
                models[m] = _model(quantile).fit(X[ok], y[ok])
            out[day] = np.maximum(models[m].predict(_supply_X(self.df, _day_index(day), features)), 0)
        self._cache[key] = out
        return out

    def wind_scenarios(self, features: str, quantiles: tuple) -> dict[pd.Timestamp, np.ndarray]:
        """(S, 24) per day: one scenario per quantile (sorted per hour, no crossing), or the point model.
        features == "raw_forecast" (ablation only): Energinet's published day-ahead forecast, no model, one scenario."""
        if features == "raw_forecast":
            return {d: v[None, :] for d, v in self.fc_filled().items()}
        key = ("scen", features, quantiles)
        if key not in self._cache:
            preds = [self.wind(features, q) for q in quantiles] or [self.wind(features, None)]
            self._cache[key] = {d: np.sort(np.vstack([p[d] for p in preds]), axis=0) for d in self.days}
        return self._cache[key]

    def wind_point(self, features: str, quantiles: tuple) -> dict[pd.Timestamp, np.ndarray]:
        if features == "raw_forecast":
            return self.fc_filled()
        if not quantiles:
            return self.wind(features, None)
        if 0.5 in quantiles:
            return self.wind(features, 0.5)
        return {d: s.mean(axis=0) for d, s in self.wind_scenarios(features, quantiles).items()}

    def fc_filled(self) -> dict[pd.Timestamp, np.ndarray]:
        if "fc" not in self._cache:
            self._cache["fc"] = {d: _supply_X(self.df, _day_index(d), "total")["fc"].to_numpy() for d in self.days}
        return self._cache["fc"]


# ------------------------------------------------------------------ policy
def plan_day(p_load: np.ndarray, p_cert: np.ndarray, p_avail: np.ndarray, budget_mwh: float,
             params: AgentParams) -> tuple[np.ndarray, np.ndarray]:
    """Return (shift_mwh[24], buy_mwh[24]) from predictions only.
    shift: negative = defer load out of the hour, positive = run deferred load in the hour (sums to 0)."""
    n = len(p_load)
    shift = np.zeros(n)
    surplus = p_cert - p_load
    give = np.minimum(params.flex_share * p_load, np.maximum(-surplus, 0))   # flexible load in short hours
    room = np.minimum(params.flex_cap * p_load, np.maximum(surplus, 0))      # spare clean cover in long hours
    donors = sorted(range(n), key=lambda h: -give[h])
    receivers = sorted(range(n), key=lambda h: -room[h])
    r = 0
    for d in donors:
        while give[d] > 1e-9 and r < n:
            h = receivers[r]
            if room[h] <= 1e-9 or h == d:
                r += 1
                continue
            m = min(give[d], room[h])
            shift[d] -= m
            shift[h] += m
            give[d] -= m
            room[h] -= m
    # top-up: water-fill the budget into the largest predicted residual shortfalls
    residual = np.maximum(p_load + shift - p_cert, 0)
    buy = np.zeros(n)
    left = budget_mwh
    for h in np.argsort(-residual):
        if left <= 1e-9 or residual[h] <= 1e-9:
            break
        m = min(residual[h], max(p_avail[h], 0), left)
        buy[h] = m
        left -= m
    return shift, buy


def plan_day_lp(p_load: np.ndarray, cert_scenarios: np.ndarray, p_avail: np.ndarray, spend_cap: float,
                params: AgentParams) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic linear program (HiGHS): maximise the expected matched MWh over the wind scenarios.
    Variables per hour h: out_h, in_h (flexible load moved out of / into h), buy_h, matched_{h,s} per scenario s.
      matched_{h,s} <= p_load_h - out_h + in_h,   matched_{h,s} <= cert_{h,s} + buy_h,
      0 <= out_h <= flex_share * p_load_h,  0 <= in_h <= flex_cap * p_load_h,  sum out = sum in,
      0 <= buy_h <= p_avail_h,  sum buy <= spend_cap.
    Tiny costs on purchases and moves break ties, so nothing is bought or moved without an expected gain.
    Returns (shift = in - out, buy), the same shape as plan_day."""
    p_load = np.asarray(p_load, float)
    cert = np.atleast_2d(np.asarray(cert_scenarios, float))
    S, n = cert.shape
    avail = np.maximum(np.asarray(p_avail, float), 0)
    cap = max(float(spend_cap), 0.0)
    eye, zero = np.eye(n), np.zeros((n, n))
    rows, rhs = [], []
    for s in range(S):
        m = np.zeros((n, S * n))
        m[:, s * n:(s + 1) * n] = eye
        rows += [np.hstack([eye, -eye, zero, m]), np.hstack([zero, zero, -eye, m])]
        rhs += [p_load, cert[s]]
    rows.append(np.concatenate([np.zeros(2 * n), np.ones(n), np.zeros(S * n)])[None, :])
    rhs.append([cap])
    c = np.concatenate([np.full(2 * n, _EPS_MOVE), np.full(n, _EPS_BUY), np.full(S * n, -1.0 / S)])
    bounds = ([(0, params.flex_share * x) for x in p_load] + [(0, params.flex_cap * x) for x in p_load]
              + [(0, a) for a in avail] + [(0, None)] * (S * n))
    res = linprog(c, A_ub=np.vstack(rows), b_ub=np.concatenate(rhs),
                  A_eq=np.concatenate([np.ones(n), -np.ones(n), np.zeros(n + S * n)])[None, :], b_eq=[0.0],
                  bounds=bounds, method="highs")
    if res.status != 0:
        raise RuntimeError(f"day LP failed: {res.message}")
    out, inn = res.x[:n], res.x[n:2 * n]
    buy = np.clip(res.x[2 * n:3 * n], 0, avail)
    if buy.sum() > cap:
        buy *= cap / buy.sum()
    return inn - out, buy


def execute_day(load: np.ndarray, shift: np.ndarray, buy: np.ndarray, avail: np.ndarray,
                params: AgentParams) -> tuple[np.ndarray, np.ndarray]:
    """Apply a plan to what actually happened. Deferral is limited by the flexible part of ACTUAL load;
    deferred energy is re-placed in the planned hours (energy conserved). Purchases are limited by
    ACTUAL available clean production."""
    out = np.minimum(-np.minimum(shift, 0), params.flex_share * load)
    moved = out.sum()
    inc = np.maximum(shift, 0)
    add = inc / inc.sum() * moved if inc.sum() > 0 else np.zeros_like(load)
    new_load = load - out + add
    bought = np.minimum(buy, np.maximum(avail, 0))
    return new_load, bought


class RollingBudget:
    """The certificate budget as it is known at each decision (D-1 17:30 UTC).
    Each day adds budget_day; unused balance carries forward, capped at BALANCE_CAP_DAYS days of budget.
    The day's spend is limited by spend_cap = min(balance, alpha * budget_day). A plan reserves its planned
    purchases at decision time; the part that could not be bought (actual availability was lower) is refunded
    only once that day is over, i.e. from the decision two days later. So no plan depends on the outcome of a
    day that has not finished, and cumulative purchases never exceed the cumulative budget.
    With alpha = 1 the spend cap is always exactly budget_day: the v1 budget that expired at midnight."""

    def __init__(self, budget_day: float, alpha: float):
        self.bd, self.alpha = float(budget_day), float(alpha)
        self.balance, self.cap, self.i = 0.0, 0.0, -1
        self._refunds: dict[int, float] = {}
        self.trace: list[dict] = []
        self._added = self._realised = 0.0

    def open_day(self) -> float:
        self.i += 1
        self.balance += self._refunds.pop(self.i, 0.0)
        self.balance = min(self.balance + self.bd, BALANCE_CAP_DAYS * self.bd)
        self._added += self.bd
        self.cap = min(self.balance, self.alpha * self.bd)
        return self.cap

    def close_day(self, planned: float, realised: float) -> dict:
        planned = min(float(planned), self.cap)
        rec = {"balance_at_decision": self.balance, "spend_cap": self.cap, "planned": planned,
               "realised": float(realised)}
        self.balance -= planned
        self._refunds[self.i + 2] = self._refunds.get(self.i + 2, 0.0) + max(planned - float(realised), 0.0)
        self._realised += float(realised)
        rec |= {"cumulative_budget": self._added, "cumulative_realised": self._realised}
        self.trace.append(rec)
        return rec


def _plan(policy: str, p_load, p_cert_point, cert_scen, p_avail, cap, params):
    if policy == "greedy":
        return plan_day(p_load, p_cert_point, p_avail, cap, params)
    if policy == "lp":
        return plan_day_lp(p_load, cert_scen, p_avail, cap, params)
    raise ValueError(f"unknown policy {policy}")


def plan_json(day: pd.Timestamp, shift: np.ndarray, buy: np.ndarray, p_load: np.ndarray, p_cert: np.ndarray,
              model_tag: str, extra: dict | None = None) -> bytes:
    """Canonical bytes of a day plan (this is what gets hashed and committed on-chain)."""
    return json.dumps({
        "agent": AGENT_ID, "day_utc": day.strftime("%Y-%m-%d"), "model": model_tag,
        "shift_mwh": [round(float(x), 3) for x in shift], "buy_mwh": [round(float(x), 3) for x in buy],
        "pred_load_mwh": [round(float(x), 3) for x in p_load], "pred_cert_mwh": [round(float(x), 3) for x in p_cert],
    } | (extra or {}), separators=(",", ":"), sort_keys=True).encode()


# ------------------------------------------------------------------ simulation
def _simulate(df: pd.DataFrame, days: list, fc: Forecasts, cfg: AgentConfig, params: AgentParams, k: float,
              budget_day: float, oracle_cache: dict | None = None) -> dict:
    """Run the agent day by day (decide on predictions, execute on actuals) plus the perfect-foresight reference:
    the SAME policy and the SAME budget rule, fed with actual values."""
    d_all = df.assign(base_cert=k * df["wind_mwh"], avail=df["clean_mwh"] - k * df["wind_mwh"])
    p_loads = fc.load(cfg.load_model)
    scen = fc.wind_scenarios(cfg.wind_features, cfg.wind_quantiles)
    point = fc.wind_point(cfg.wind_features, cfg.wind_quantiles)
    fcs = fc.fc_filled()
    acct = RollingBudget(budget_day, cfg.alpha)
    rows, plans = [], []
    for day in days:
        d = d_all.loc[_day_index(day)]
        load, avail = d["load_mwh"].to_numpy(), d["avail"].to_numpy()
        cap = acct.open_day()
        p_cert = k * point[day]
        p_avail = np.maximum(fcs[day] - p_cert, 0)  # forecast-based availability
        shift, buy = _plan(cfg.policy, p_loads[day], p_cert, k * scen[day], p_avail, cap, params)
        a_load, a_buy = execute_day(load, shift, buy, avail, params)
        b = acct.close_day(buy.sum(), a_buy.sum())
        s_load, _ = execute_day(load, shift, np.zeros(24), avail, params)  # ablation: shifting only
        rows.append({"day": day, "load": load, "base": d["base_cert"].to_numpy(), "wind": d["wind_mwh"].to_numpy(),
                     "fc": fcs[day], "p_load": p_loads[day], "p_wind": point[day], "scen": scen[day],
                     "agent_load": a_load, "agent_buy": a_buy, "shift_only_load": s_load})
        plans.append((day, shift, buy, p_loads[day], p_cert, b))
    key = (cfg.policy, cfg.alpha)
    if oracle_cache is None or key not in oracle_cache:
        o_acct, oracle = RollingBudget(budget_day, cfg.alpha), []
        for day in days:
            d = d_all.loc[_day_index(day)]
            load, base, avail = d["load_mwh"].to_numpy(), d["base_cert"].to_numpy(), d["avail"].to_numpy()
            cap = o_acct.open_day()
            o_shift, o_buy = _plan(cfg.policy, load, base, base[None, :], avail, cap, params)
            o_load, o_bought = execute_day(load, o_shift, o_buy, avail, params)
            o_acct.close_day(o_buy.sum(), o_bought.sum())
            oracle.append((o_load, o_bought))
        if oracle_cache is None:
            oracle_cache = {}
        oracle_cache[key] = oracle
    for r, (o_load, o_buy) in zip(rows, oracle_cache[key]):
        r["oracle_load"], r["oracle_buy"] = o_load, o_buy
    return {"rows": rows, "plans": plans, "budget_trace": acct.trace}


def _summarize(sim: dict, k: float) -> dict:
    rows = sim["rows"]
    cat = lambda key: np.concatenate([r[key] for r in rows])  # noqa: E731
    load, base, wind = cat("load"), cat("base"), cat("wind")
    extra_mwh = float(cat("agent_buy").sum())
    k_big = k + extra_mwh / wind.sum()  # bigger portfolio with EXACTLY the agent's realised extra MWh
    res = {
        "naive_fixed_portfolio": coverage(load, base),
        "bigger_portfolio_same_mwh": coverage(load, k_big * wind),
        "agent_shift_only": coverage(cat("shift_only_load"), base),
        "agent_shift_and_topup": coverage(cat("agent_load"), base + cat("agent_buy")),
        "perfect_foresight_bound": coverage(cat("oracle_load"), base + cat("oracle_buy")),
    }
    return {"coverage": res, "extra_mwh": extra_mwh, "extra_share": extra_mwh / load.sum(),
            "oracle_extra_mwh": float(cat("oracle_buy").sum()),
            "gain_vs_same_mwh_pp": 100 * (res["agent_shift_and_topup"] - res["bigger_portfolio_same_mwh"]),
            "gain_vs_naive_pp": 100 * (res["agent_shift_and_topup"] - res["naive_fixed_portfolio"]),
            "wind_mae_model_mwh": float(np.mean(np.abs(cat("p_wind") - wind))),
            "load_mae_used_mwh": float(np.mean(np.abs(cat("p_load") - load)))}


def _load_maes(df: pd.DataFrame, days: list, fc: Forecasts) -> dict[str, float]:
    actual = np.concatenate([df["load_mwh"].reindex(_day_index(d)).to_numpy() for d in days])
    return {kind: float(np.mean(np.abs(np.concatenate([fc.load(kind)[d] for d in days]) - actual)))
            for kind in LOAD_MODELS}


# ------------------------------------------------------------------ walk-forward backtest
def backtest(df: pd.DataFrame, params: AgentParams = AgentParams(), test_from: str | None = None,
             write: bool = True, config: AgentConfig = V1_CONFIG, test_to: str | None = None) -> dict:
    df = df.sort_index()
    k = portfolio_share(df)
    test_from = pd.Timestamp(test_from) if test_from else df.index[0].normalize() + (df.index[-1] - df.index[0]) / 2
    test_from = test_from.normalize().replace(day=1)
    days = _full_days(df, test_from, test_to)
    budget_day = params.topup_share * df["load_mwh"].sum() / (len(df) / 24)
    if config.wind_features == "area_type" and not all(c in df.columns for c in FC_AREA_COLUMNS):
        raise SystemExit("config needs area/type wind forecasts: rebuild the dataset with `python -m hourproof data fetch`")
    fc = Forecasts(df, days)
    sim = _simulate(df, days, fc, config, params, k, budget_day)
    sm = _summarize(sim, k)
    rows = sim["rows"]
    cat = lambda key: np.concatenate([r[key] for r in rows])  # noqa: E731
    load, wind = cat("load"), cat("wind")
    maes = _load_maes(df, days, fc)
    scen = np.concatenate([r["scen"] for r in rows], axis=1)
    out = {
        "agent": AGENT_ID, "version": "v1" if config == V1_CONFIG else "v2",
        "params": asdict(params), "portfolio_share_k": k,
        "test_period": [str(days[0].date()), str(days[-1].date())], "test_days": len(days),
        "extra_certificate_mwh": sm["extra_mwh"], "extra_share_of_test_load": sm["extra_share"],
        "coverage": sm["coverage"],
        "forecast_skill": {
            "wind_mae_raw_forecast_mwh": float(np.mean(np.abs(np.nan_to_num(cat("fc")) - wind))),
            "wind_mae_model_mwh": sm["wind_mae_model_mwh"],      # the agent's point wind forecast
            "load_mae_model_mwh": sm["load_mae_used_mwh"],       # the load forecast the agent actually used
            "load_mae_lag168_mwh": maes["lag168"],
            "load_forecast_used": config.load_model,
            "load_mae_residual_model_mwh": maes["residual"],
            "load_mae_selector_mwh": maes["selector"],
            "load_mae_v1_gbr_mwh": maes["v1_gbr"],
        },
        "load_mae_selector_mwh": maes["selector"],
        "wind_pinball": {f"{q:g}": pinball(wind, scen[i], q) for i, q in enumerate(config.wind_quantiles)},
        "gain_vs_same_mwh_pp": sm["gain_vs_same_mwh_pp"],
        "gain_vs_naive_pp": sm["gain_vs_naive_pp"],
        "selected_config": config.to_dict() | {"tag": config.tag()},
        "budget": {"rule": "rolling balance, capped at %d days; spend_cap = min(balance, alpha * budget_day); "
                           "unfilled purchases refunded after the day ends" % BALANCE_CAP_DAYS,
                   "budget_day_mwh": budget_day, "budget_total_mwh": budget_day * len(days),
                   "budget_total_share_of_test_load": budget_day * len(days) / load.sum(),
                   "alpha": config.alpha, "balance_cap_days": BALANCE_CAP_DAYS,
                   "max_cumulative_overspend_mwh": max(t["cumulative_realised"] - t["cumulative_budget"]
                                                       for t in sim["budget_trace"])},
        "perfect_foresight": {
            "definition": "same policy and same budget rule, fed with actual load, wind and availability",
            "extra_certificate_mwh": sm["oracle_extra_mwh"]},
        "load_selector_choices": fc.selector_choices,
        "v1_feature_fill_days": fc.v1_fill_used,
        "note": "Flexible share and top-up budget are declared scenario parameters; every MWh value is real "
                "Energinet data; decisions use only information available at D-1 17:30 UTC.",
    }
    if write:
        BACKTEST_JSON.write_text(json.dumps(out, indent=2))
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        for day, shift, buy, p_load, p_cert, b in sim["plans"]:
            m = _month(day)
            tag = hashlib.sha256(f"{m:%Y-%m}|{int((df.index < decision_time(m)).sum())}|{params}"
                                 .encode()).hexdigest()[:16] if config == V1_CONFIG else \
                hashlib.sha256(f"{m:%Y-%m}|{config.tag()}|{params}".encode()).hexdigest()[:16]
            extra = None if config == V1_CONFIG else {
                "version": "v2", "config": config.tag(), "budget_balance_mwh": round(b["balance_at_decision"], 3),
                "spend_cap_mwh": round(b["spend_cap"], 3)}
            (PLANS_DIR / f"{day:%Y-%m-%d}.json").write_bytes(plan_json(day, shift, buy, p_load, p_cert, tag, extra))
        days_df = pd.DataFrame({"hour_utc": np.concatenate([_day_index(r["day"]) for r in rows]),
                                "load_mwh": load, "agent_load_mwh": cat("agent_load"), "base_cert_mwh": cat("base"),
                                "agent_buy_mwh": cat("agent_buy"), "pred_load_mwh": cat("p_load"),
                                "pred_wind_mwh": cat("p_wind"), "wind_mwh": wind})
        days_df.to_csv(BACKTEST_JSON.with_suffix(".hours.csv"), index=False, float_format="%.4f")
    return out


# ------------------------------------------------------------------ selection on VALIDATION only
def candidate_grid(df: pd.DataFrame | None = None) -> list[AgentConfig]:
    """Full factorial over the v2 choices, simplest first (ties in validation coverage go to the earlier one).
    V1_CONFIG is the first candidate."""
    feats = [f for f in WIND_FEATURES if f == "total" or df is None or all(c in df.columns for c in FC_AREA_COLUMNS)]
    return [AgentConfig(policy=p, alpha=a, load_model=lm, wind_features=wf, wind_quantiles=q)
            for p, a, lm, wf, q in product(POLICIES, ALPHAS, LOAD_MODELS, feats, QUANTILE_SETS)]


def select_config(df: pd.DataFrame, candidates: list[AgentConfig], val_start, val_end,
                  params: AgentParams = AgentParams(), report: dict | None = None) -> AgentConfig:
    """Pick the configuration with the highest walk-forward agent coverage on [val_start, val_end).
    Structural guarantee: the first statement drops every row at or after val_end; everything below (the
    portfolio share, the daily budget, all models) is computed from the remaining rows only.
    Eligible: load forecast in SELECTABLE_LOAD_MODELS with validation MAE no worse than last week's value."""
    vis = df[df.index < pd.Timestamp(val_end)].sort_index()
    days = _full_days(vis, val_start, val_end)
    k = portfolio_share(vis)
    budget_day = params.topup_share * vis["load_mwh"].sum() / (len(vis) / 24)
    fc, oracle_cache = Forecasts(vis, days), {}
    maes = _load_maes(vis, days, fc)
    results = []
    for i, cfg in enumerate(candidates):
        if cfg.wind_features == "area_type" and not all(c in vis.columns for c in FC_AREA_COLUMNS):
            continue
        sm = _summarize(_simulate(vis, days, fc, cfg, params, k, budget_day, oracle_cache), k)
        results.append({"order": i, "tag": cfg.tag(), "config": cfg.to_dict(),
                        "eligible": cfg.load_model in SELECTABLE_LOAD_MODELS and maes[cfg.load_model] <= maes["lag168"],
                        "validation_coverage": sm["coverage"]["agent_shift_and_topup"],
                        "coverage": sm["coverage"], "extra_share_of_val_load": sm["extra_share"],
                        "gain_vs_same_mwh_pp": sm["gain_vs_same_mwh_pp"],
                        "wind_mae_model_mwh": sm["wind_mae_model_mwh"], "load_mae_mwh": maes[cfg.load_model]})
    eligible = [r for r in results if r["eligible"]]
    if not eligible:
        raise RuntimeError("no eligible candidate")
    best = max(eligible, key=lambda r: (r["validation_coverage"], -r["order"]))
    if report is not None:
        report.update({
            "validation_period": [str(days[0].date()), str(days[-1].date())], "validation_days": len(days),
            "visible_rows_until": str(vis.index[-1]), "portfolio_share_k": k, "budget_day_mwh": budget_day,
            "selection_metric": "validation coverage (agent_shift_and_topup); ties -> simpler (earlier) candidate",
            "eligibility": f"load forecast in {list(SELECTABLE_LOAD_MODELS)} and its validation MAE <= last-week "
                           "(lag168) validation MAE; other load models are evaluated for the ablation only",
            "load_mae_validation_mwh": maes, "load_selector_choices": fc.selector_choices,
            "selected": best, "candidates": results, "ablation": _ablation(results)})
    return AgentConfig.from_dict(best["config"])


def _ablation(results: list[dict]) -> dict:
    """On VALIDATION: each fix alone on top of v1, and the fixes added cumulatively in the order A..E."""
    by = {r["tag"]: r for r in results}

    def get(cfg: AgentConfig):
        r = by.get(cfg.tag())
        return None if r is None else {"tag": cfg.tag(), "validation_coverage": r["validation_coverage"],
                                       "extra_share_of_val_load": r["extra_share_of_val_load"],
                                       "perfect_foresight_bound": r["coverage"]["perfect_foresight_bound"],
                                       "eligible": r["eligible"]}

    def best(cfgs):
        got = [g for g in (get(c) for c in cfgs) if g]
        return max(got, key=lambda g: g["validation_coverage"]) if got else None

    v1 = V1_CONFIG
    alone = {
        "v1": get(v1),
        "A_pacing (best alpha)": best([AgentConfig(alpha=a) for a in ALPHAS]),
        "B_load_residual_model": get(AgentConfig(load_model="residual")),
        "B_load_selector": get(AgentConfig(load_model="selector")),
        "B_load_last_week": get(AgentConfig(load_model="lag168")),
        "C_wind_area_type": get(AgentConfig(wind_features="area_type")),
        "D_quantiles (best set)": best([AgentConfig(wind_quantiles=q) for q in QUANTILE_SETS[1:]]),
        "E_lp": get(AgentConfig(policy="lp")),
    }
    steps, cur = [("v1", v1)], v1
    for name, options in (("+A pacing", [dict(alpha=a) for a in ALPHAS]),
                          ("+B load selector", [dict(load_model="selector")]),
                          ("+C wind area/type", [dict(wind_features="area_type")]),
                          ("+D quantiles", [dict(wind_quantiles=q) for q in QUANTILE_SETS]),
                          ("+E lp", [dict(policy="lp")]),
                          ("+E lp, quantiles re-chosen", [dict(policy="lp", wind_quantiles=q) for q in QUANTILE_SETS])):
        cands = [AgentConfig.from_dict(cur.to_dict() | o) for o in options]
        b = best(cands)
        if b:
            cur = AgentConfig.from_dict(by[b["tag"]]["config"])
        steps.append((name, cur))
    return {"each_fix_alone_on_v1": alone,
            "cumulative": [{"step": n} | (get(c) or {"tag": c.tag()}) for n, c in steps]}


def frozen_config(params: AgentParams = AgentParams()) -> AgentConfig | None:
    if not AGENT_CONFIG_JSON.exists():
        return None
    j = json.loads(AGENT_CONFIG_JSON.read_text())
    if j["params"] != asdict(params):
        raise SystemExit(f"{AGENT_CONFIG_JSON} was selected for params {j['params']}, not {asdict(params)}")
    return AgentConfig.from_dict(j["config"])


def freeze(df: pd.DataFrame, params: AgentParams = AgentParams(), force: bool = False) -> AgentConfig:
    """Select the configuration on VALIDATION and freeze it (data/agent_config.json + agent_experiments.json)."""
    if AGENT_CONFIG_JSON.exists() and not force:
        raise SystemExit(f"{AGENT_CONFIG_JSON} already exists. Re-selecting after the TEST run would invalidate "
                         "the test; pass --force only if you mean it.")
    p = periods(df)
    report: dict = {"train_period": p["train"], "test_period_not_used": p["test"]}
    cfg = select_config(df, candidate_grid(df), *p["validation"], params=params, report=report)
    text = json.dumps(report, indent=1, default=str)
    AGENT_EXPERIMENTS_JSON.write_text(text)
    AGENT_CONFIG_JSON.write_text(json.dumps({
        "config": cfg.to_dict(), "tag": cfg.tag(), "params": asdict(params), "selected_on": p["validation"],
        "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiments_sha256": hashlib.sha256(text.encode()).hexdigest()}, indent=2))
    return cfg


def run_backtest(df: pd.DataFrame, params: AgentParams = AgentParams(), write: bool = True) -> dict:
    """The TEST run: the frozen configuration (selected on validation first, if none is frozen yet)."""
    cfg = frozen_config(params) or freeze(df, params)
    out = backtest(df, params, test_from=periods(df)["test"][0], write=write, config=cfg)
    if AGENT_EXPERIMENTS_JSON.exists():
        sel = json.loads(AGENT_EXPERIMENTS_JSON.read_text())["selected"]
        out["validation"] = {k: sel[k] for k in ("validation_coverage", "coverage", "extra_share_of_val_load",
                                                 "gain_vs_same_mwh_pp", "load_mae_mwh", "wind_mae_model_mwh")}
        out["validation"]["period"] = list(periods(df)["validation"])
        if write:
            BACKTEST_JSON.write_text(json.dumps(out, indent=2))
    return out


def ml_ablation(df: pd.DataFrame, params: AgentParams = AgentParams()) -> dict:
    """What the learned models contribute, on TEST, with the FROZEN config otherwise unchanged (nothing is
    re-selected or retuned): (1) wind = Energinet's published day-ahead forecast as one point scenario,
    (2) load = last week's value, (3) both. Writes data/agent_ml_ablation.json; agent_backtest.json is untouched."""
    cfg = frozen_config(params)
    if cfg is None:
        raise SystemExit("no frozen config: run `python -m hourproof agent select` first")
    raw_wind = {"wind_features": "raw_forecast", "wind_quantiles": []}
    variants = {"v2 (frozen)": {}, "wind = raw day-ahead forecast": raw_wind,
                "load = last week": {"load_model": "lag168"}, "both": raw_wind | {"load_model": "lag168"}}
    out = {"frozen_config": cfg.tag(), "period": "test", "variants": {}}
    for name, change in variants.items():
        c = AgentConfig.from_dict(cfg.to_dict() | change)
        r = backtest(df, params, test_from=periods(df)["test"][0], write=False, config=c)
        out["variants"][name] = {"tag": c.tag(), "coverage": r["coverage"], "gain_vs_same_mwh_pp": r["gain_vs_same_mwh_pp"],
                                 "extra_share_of_test_load": r["extra_share_of_test_load"],
                                 "extra_certificate_mwh": r["extra_certificate_mwh"],
                                 "wind_mae_point_mwh": r["forecast_skill"]["wind_mae_model_mwh"],
                                 "load_mae_used_mwh": r["forecast_skill"]["load_mae_model_mwh"]}
    ML_ABLATION_JSON.write_text(json.dumps(out, indent=2))
    return out


def sensitivity(df: pd.DataFrame, flex_values=(0.0, 0.05, 0.10, 0.20), topup_values=(0.0, 0.05),
                config: AgentConfig = V1_CONFIG) -> list[dict]:
    rows = []
    for f in flex_values:
        for t in topup_values:
            r = backtest(df, AgentParams(flex_share=f, topup_share=t), write=False, config=config)
            rows.append({"flex_share": f, "topup_share": t, **r["coverage"]})
    return rows
