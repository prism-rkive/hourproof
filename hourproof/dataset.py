"""Build the real hourly dataset the whole project runs on.

Sources (Energinet, Energi Data Service, keyless; see https://www.energidataservice.dk):
  * DeclarationProduction (Version=Final): hourly production by type, DK1+DK2
  * ConsumptionDK3619IndustryHour: hourly consumption of one Danish industry branch (the buyer)
  * Forecasts_Hour: day-ahead wind forecasts (published 18:00 Danish time the day before)

Output: data/hourly.csv (UTC hours) + data/hourly_meta.json. Nothing is simulated.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import eds
from .config import CARBON_CSV, CARBON_META, DATASET_CSV, DATASET_META

WIND_RE, SOLAR_RE, CLEAN_RE = r"(?i)wind|vind", r"(?i)sol", r"(?i)wind|vind|sol|hydro|vand"
DEFAULT_BRANCH_HINT = r"(?i)informat|it-|data|telekom|kommunik"
COLUMNS = ["load_mwh", "wind_mwh", "clean_mwh", "wind_fc_da_mwh"]
# day-ahead wind forecasts by price area and type (optional; absent in datasets made by `data import`)
FC_AREA_COLUMNS = ["wind_fc_da_dk1_offshore_mwh", "wind_fc_da_dk1_onshore_mwh",
                   "wind_fc_da_dk2_offshore_mwh", "wind_fc_da_dk2_onshore_mwh"]


def _choose_method(year: int) -> tuple[str, str, dict]:
    """FuelAllocationMethod row sets differ; pick the one whose wind matches the settlement series."""
    p0, p1 = pd.Timestamp(f"{year}-06-01"), pd.Timestamp(f"{year}-06-08")
    probe = eds.fetch("DeclarationProduction", p0, p1, filt={"PriceArea": ["DK1", "DK2"]},
                      columns=["HourUTC", "PriceArea", "Version", "FuelAllocationMethod", "ProductionType", "Production_MWh"])
    version = next(v for v in ("Final", "Preliminary", "Initial") if v in set(probe["Version"]))
    pv = probe[(probe["Version"] == version) & probe["ProductionType"].str.contains(WIND_RE)]
    st = eds.fetch("ProductionConsumptionSettlement", p0, p1, filt={"PriceArea": ["DK1", "DK2"]})
    wcols = [c for c in st.columns if re.search(r"Wind", c)]
    st["w"] = st[wcols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    ref = st.groupby("HourUTC")["w"].sum()
    ok = ref > 100
    score = {}
    for m, g in pv.groupby("FuelAllocationMethod"):
        w = g.groupby("HourUTC")["Production_MWh"].sum().reindex(ref.index)
        score[m] = float(((w[ok] - ref[ok]).abs() / ref[ok]).median()) if ok.any() else math.inf
    method = min(score, key=score.get)
    print(f"   DeclarationProduction: Version={version}, FuelAllocationMethod={method}; wind error by method {score}")
    return version, method, score


def build(year: int = 2025, branch_code: str | None = None, branch_hint: str = DEFAULT_BRANCH_HINT) -> pd.DataFrame:
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year + 1}-01-01")
    s, e = start - pd.Timedelta(days=1), end + pd.Timedelta(days=1)
    version, method, score = _choose_method(year)

    dp = eds.fetch("DeclarationProduction", s, e,
                   filt={"PriceArea": ["DK1", "DK2"], "Version": [version], "FuelAllocationMethod": [method]},
                   columns=["HourUTC", "PriceArea", "ProductionType", "Production_MWh"])
    piv = dp.pivot_table(index="HourUTC", columns="ProductionType", values="Production_MWh", aggfunc="sum").fillna(0)
    pick = lambda rx: piv[[c for c in piv.columns if re.search(rx, c)]].sum(axis=1)  # noqa: E731
    supply = pd.DataFrame({"wind_mwh": pick(WIND_RE), "clean_mwh": pick(CLEAN_RE)})

    ld = eds.fetch("ConsumptionDK3619IndustryHour", s, e, timecol="TimeUTC")
    totals = ld.groupby(["DK36Code", "DK36Title"])["Consumption_MWh"].sum().sort_values(ascending=False)
    if branch_code is None:
        cands = [c for (c, t) in totals.index if re.search(branch_hint, str(t))]
        branch_code = cands[0] if cands else totals.index[0][0]
    title = str(ld.loc[ld["DK36Code"] == branch_code, "DK36Title"].iloc[0])
    load = ld[ld["DK36Code"] == branch_code].groupby("TimeUTC")["Consumption_MWh"].sum().rename("load_mwh")
    load.index.name = "HourUTC"

    fc = eds.fetch("Forecasts_Hour", s, e, filt={"PriceArea": ["DK1", "DK2"]})
    fc = fc[fc["ForecastType"].str.contains("wind", case=False)]
    fc["ForecastDayAhead"] = pd.to_numeric(fc["ForecastDayAhead"], errors="coerce")
    fcw = fc.groupby("HourUTC")["ForecastDayAhead"].sum(min_count=1).rename("wind_fc_da_mwh")
    kind = np.where(fc["ForecastType"].str.contains("offshore", case=False), "offshore", "onshore")
    fc["col"] = "wind_fc_da_" + fc["PriceArea"].str.lower() + "_" + kind + "_mwh"
    fca = fc.groupby(["HourUTC", "col"])["ForecastDayAhead"].sum(min_count=1).unstack("col").reindex(columns=FC_AREA_COLUMNS)

    df = supply.join(load, how="inner").join(fcw, how="left").join(fca, how="left")
    df = df[(df.index >= start) & (df.index < end)]
    df = df[df["load_mwh"] > 0].sort_index()
    df.index.name = "hour_utc"
    _write(df, {
        "source": "energidataservice.dk (Energinet)",
        "datasets": ["DeclarationProduction", "ConsumptionDK3619IndustryHour", "Forecasts_Hour"],
        "year": year, "declaration_version": version, "fuel_allocation_method": method,
        "method_wind_error_vs_settlement": score,
        "note_on_sources": "DeclarationProduction and ProductionConsumptionSettlement are derived from the same "
                           "settlement data, so they are NOT independent sources.",
        "buyer_branch": f"{branch_code} {title}", "buyer_label": title,
    })
    return df


def import_k1_csv(path: str, label: str | None = None) -> pd.DataFrame:
    """Reuse data/hourly_2025.csv produced by the Colab kill test (K1) instead of downloading again."""
    k = pd.read_csv(path, index_col=0, parse_dates=True)
    need = {"load": "load_mwh", "wind_decl": "wind_mwh", "clean_decl": "clean_mwh", "wind_fc_da": "wind_fc_da_mwh"}
    missing = [c for c in need if c not in k.columns]
    if missing:
        raise SystemExit(f"{path} is not a K1 hourly file (missing {missing})")
    df = k[list(need)].rename(columns=need).dropna(subset=["load_mwh", "wind_mwh"])
    df.index.name = "hour_utc"
    year = int(df.index[len(df) // 2].year)
    _write(df.sort_index(), {"source": "energidataservice.dk (Energinet), imported from kill-test K1 file",
                             "datasets": ["DeclarationProduction", "ConsumptionDK3619IndustryHour", "Forecasts_Hour"],
                             "year": year, "imported_from": str(path),
                             "buyer_branch": label or "Danish industry branch from the K1 run",
                             "buyer_label": label or "Danish industry branch"})
    return df


def _write(df: pd.DataFrame, meta: dict) -> None:
    df.to_csv(DATASET_CSV, float_format="%.6f")
    k = df["load_mwh"].sum() / df["wind_mwh"].sum()
    base = np.minimum(df["load_mwh"], k * df["wind_mwh"]).sum() / df["load_mwh"].sum()
    meta |= {"hours": int(len(df)), "first": str(df.index.min()), "last": str(df.index.max()),
             "annual_load_mwh": float(df["load_mwh"].sum()),
             "hourly_match_of_100pct_annual_wind": float(base),
             "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "synthetic": False}
    DATASET_META.write_text(json.dumps(meta, indent=2))
    print(f"   wrote {DATASET_CSV} ({len(df)} hours); 100% annual wind -> {base:.1%} hourly")


# ------------------------------------------------------------------ carbon-aware mode
# Ported from the carbon kill test (notebooks/, cells 2-3). Kept in its own file: data/carbon_hourly.csv.
CARBON_FC_COLUMNS = ["fc_DK1_offshore_wind", "fc_DK1_onshore_wind", "fc_DK1_solar",
                     "fc_DK2_offshore_wind", "fc_DK2_onshore_wind", "fc_DK2_solar"]
CARBON_COLUMNS = ["wind_mwh", "co2_g_per_kwh", "load_mwh", *CARBON_FC_COLUMNS, "price_eur"]
INTENSITY_VERSION, INTENSITY_METHOD = "Final", "125%"  # Danish declaration convention (125 % fuel allocation)
PRICE_SWITCH = pd.Timestamp("2025-10-01")  # Elspotprices (hourly) before, DayAheadPrices (15-minute) from here
_BUYER_WORDS = ("informat", "telekom", "it-")


def grid_intensity(ge: pd.DataFrame, cons_area: pd.DataFrame, version: str = INTENSITY_VERSION,
                   method: str = INTENSITY_METHOD) -> pd.Series:
    """DeclarationGridEmission CO2PerkWh (g/kWh) for one Version and FuelAllocationMethod, weighted over DK1 and
    DK2 by each area's GrossConsumptionMWh (ProductionConsumptionSettlement)."""
    g = ge[(ge["Version"] == version) & (ge["FuelAllocationMethod"] == method)]
    inten_area = g.pivot_table(index="HourUTC", columns="PriceArea", values="CO2PerkWh", aggfunc="mean")
    w = cons_area.reindex(inten_area.index)
    return ((inten_area * w).sum(axis=1) / w.sum(axis=1)).rename("co2_g_per_kwh")


