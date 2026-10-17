"""Dashboard + JSON API (Starlette). Start with:  python -m hourproof serve"""
from __future__ import annotations

import contextlib
import functools
import io
import json
import threading
from pathlib import Path

import pandas as pd
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .config import BACKTEST_JSON, CARBON_BACKTEST_JSON, DATA, DATASET_CSV, DATASET_META, DEMO_STATE, LIVE_JSON, WEB
from . import zk

_run_lock = threading.Lock()
_log = io.StringIO()
_running = {"active": False}


def _read(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


async def index(_: Request):
    return FileResponse(WEB / "index.html")


@functools.lru_cache(maxsize=4)
def _annual_match(dataset_mtime: float, backtest_mtime: float) -> float | None:
    """The fixed portfolio's ANNUAL match: portfolio share k (stored by the agent backtest) x annual wind / annual
    load, from the hourly dataset. The portfolio is sized so this is 100 %; computing it keeps the hero honest."""
    bt = _read(BACKTEST_JSON)
    if not bt or not DATASET_CSV.exists():
        return None
    df = pd.read_csv(DATASET_CSV, usecols=["load_mwh", "wind_mwh"])
    return float(bt["portfolio_share_k"] * df["wind_mwh"].sum() / df["load_mwh"].sum())


async def overview(_: Request):
    demo = _read(DEMO_STATE)
    am = (_annual_match(DATASET_CSV.stat().st_mtime, BACKTEST_JSON.stat().st_mtime)
          if DATASET_CSV.exists() and BACKTEST_JSON.exists() else None)
    return JSONResponse({
        "dataset": _read(DATASET_META),
        "annual_match": am,
        "backtest": _read(BACKTEST_JSON),
        "zk": _read(zk.ZK_META),
        "demo": demo,
        "live": _read(LIVE_JSON),
        "running": _running["active"],
    })


async def week(_: Request):
    """Hourly series for one week: public (certificates) and the buyer's private load view.
    Uses the last demo run's window, or a week from the agent backtest if no run exists yet."""
    demo = _read(DEMO_STATE)
    hours_csv = BACKTEST_JSON.with_suffix(".hours.csv")
    if not hours_csv.exists():
        return JSONResponse({"available": False})
    h = pd.read_csv(hours_csv, parse_dates=["hour_utc"]).set_index("hour_utc")
    if demo and "window" in demo:
        start = pd.Timestamp(demo["window"]["window_start_utc"])
        source = "demo run " + demo["run_id"]
    else:
        start = next(ws for ws in pd.date_range(h.index.min().normalize(), h.index.max(), freq="W-MON")
                     if len(h.loc[ws: ws + pd.Timedelta(hours=167)]) == 168)
        source = "agent backtest (no on-chain run yet)"
    sel = h.loc[start: start + pd.Timedelta(hours=167)].copy()
    ch_csv = CARBON_BACKTEST_JSON.with_suffix(".hours.csv")
    if demo and demo.get("mode") == "carbon" and ch_csv.exists():  # the buyer's load followed the carbon plan
        ch = pd.read_csv(ch_csv, parse_dates=["hour_utc"]).set_index("hour_utc")["carbon_model_load"]
        if ch.reindex(sel.index).notna().all():
            sel["agent_load_mwh"] = ch.reindex(sel.index).to_numpy()
            source += ", carbon-aware load"
    base = sel["base_cert_mwh"].to_numpy()
    top = sel["agent_buy_mwh"].to_numpy()
    cov = lambda load, cert: float((pd.Series(load).clip(upper=pd.Series(cert)).sum()) / pd.Series(load).sum())  # noqa: E731
    return JSONResponse({
        "available": True, "source": source, "window_start_utc": str(start),
        "hours": [str(t) for t in sel.index],
        "base_mwh": [round(x, 3) for x in base.tolist()],
        "topup_mwh": [round(x, 3) for x in top.tolist()],
        "private_agent_load_mwh": [round(x, 3) for x in sel["agent_load_mwh"].tolist()],
        "private_naive_load_mwh": [round(x, 3) for x in sel["load_mwh"].tolist()],
        "coverage_naive": cov(sel["load_mwh"].to_numpy(), base),
        "coverage_agent": cov(sel["agent_load_mwh"].to_numpy(), base + top),
    })


STRATEGY_LABELS = {"no_shift": "No shift", "shift_for_mwh": "Shift for MWh matching",
                   "carbon_persist": "Carbon-aware, last week's intensity", "carbon_model": "Carbon-aware, learned forecast",
                   "carbon_perfect": "Carbon-aware, actual intensity (reference)"}


async def carbon_view(_: Request):
    """Carbon panel: the five strategies (TEST, Jul-Dec 2025), and one week of hourly intensity: the last
    carbon-aware demo run's week (with its on-chain proof), or the kill test's K4 week from the backtest."""
    bt = _read(CARBON_BACKTEST_JSON)
    if not bt or "strategies" not in bt:
        return JSONResponse({"available": False})
    out = {"available": True, "test_period": bt["periods"]["test"], "test_hours": bt["test_hours"],
           "mae": bt["forecast"]["test_mae_g_per_kwh"],
           "improvement_vs_best_persistence": bt["forecast"]["improvement_vs_best_persistence"],
           "strategies": [{"id": k, "label": STRATEGY_LABELS[k], "reference": k == "carbon_perfect", **v}
                          for k, v in bt["strategies"].items()],
           "robustness": {k: v for k, v in bt["robustness"].items() if isinstance(v, dict)},
           "frozen_config": {k: bt["frozen_config"][k] for k in ("flex_share", "flex_cap")},
           "caveats": bt["caveats"]}
    demo = _read(DEMO_STATE)
    w = (demo or {}).get("window", {})
    if demo and demo.get("mode") == "carbon" and "intensity_g_per_kwh" in w:
        steps = {s["id"]: s for s in demo["steps"]}
        em = steps.get("prove_emissions", {}).get("metrics", {})
        out["week"] = {"source": f"demo run {demo['run_id']} ({demo['status']})", "hours": w["hours"],
                       "intensity": w["intensity_g_per_kwh"], "forecast": w["co2_forecast_g_per_kwh"],
                       "shift_mwh": w["planned_shift_mwh"], "mae": w.get("co2_mae_week_g_per_kwh")}
        if em.get("proven_residual_kg") is not None:
            note = steps.get("note", {}).get("metrics", {})
            out["proof"] = {"residual_kg": em["proven_residual_kg"], "coverage_bps": em["threshold_bps"],
                            "gas": em.get("verify_gas"), "zk_mode": demo["zk_mode"], "network": demo["network"],
                            "target_kg": em.get("target_residual_kg"), "kpi_met": note.get("kpi_met"),
                            "coupon_bps": note.get("coupon_bps")}
    else:
        h = pd.read_csv(CARBON_BACKTEST_JSON.with_suffix(".hours.csv"), parse_dates=["hour_utc"]).set_index("hour_utc")
        from .carbon import K4_WEEK
        sel = h.loc[K4_WEEK: K4_WEEK + pd.Timedelta(hours=167)]
        if len(sel) == 168:
            out["week"] = {"source": "carbon backtest (no carbon-aware run yet)", "hours": [str(t) for t in sel.index],
                           "intensity": [round(x, 2) for x in sel["co2_actual"]],
                           "forecast": [round(x, 2) for x in sel["co2_forecast"]],
                           "shift_mwh": [round(a - b, 3) for a, b in zip(sel["carbon_model_load"], sel["load"])]}
        fx = _read(DATA / "zk_emissions_fixture.json")
        if fx:
            out["proof"] = {"residual_kg": fx["cap_kg"], "coverage_bps": fx["threshold_bps"], "zk_mode": "real",
                            "network": None, "fixture_week": fx["week_utc"][:10]}
    return JSONResponse(out)


def _run_demo(network: str, zk_mode: str, target_bps: int, mode: str = "carbon") -> None:
    from .demo import Run
    try:
        with contextlib.redirect_stdout(_log):
            Run(network=network, zk_mode=zk_mode, target_bps=target_bps, mode=mode).execute()
    finally:
        _running["active"] = False
        _run_lock.release()


async def run_demo(request: Request):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    network = body.get("network", "local")
    zk_mode = body.get("zk_mode", "real")
    target = int(body.get("target_bps", 7500))
    mode = body.get("mode", "carbon")
    if network not in ("local", "base-sepolia") or zk_mode not in ("real", "mock") or not 1 <= target <= 10000             or mode not in ("carbon", "procurement"):
        return JSONResponse({"error": "bad parameters"}, status_code=400)
    if not _run_lock.acquire(blocking=False):
        return JSONResponse({"error": "a run is already in progress"}, status_code=409)
    _running["active"] = True
    _log.seek(0)
    _log.truncate()
    threading.Thread(target=_run_demo, args=(network, zk_mode, target, mode), daemon=True).start()
    return JSONResponse({"started": True}, status_code=202)


async def run_log(_: Request):
    return JSONResponse({"running": _running["active"], "log": _log.getvalue()[-20000:]})


app = Starlette(routes=[
    Route("/", index),
    Route("/api/overview", overview),
    Route("/api/week", week),
    Route("/api/carbon", carbon_view),
    Route("/api/demo/run", run_demo, methods=["POST"]),
    Route("/api/demo/log", run_log),
    Mount("/static", StaticFiles(directory=WEB), name="static"),
])
