"""TEST-ONLY synthetic hourly year. Used by unit tests to exercise code paths without network.
Never used by the demo: dataset.load(require_real=True) refuses data marked synthetic."""
import numpy as np
import pandas as pd


def synthetic_year(seed: int = 0, year: int = 2025) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", inclusive="left")
    n = len(idx)
    # wind: persistent weather regimes (AR(1) on a daily scale) + noise
    reg = np.zeros(n)
    for i in range(1, n):
        reg[i] = 0.995 * reg[i - 1] + rng.normal(0, 0.08)
    wind = np.clip(2500 + 1800 * np.tanh(reg) + rng.normal(0, 150, n), 50, None)
    fc = np.clip(wind * (1 + rng.normal(0, 0.12, n)), 0, None)
    solar = np.clip(600 * np.sin((idx.hour - 6) / 12 * np.pi), 0, None) * (1 + 0.5 * np.sin(2 * np.pi * idx.dayofyear / 365 - 1.4))
    load = 100 + 15 * np.sin((idx.hour - 8) / 24 * 2 * np.pi) - 8 * (idx.dayofweek >= 5) + rng.normal(0, 3, n)
    return pd.DataFrame({"load_mwh": load, "wind_mwh": wind, "clean_mwh": wind + solar + 20,
                         "wind_fc_da_mwh": fc}, index=pd.DatetimeIndex(idx, name="hour_utc"))


def with_area_forecasts(df: pd.DataFrame, seed: int = 1) -> pd.DataFrame:
    """TEST-ONLY: split the synthetic day-ahead forecast into DK1/DK2 x offshore/onshore columns."""
    from hourproof.dataset import FC_AREA_COLUMNS
    rng = np.random.default_rng(seed)
    w = rng.dirichlet([4, 5, 3, 1], size=len(df))
    return df.assign(**{c: df["wind_fc_da_mwh"].to_numpy() * w[:, i] for i, c in enumerate(FC_AREA_COLUMNS)})