def consumption_by_area(st: pd.DataFrame) -> pd.DataFrame:
    st = st.assign(cons=pd.to_numeric(st["GrossConsumptionMWh"], errors="coerce"))
    return st.pivot_table(index="HourUTC", columns="PriceArea", values="cons", aggfunc="sum")


def area_forecasts(fc: pd.DataFrame) -> pd.DataFrame:
    """Forecasts_Hour ForecastDayAhead by price area and forecast type -> fc_<area>_<type> columns."""
    fc = fc.assign(ForecastDayAhead=pd.to_numeric(fc["ForecastDayAhead"], errors="coerce"))
    fc["key"] = fc["PriceArea"] + "_" + fc["ForecastType"].str.lower().str.replace(" ", "_")
    fcp = fc.pivot_table(index="HourUTC", columns="key", values="ForecastDayAhead", aggfunc="sum")
    fcp.columns = [f"fc_{c}" for c in fcp.columns]
    return fcp


def hourly_price(sp: pd.DataFrame, da: pd.DataFrame) -> pd.Series:
    """EUR/MWh, mean of DK1 and DK2: Elspotprices SpotPriceEUR before PRICE_SWITCH, then DayAheadPrices
    DayAheadPriceEUR averaged over each hour's quarter-hours."""
    sp = sp.drop_duplicates(["HourUTC", "PriceArea"]).assign(HourUTC=lambda x: pd.to_datetime(x["HourUTC"]))
    da = da.drop_duplicates(["TimeUTC", "PriceArea"]).assign(TimeUTC=lambda x: pd.to_datetime(x["TimeUTC"]))
    p1 = sp.assign(p=pd.to_numeric(sp["SpotPriceEUR"], errors="coerce")).groupby("HourUTC")["p"].mean()
    da = da.assign(p=pd.to_numeric(da["DayAheadPriceEUR"], errors="coerce"))
    p2 = da.groupby(da["TimeUTC"].dt.floor("h"))["p"].mean()
    price = pd.concat([p1[p1.index < PRICE_SWITCH], p2]).sort_index()
    return price[~price.index.duplicated()].rename("price_eur")


