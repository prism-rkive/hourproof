"""Live mode: the agent commits tomorrow's forecast on a public chain BEFORE the day, then is scored.

  python -m hourproof live commit --network base-sepolia   # run after 18:00 Danish time
  python -m hourproof live score  --network base-sepolia   # any time after the day has ended

The commitment covers the agent's hourly prediction of the buyer's portfolio output (portfolio share
x Danish wind) for the next UTC day and, in the same hashed plan, the carbon-aware part: tomorrow's hourly CO2
intensity forecast (24 values, the frozen model trained on Final data, lag features from Energinet's Initial
version) and the planned hourly shift profile. Scoring uses Energinet's real-time declared production and the
CO2 MAE against lag168 persistence, scored against Initial and, once Energinet publishes it, Final.
Load is not part of live mode: Energinet's industry consumption feed is paused until 2027.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import agent, carbon, dataset, eds
from .chain import Chain, b32, keccak_hex
from .config import AGENT_ID, LIVE_JSON, base_sepolia_network, local_network


def _net(name: str):
    return local_network() if name == "local" else base_sepolia_network()


def _records() -> dict:
    return json.loads(LIVE_JSON.read_text()) if LIVE_JSON.exists() else {"log_contract": {}, "days": []}


def _log_contract(ch: Chain, rec: dict) -> str:
    key = f"{ch.net.name}:{ch.net.chain_id}"
    if key not in rec["log_contract"]:
        rec["log_contract"][key] = ch.deploy("AgentCommitLog", role="agent" if ch.net.name == "local" else "admin")
    return rec["log_contract"][key]


def commit(network: str = "base-sepolia", day: str | None = None) -> dict:
    df, _ = dataset.load()
    k = agent.portfolio_share(df)
    target = pd.Timestamp(day) if day else pd.Timestamp(datetime.now(timezone.utc).date()) + pd.Timedelta(days=1)
    target = target.tz_localize(None) if target.tzinfo else target
    fc_all = eds.latest("Forecasts_Hour", target, target + pd.Timedelta(days=1), filt={"PriceArea": ["DK1", "DK2"]})
    if fc_all.empty:
        raise SystemExit(f"No forecast published yet for {target:%Y-%m-%d} (it appears around 18:00 Danish time)")
    fc = fc_all[fc_all["ForecastType"].str.contains("wind", case=False)].copy()
    fc["ForecastDayAhead"] = pd.to_numeric(fc["ForecastDayAhead"], errors="coerce")
    raw = fc.groupby("HourUTC")["ForecastDayAhead"].sum(min_count=1).reindex(pd.date_range(target, periods=24, freq="h"))
    if raw.isna().any():
        raise SystemExit(f"Day-ahead forecast incomplete for {target:%Y-%m-%d} ({int(raw.isna().sum())} hours missing)")
    # train the supply model on the full real dataset, predict tomorrow from the published forecast
    hist = df.dropna(subset=["wind_fc_da_mwh"])
    X = agent.supply_features(df, hist.index)
    model = agent._model().fit(X, hist["wind_mwh"])
    fut = pd.DataFrame({"wind_fc_da_mwh": raw.to_numpy()}, index=raw.index)
    pred = np.maximum(model.predict(agent.supply_features(fut, fut.index)), 0)
    co2 = carbon_live_plan(target, fc_all)  # before any transaction: an incomplete input aborts the whole commit
    plan = json.dumps({"agent": AGENT_ID, "mode": "live", "day_utc": f"{target:%Y-%m-%d}",
                       "pred_wind_mwh": [round(float(x), 3) for x in pred],
                       "pred_portfolio_mwh": [round(float(k * x), 3) for x in pred],
                       "raw_forecast_mwh": [round(float(x), 3) for x in raw.to_numpy()],
                       "portfolio_share_k": k, "carbon": co2}, separators=(",", ":"), sort_keys=True).encode()
    h = keccak_hex(plan)
    ch = Chain(_net(network))
    rec = _records()
    log = _log_contract(ch, rec)
    day_start = int(target.tz_localize("UTC").timestamp())
    tx = ch.send(log, "commit(bytes32,uint64,bytes32)", [b32(AGENT_ID), day_start, h], role="agent" if network == "local" else "admin",
                 label=f"live commit {target:%Y-%m-%d}")
    entry = {"day": f"{target:%Y-%m-%d}", "network": network, "plan": plan.decode(), "plan_hash": h, "tx": tx.hash,
             "tx_url": tx.url, "committed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "early": datetime.now(timezone.utc).timestamp() < day_start}
    rec["days"] = [d for d in rec["days"] if not (d["day"] == entry["day"] and d["network"] == network)] + [entry]
    LIVE_JSON.write_text(json.dumps(rec, indent=2))
    print(f"committed plan for {entry['day']} ({'before' if entry['early'] else 'AFTER'} the day started): {tx.url or tx.hash}")
    return entry


AREAS = {"PriceArea": ["DK1", "DK2"]}


def _grid_emission(start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """DeclarationGridEmission (125 %, every version) for [start, end) and settlement consumption for the weights
    (from 4 weeks earlier: settlement is published ~10 days late)."""
    ge = eds.latest("DeclarationGridEmission", start, end, filt=AREAS | {"FuelAllocationMethod": ["125%"]})
    st = eds.latest("ProductionConsumptionSettlement", start - pd.Timedelta(weeks=4), end, filt=AREAS)
    if ge.empty:
        raise SystemExit(f"DeclarationGridEmission returned nothing for {start:%Y-%m-%d}..{end:%Y-%m-%d}")
    return ge, st


def carbon_live_plan(day: pd.Timestamp, fc_all: pd.DataFrame) -> dict:
    ge, st = _grid_emission(day - pd.Timedelta(days=carbon.LIVE_LAG_DAYS), day)
    da = eds.latest("DayAheadPrices", day, day + pd.Timedelta(days=1), filt=AREAS)
    if da.empty:
        raise SystemExit(f"No day-ahead prices yet for {day:%Y-%m-%d} (published around 13:00 CET)")
    return carbon.live_plan(day, ge, st, fc_all, da)


def _score_carbon(d: dict, day: pd.Timestamp) -> None:
    """Adds CO2 scores for every intensity version that is complete and not scored yet (Initial, then Final)."""
    plan = json.loads(d["plan"]).get("carbon")
    if not plan:
        return
    have = d.setdefault("co2_score", {})
    if carbon.LIVE_TRAIN_VERSION in have:
        return
    ge, st = _grid_emission(day, day + pd.Timedelta(days=1))
    for version, sc in carbon.live_score(plan, day, ge, st).items():
        if version not in have:
            have[version] = sc | {"scored_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            print(f"{d['day']}: CO2 MAE vs {version}: model {sc['mae_model_g_per_kwh']:.1f} g/kWh, "
                  f"lag168 persistence {sc['mae_lag168_g_per_kwh']:.1f} g/kWh")
    if carbon.LIVE_TRAIN_VERSION not in have:
        print(f"{d['day']}: Final intensity not published yet; rerun `live score` later to add it")


def score(network: str = "base-sepolia") -> list[dict]:
    rec = _records()
    ch = Chain(_net(network))
    out = []
    for d in rec["days"]:
        if d["network"] != network:
            continue
        day = pd.Timestamp(d["day"])
        if datetime.now(timezone.utc) < (day + pd.Timedelta(days=1, hours=2)).tz_localize("UTC"):
            continue
        _score_carbon(d, day)
        LIVE_JSON.write_text(json.dumps(rec, indent=2))
        if d.get("score"):
            continue
        act = eds.latest("DeclarationProduction", day, day + pd.Timedelta(days=1), filt={"PriceArea": ["DK1", "DK2"]})
        act = act[act["ProductionType"].str.contains("wind", case=False)]
        if "FuelAllocationMethod" in act:  # method row sets differ; "All" matched settlement wind in K1
            methods = sorted(act["FuelAllocationMethod"].unique())
            act = act[act["FuelAllocationMethod"] == ("All" if "All" in methods else methods[0])]
        actual = act.groupby("HourUTC")["Production_MWh"].sum().reindex(pd.date_range(day, periods=24, freq="h"))
        if actual.isna().any():
            print(f"{d['day']}: actual production not complete yet")
            continue
        plan = json.loads(d["plan"])
        mae_model = float(np.mean(np.abs(np.array(plan["pred_wind_mwh"]) - actual.to_numpy())))
        mae_raw = float(np.mean(np.abs(np.array(plan["raw_forecast_mwh"]) - actual.to_numpy())))
        log = rec["log_contract"][f"{ch.net.name}:{ch.net.chain_id}"]
        tx = ch.send(log, "reveal(bytes32,uint64,bytes)", [b32(AGENT_ID), int(day.tz_localize("UTC").timestamp()),
                     "0x" + d["plan"].encode().hex()], role="agent" if network == "local" else "admin", label=f"reveal {d['day']}")
        d["score"] = {"mae_model_mwh": mae_model, "mae_raw_forecast_mwh": mae_raw, "reveal_tx": tx.hash, "reveal_url": tx.url,
                      "actual_wind_mwh": [round(float(x), 3) for x in actual.to_numpy()]}
        out.append(d)
        print(f"{d['day']}: model MAE {mae_model:.0f} MWh vs raw forecast {mae_raw:.0f} MWh; revealed {tx.url or tx.hash}")
    LIVE_JSON.write_text(json.dumps(rec, indent=2))
    return out