def build_carbon(year: int = 2025) -> pd.DataFrame:
    """Fetch everything the carbon backtest needs with the cached, rate-limit-aware client."""
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year + 1}-01-01")
    s, e = start - pd.Timedelta(days=1), end + pd.Timedelta(days=1)
    areas = {"PriceArea": ["DK1", "DK2"]}
    st = eds.fetch("ProductionConsumptionSettlement", s, e, filt=areas)
    wcols = [c for c in st.columns if "Wind" in c]
    st["wind"] = st[wcols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    wind = st.groupby("HourUTC")["wind"].sum().rename("wind_mwh")
    ge = eds.fetch("DeclarationGridEmission", s, e, filt=areas)
    if INTENSITY_VERSION not in set(ge["Version"]) or INTENSITY_METHOD not in set(ge["FuelAllocationMethod"]):
        raise SystemExit(f"DeclarationGridEmission has no Version={INTENSITY_VERSION} / {INTENSITY_METHOD} rows for {year}")
    intensity = grid_intensity(ge, consumption_by_area(st))
    fcp = area_forecasts(eds.fetch("Forecasts_Hour", s, e, filt=areas))
    ld = eds.fetch("ConsumptionDK3619IndustryHour", s, e, timecol="TimeUTC")
    tot = ld.groupby(["DK36Code", "DK36Title"])["Consumption_MWh"].sum().sort_values(ascending=False)
    code = next((c for (c, t) in tot.index if any(k in str(t).lower() for k in _BUYER_WORDS)), tot.index[0][0])
    load = ld[ld["DK36Code"] == code].groupby("TimeUTC")["Consumption_MWh"].sum().rename("load_mwh")
    load.index.name = "HourUTC"
    E = pd.concat([wind, intensity, load, fcp], axis=1)
    E = E[(E.index >= start) & (E.index < end)].sort_index()
    sp = eds.fetch("Elspotprices", s, min(e, PRICE_SWITCH), filt=areas) if s < PRICE_SWITCH else pd.DataFrame(
        columns=["HourUTC", "PriceArea", "SpotPriceEUR"])
    da = eds.fetch("DayAheadPrices", max(s, PRICE_SWITCH), e, filt=areas, timecol="TimeUTC") if e > PRICE_SWITCH \
        else pd.DataFrame(columns=["TimeUTC", "PriceArea", "DayAheadPriceEUR"])
    E["price_eur"] = hourly_price(sp, da).reindex(E.index)
    title = str(ld.loc[ld["DK36Code"] == code, "DK36Title"].iloc[0])
    _write_carbon(E, {"source": "energidataservice.dk (Energinet), fetched", "buyer_branch": f"{code} {title}"})
    return E


def _cache_records(folder: Path, dataset: str) -> pd.DataFrame:
    frames = []
    for f in sorted((folder / "cache").glob(f"{dataset}_*.json")):
        d = json.loads(f.read_text())
        frames.append(pd.DataFrame(d["records"] if isinstance(d, dict) else d))
    if not frames:
        raise SystemExit(f"no {dataset}_*.json in {folder / 'cache'}")
    return pd.concat(frames, ignore_index=True)


def import_carbon(folder: str) -> pd.DataFrame:
    """Reuse the carbon kill test's downloads (hp_ai/energinet_hourly.csv + hp_ai/cache/*.json for prices)."""
    folder = Path(folder)
    E = pd.read_csv(folder / "energinet_hourly.csv", index_col=0, parse_dates=True, float_precision="round_trip")
    missing = [c for c in CARBON_COLUMNS[:-1] if c not in E.columns]
    if missing:
        raise SystemExit(f"{folder / 'energinet_hourly.csv'} is not the kill test's hourly file (missing {missing})")
    E = E[CARBON_COLUMNS[:-1]]
    E["price_eur"] = hourly_price(_cache_records(folder, "Elspotprices"), _cache_records(folder, "DayAheadPrices")).reindex(E.index)
    _write_carbon(E, {"source": "energidataservice.dk (Energinet), imported from the carbon kill test",
                      "imported_from": str(folder), "buyer_branch": "JB_JC Telekommunikation & IT- og informationstjenester"})
    return E


def _write_carbon(E: pd.DataFrame, meta: dict) -> None:
    E = E.copy()
    E.index.name = "hour_utc"
    full = pd.date_range(E.index.min(), E.index.max(), freq="h")
    if len(full) != len(E):
        raise SystemExit(f"carbon dataset has gaps: {len(full) - len(E)} hours missing (lags are positional)")
    E.to_csv(CARBON_CSV)
    meta |= {
        "datasets": {"wind_mwh": "ProductionConsumptionSettlement, all *Wind* columns, DK1+DK2",
                     "co2_g_per_kwh": f"DeclarationGridEmission CO2PerkWh, Version={INTENSITY_VERSION}, "
                                      f"FuelAllocationMethod={INTENSITY_METHOD}, DK1/DK2 weighted by "
                                      "ProductionConsumptionSettlement GrossConsumptionMWh",
                     "load_mwh": "ConsumptionDK3619IndustryHour, IT/telecom branch",
                     "fc_*": "Forecasts_Hour ForecastDayAhead by PriceArea and ForecastType",
                     "price_eur": f"Elspotprices SpotPriceEUR before {PRICE_SWITCH.date()}, then DayAheadPrices "
                                  "DayAheadPriceEUR hourly mean; mean of DK1 and DK2"},
        "hours": int(len(E)), "first": str(E.index.min()), "last": str(E.index.max()),
        "non_missing": {c: int(E[c].notna().sum()) for c in E.columns},
        "note": "wind here is settlement wind, as in the kill test; data/hourly.csv (declared wind) is unchanged",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "synthetic": False,
    }
    CARBON_META.write_text(json.dumps(meta, indent=2))
    print(f"   wrote {CARBON_CSV} ({len(E)} hours; intensity {E['co2_g_per_kwh'].notna().mean():.1%}, "
          f"prices {E['price_eur'].notna().mean():.1%} of hours)")


def load_carbon(require_real: bool = True) -> tuple[pd.DataFrame, dict]:
    if not CARBON_CSV.exists():
        raise SystemExit("No carbon dataset yet. Run:  python -m hourproof data import-carbon hp_ai   "
                         "(or: data fetch-carbon)")
    meta = json.loads(CARBON_META.read_text()) if CARBON_META.exists() else {}
    if require_real and meta.get("synthetic", True):
        raise SystemExit("The carbon dataset is marked synthetic (test fixture).")
    E = pd.read_csv(CARBON_CSV, index_col=0, parse_dates=True, float_precision="round_trip")
    return E[CARBON_COLUMNS], meta


def load(require_real: bool = True) -> tuple[pd.DataFrame, dict]:
    if not DATASET_CSV.exists():
        raise SystemExit("No dataset yet. Run:  python -m hourproof data fetch   (or: data import <K1 hourly_2025.csv>)")
    meta = json.loads(DATASET_META.read_text()) if DATASET_META.exists() else {}
    if require_real and meta.get("synthetic", True):
        raise SystemExit("The dataset is marked synthetic (test fixture). Fetch real data: python -m hourproof data fetch")
    df = pd.read_csv(DATASET_CSV, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=False)
    return df[COLUMNS + [c for c in FC_AREA_COLUMNS if c in df.columns]], meta
