"""End-to-end scenario on a real week of Danish data, on a local replay chain or Base Sepolia.

Every step writes data/demo_state.json, which the dashboard polls. Attacks are executed for real and
must fail with the expected on-chain error; if one does not, the run is marked failed.

Two modes (same demo week rule):
  carbon (default) - carbon-aware: the buyer's flexible load follows the agent's committed carbon plan (CO2
      forecast + planned shift; the procurement plan's certificate purchases are kept), the oracle also posts the
      hourly grid intensity, the buyer proves coverage AND residual emissions over ONE data-hub attestation, and
      the note's KPI is RESIDUAL_EMISSIONS with a target set by a rule fixed in code (residual_target).
  procurement - the original scenario: load follows the procurement agent's MWh shift, coverage KPI note.
"""
from __future__ import annotations

import json
import secrets
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import agent, carbon, dataset, pq, zk
from .chain import Chain, ChainRevert, b32, keccak_hex, redact, start_anvil
from .config import AGENT_ID, ASSET, BACKTEST_JSON, CARBON_BACKTEST_JSON, CARBON_PLANS_DIR, DEMO_STATE, HOURS, \
    PLANS_DIR, RUNS, ZONE, Network, base_sepolia_network, local_network

ASSET_OTHER = "DK-other-clean-declared"  # declared solar + hydro (clean minus wind)
TARGET_BPS_DEFAULT = 7500
DAY = 86400
KPI_COVERAGE, KPI_RESIDUAL_EMISSIONS = 0, 1  # SustainabilityLinkedNote.KpiKind
MODES = ("carbon", "procurement")
# ------------------------------------------------------------------ public-chain funding (fail closed)
# Each role wallet must hold GAS_MARGIN x (the gas its transactions use) x the fee cap `cast send` may charge.
# The gas comes from the newest REAL local replay run of the same mode and week: the same deterministic list of
# transactions a public run sends (the public run only adds the admin's funding transfers, counted below).
GAS_MARGIN = 3
TRANSFER_GAS = 21_000  # one plain ETH transfer from the admin to a role wallet
# A role with no successful transaction still needs balance for gas ESTIMATION: the ghost buyer's double-claim
# attack is refused at estimation, and an estimate with too little balance errors with a different message
# (which the attack check would treat as a failure, so this can only make a run fail, never pass).
RESERVE_GAS = {"ghost": 500_000}
FUNDED_ROLES = ("oracle", "issuer_ops", "buyer", "ghost", "datahub", "investor", "agent")


def planned_gas_by_role(mode: str, window_start_unix: int | None = None, runs: Path | None = None) -> tuple[dict, str]:
    """Gas per role from the newest successful REAL local run of `mode` (and window). Fails closed if none."""
    for path in sorted((runs or RUNS).glob("*/state.json"), reverse=True):
        try:
            st = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (st.get("network"), st.get("zk_mode"), st.get("mode", "procurement"), st.get("status")) != \
                ("local", "real", mode, "done"):
            continue
        if window_start_unix is not None and st.get("window", {}).get("window_start_unix") != window_start_unix:
            continue
        txs = [t for step in st.get("steps", []) for t in step.get("txs", [])]
        if not txs or any(not t.get("role") for t in txs):  # runs from before per-role gas was recorded
            continue
        gas = dict.fromkeys(("admin", *FUNDED_ROLES), 0)
        for t in txs:
            gas[t["role"]] = gas.get(t["role"], 0) + int(t["gas"])
        return gas, st["run_id"]
    raise SystemExit(f"no successful real local '{mode}' run" + (f" for window {window_start_unix}" if window_start_unix
                     else "") + " with per-role gas records: run `python -m hourproof demo --network local` (same "
                     "--window and --mode) first; the public-chain funding plan is derived from it")


def funding_plan(ch: Chain, gas: dict, source: str) -> dict:
    """Read-only. Integer wei throughout. Every role is topped up to its FULL target; the admin must cover all
    top-ups plus its own transactions (incl. the transfers) at the same margin and fee cap."""
    fee = ch.fee_cap_wei()
    roles = {}
    for r in FUNDED_ROLES:
        target = GAS_MARGIN * max(gas.get(r, 0), RESERVE_GAS.get(r, 0)) * fee
        bal = ch.balance_wei(r)
        roles[r] = {"address": ch.addr(r), "balance_wei": bal, "target_wei": target, "to_send_wei": max(0, target - bal)}
    transfers = sum(1 for v in roles.values() if v["to_send_wei"] > 0)
    admin_target = GAS_MARGIN * (gas["admin"] + TRANSFER_GAS * transfers) * fee
    need = sum(v["to_send_wei"] for v in roles.values()) + admin_target
    admin_bal = ch.balance_wei("admin")
    return {"source_run": source, "fee_cap_wei": fee, "fee_cap_gwei": fee / 1e9, "margin": GAS_MARGIN,
            "planned_gas": gas, "roles": roles, "admin_address": ch.addr("admin"), "admin_balance_wei": admin_bal,
            "admin_target_wei": admin_target, "admin_needs_wei": need, "shortfall_wei": max(0, need - admin_bal),
            "ready": admin_bal >= need,
            "max_spend_wei": (sum(gas.values()) + TRANSFER_GAS * transfers) * fee}


def assert_funded(plan: dict) -> None:
    """After the transfers: every role holds its full target and the admin its own target, re-read from chain."""
    short = [r for r, v in plan["roles"].items() if v["to_send_wei"] > 0]
    if short or plan["admin_balance_wei"] < plan["admin_target_wei"]:
        raise RuntimeError(f"post-funding check failed: under target: {short or ['admin']}; nothing deployed")


def representative_week(hours: pd.DataFrame) -> pd.Timestamp:
    """The demo week rule: the agent's weekly coverage closest to its median over the test period."""
    weeks = []
    for ws in pd.date_range(hours.index.min().normalize(), hours.index.max(), freq="W-MON"):
        w = hours.loc[ws: ws + pd.Timedelta(hours=HOURS - 1)]
        if len(w) == HOURS:
            weeks.append((ws, agent.coverage(w["agent_load_mwh"], w["base_cert_mwh"] + w["agent_buy_mwh"])))
    med = float(np.median([c for _, c in weeks]))
    return min(weeks, key=lambda x: abs(x[1] - med))[0]

# The residual-emissions KPI target, fixed in code BEFORE any run (never chosen after seeing a result):
RESIDUAL_TARGET_WEEKS = 4
RESIDUAL_TARGET_RULE = (
    "mean weekly residual (unmatched) emissions of the 4 complete weeks that ended at least one week before the "
    "window (so the value is known when the note is issued, 2 days before the window), with the same load, "
    "certificate and intensity rules as the window; rounded down to whole kg")


class AttackDidNotFail(RuntimeError):
    pass


class Run:
    def __init__(self, network: str = "local", zk_mode: str = "real", target_bps: int = TARGET_BPS_DEFAULT,
                 window: str | None = None, port: int = 8545, allow_synthetic: bool = False, mode: str = "carbon"):
        if zk_mode not in ("real", "mock"):
            raise ValueError("zk_mode must be 'real' or 'mock'")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode
        self.network_name, self.zk_mode, self.target_bps, self.window_arg, self.port = network, zk_mode, target_bps, window, port
        self.allow_synthetic = allow_synthetic
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.dir = RUNS / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state: dict = {"run_id": self.run_id, "network": network, "zk_mode": zk_mode, "mode": mode,
                            "status": "running",
                            "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "steps": [], "attacks": [], "contracts": {}, "summary": {}}
        self.anvil = None
        self.chain: Chain | None = None
        self.c: dict[str, str] = {}

    # ------------------------------------------------------------------ bookkeeping
    def _redact(self, text: str) -> str:
        """Scrub every signing key from text before it is saved, printed or served by the dashboard."""
        return redact(text, self.chain.secrets()) if self.chain else text

    def save(self) -> None:
        text = self._redact(json.dumps(self.state, indent=2, default=str))  # one choke point for every field
        DEMO_STATE.write_text(text)
        (self.dir / "state.json").write_text(text)

    def step(self, sid: str, title: str):
        run = self

        class _Step:
            def __enter__(self_inner):
                self_inner.rec = {"id": sid, "title": title, "status": "running", "detail": "", "txs": [], "metrics": {}}
                self_inner.t0 = time.time()
                self_inner.n0 = len(run.chain.txs) if run.chain else 0
                run.state["steps"].append(self_inner.rec)
                run.save()
                print(f"\n▶ {title}")
                return self_inner.rec

            def __exit__(self_inner, et, ev, tb):
                rec = self_inner.rec
                if run.chain:
                    rec["txs"] = [asdict(t) for t in run.chain.txs[self_inner.n0:]]
                    rec["metrics"].setdefault("gas_total", sum(t.gas for t in run.chain.txs[self_inner.n0:]))
                rec["seconds"] = round(time.time() - self_inner.t0, 1)
                rec["status"] = "failed" if et else "done"
                if et:
                    rec["detail"] = run._redact(f"{et.__name__}: {ev}")
                    print(f"  ✗ {rec['detail'][:400]}")
                else:
                    print(f"  ✓ {rec.get('detail', '')[:200]}")
                run.save()
                return False

        return _Step()

    def attack(self, aid: str, title: str, expected_error: str, fn) -> None:
        rec = {"id": aid, "title": title, "expected": expected_error, "status": "running"}
        self.state["attacks"].append(rec)
        self.save()
        print(f"\n⚔ {title}")
        try:
            fn()
        except ChainRevert as e:
            rec.update(observed=e.error, status="blocked" if e.error == expected_error else "wrong-error")
        except zk.ProverRefused as e:
            rec.update(observed="ProverRefused", status="blocked" if expected_error == "ProverRefused" else "wrong-error",
                       note=str(e))
        else:
            rec.update(observed="succeeded", status="NOT BLOCKED")
        print(f"  {'✓ blocked by ' + rec['observed'] if rec['status'] == 'blocked' else '✗ ' + rec['status'] + ' (' + rec['observed'] + ')'}")
        self.save()
        if rec["status"] != "blocked":
            raise AttackDidNotFail(f"{aid}: expected {expected_error}, observed {rec['observed']}")

    # ------------------------------------------------------------------ data for the window
    def prepare_data(self, persist: bool = True) -> dict:
        df, meta = dataset.load(require_real=not self.allow_synthetic)
        self.state["synthetic_data"] = bool(meta.get("synthetic"))
        if not BACKTEST_JSON.exists():
            print("  (no backtest yet: running the agent backtest first)")
            agent.run_backtest(df) if not self.allow_synthetic else agent.backtest(df)
        bt = json.loads(BACKTEST_JSON.read_text())
        hours = pd.read_csv(BACKTEST_JSON.with_suffix(".hours.csv"), parse_dates=["hour_utc"]).set_index("hour_utc")
        k = bt["portfolio_share_k"]
        if self.window_arg:
            start = pd.Timestamp(self.window_arg)
        else:  # representative week: agent weekly coverage closest to its median over the test period
            start = representative_week(hours)
        w = hours.loc[start: start + pd.Timedelta(hours=HOURS - 1)]
        if len(w) != HOURS:
            raise SystemExit(f"window {start} is not a full week inside the agent's test period")
        cw = week_certs(w, df.loc[w.index])
        base, wind_prod, other_prod, top_wind, top_other, cert_mwh = (
            cw[x] for x in ("base", "wind_prod", "other_prod", "top_wind", "top_other", "cert"))
        load_kwh = np.rint(w["agent_load_mwh"].to_numpy() * 1000).astype(int)
        naive_load_kwh = np.rint(w["load_mwh"].to_numpy() * 1000).astype(int)
        naive_cert_kwh = np.floor(w["base_cert_mwh"].to_numpy()).astype(int) * 1000
        info = {
            "window_start_utc": str(start), "window_start_unix": int(start.tz_localize("UTC").timestamp()),
            "hours": [str(t) for t in w.index], "buyer_branch": meta.get("buyer_branch"), "portfolio_share_k": k,
            "load_kwh": load_kwh.tolist(), "naive_load_kwh": naive_load_kwh.tolist(),
            "base_mwh": base.tolist(), "topup_wind_mwh": top_wind.tolist(), "topup_other_mwh": top_other.tolist(),
            "cert_mwh": cert_mwh.tolist(), "wind_production_mwh": wind_prod.tolist(), "other_production_mwh": other_prod.tolist(),
            "coverage_agent_bps": zk.max_bps(load_kwh.tolist(), (cert_mwh * 1000).tolist()),
            "coverage_naive_bps": zk.max_bps(naive_load_kwh.tolist(), naive_cert_kwh.tolist()),
            "agent_backtest": {kk: bt[kk] for kk in ("coverage", "params", "test_period", "gain_vs_same_mwh_pp")},
            "dataset": {kk: meta.get(kk) for kk in ("source", "year", "hours", "declaration_version", "note_on_sources")},
        }
        if self.mode == "carbon":
            info |= self._carbon_week(info, hours, df, start)
        private = ("load_kwh", "procurement_load_kwh")
        self.state["window"] = {kk: v for kk, v in info.items() if kk not in private}  # private load stays out of UI state
        self.state["window"]["load_profile_private"] = True
        if persist:
            self.save()
        return info

    def _carbon_week(self, info: dict, hours: pd.DataFrame, df: pd.DataFrame, start: pd.Timestamp) -> dict:
        """The carbon-aware week: the buyer's load after executing the committed carbon plans, the public hourly
        intensity (integer g/kWh, as posted on-chain), the agent's CO2 forecast, and the KPI target by rule."""
        E, cmeta = dataset.load_carbon(require_real=not self.allow_synthetic)
        if not CARBON_BACKTEST_JSON.exists():
            print("  (no carbon backtest yet: running it first)")
            carbon.backtest(E, cfg=carbon.FROZEN if self.allow_synthetic else None)
        ch = carbon_hours()
        idx = pd.DatetimeIndex(pd.to_datetime(info["hours"]))
        cw = ch.reindex(idx)
        inten = E["co2_g_per_kwh"].reindex(idx)
        if cw[["carbon_model_load", "co2_forecast"]].isna().any().any() or inten.isna().any():
            raise SystemExit(f"window {start} is not a full week inside the carbon backtest's test period")
        g = carbon.intensity_g(inten)
        load_kwh = np.rint(cw["carbon_model_load"].to_numpy() * 1000).astype(int).tolist()
        cert_kwh = [m * 1000 for m in info["cert_mwh"]]
        days = [start + pd.Timedelta(days=i) for i in range(7)]
        shift = [x for day in days
                 for x in json.loads((CARBON_PLANS_DIR / f"{day:%Y-%m-%d}.json").read_bytes())["planned_shift_mwh"]]
        target, basis = residual_target(hours, df, ch, E, start)
        persist = E["co2_g_per_kwh"].shift(168).reindex(idx)
        return {
            "mode": "carbon", "load_kwh": load_kwh, "procurement_load_kwh": info["load_kwh"],
            "intensity_g_per_kwh": g,
            "co2_forecast_g_per_kwh": [round(float(x), 2) for x in cw["co2_forecast"]],
            "planned_shift_mwh": shift,
            "coverage_agent_bps": zk.max_bps(load_kwh, cert_kwh),
            "coverage_procurement_load_bps": info["coverage_agent_bps"],
            "residual_kg": {"carbon_agent": zk.min_cap_kg(load_kwh, cert_kwh, g),
                            "procurement_agent": zk.min_cap_kg(info["load_kwh"], cert_kwh, g),
                            "no_shift": zk.min_cap_kg(info["naive_load_kwh"], cert_kwh, g)},
            "residual_target_kg": target, "residual_target_rule": RESIDUAL_TARGET_RULE,
            "residual_target_basis": basis,
            "co2_mae_week_g_per_kwh": {"model": float((cw["co2_forecast"] - inten).abs().mean()),
                                       "lag168": float((persist - inten).abs().mean())},
            "carbon_dataset": {kk: cmeta.get(kk) for kk in ("source", "buyer_branch")},
        }

    def day_plan(self, day: pd.Timestamp) -> bytes:
        """The bytes the agent commits for a day. Carbon mode: the procurement plan (certificate purchases) and
        the carbon plan (CO2 forecast + planned shift) in one canonical document, so one hash binds both."""
        proc = (PLANS_DIR / f"{day:%Y-%m-%d}.json").read_bytes()
        if self.mode != "carbon":
            return proc
        co2 = (CARBON_PLANS_DIR / f"{day:%Y-%m-%d}.json").read_bytes()
        return json.dumps({"agent": AGENT_ID, "mode": "carbon-aware", "day_utc": f"{day:%Y-%m-%d}",
                           "procurement": json.loads(proc), "carbon": json.loads(co2),
                           "executed_load_shift": "carbon.planned_shift_mwh (the procurement plan's shift_mwh is not "
                                                  "executed in carbon-aware mode; its certificate purchases are)"},
                          separators=(",", ":"), sort_keys=True).encode()

    # ------------------------------------------------------------------ the run
    def execute(self) -> dict:
        try:
            self._execute()
            self.state["status"] = "done"
        except (Exception, SystemExit) as e:  # noqa: BLE001  (SystemExit: e.g. PRIVATE_KEY missing; never leave "running")
            self.state["status"] = "failed"
            self.state["error"] = self._redact(f"{type(e).__name__}: {e}")
            self.state["traceback"] = self._redact(traceback.format_exc()[-4000:])
            print(f"\nRUN FAILED: {self.state['error']}")
        except KeyboardInterrupt:  # Ctrl-C: record it truthfully, save (finally), then stop
            self.state["status"] = "aborted"
            self.state["error"] = "interrupted by the user (Ctrl-C); transactions already mined stay on-chain"
            print(f"\nRUN ABORTED: {self.state['error']}")
            raise
        finally:
            self.state["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if self.chain:
                self.state["summary"]["transactions"] = len(self.chain.txs)
                self.state["summary"]["gas_total"] = sum(t.gas for t in self.chain.txs)
            self.save()
            if self.anvil:
                self.anvil.terminate()
        return self.state

    def _execute(self) -> None:
        # ---------------------------------------------------------- 1 preflight
        info = self.prepare_data()
        ws = info["window_start_unix"]
        net: Network
        if self.network_name == "local":
            self.anvil = start_anvil(self.port, timestamp=ws - 2 * DAY)  # replay chain clock: two days before the week
            net = local_network(self.port)
        elif self.network_name == "base-sepolia":
            net = base_sepolia_network()
        else:
            raise SystemExit(f"unknown network {self.network_name}")
        self.chain = ch = Chain(net)
        with self.step("preflight", "Preflight: chain, keys, ZK artifacts") as s:
            ensure_contracts_built()
            cid = ch.chain_id()
            if cid != net.chain_id:
                raise RuntimeError(f"RPC chain id {cid} != expected {net.chain_id}")
            if self.zk_mode == "real" and not zk.verifier_ready():
                raise RuntimeError("ZK verifier not generated yet: run `python -m hourproof zk build`")
            if self.zk_mode == "real" and self.mode == "carbon" and not zk.emissions_verifier_ready():
                raise RuntimeError("emissions verifier not generated yet: run `python -m hourproof zk build`")
            if net.name != "local":
                gas, src = planned_gas_by_role(self.mode, ws)  # fails closed without a measured local run
                plan = funding_plan(ch, gas, src)  # checked BEFORE any transfer: no half-funded run
                s["metrics"]["funding"] = {k: v for k, v in plan.items() if k != "roles"}
                if not plan["ready"]:
                    raise RuntimeError(f"admin {plan['admin_address']} holds {plan['admin_balance_wei'] / 1e18:.6f} ETH but "
                                       f"needs >= {plan['admin_needs_wei'] / 1e18:.6f} at a {plan['fee_cap_gwei']:.4f} gwei "
                                       "fee cap (faucet; see `python -m hourproof wallet check`); nothing was sent")
                for r, v in plan["roles"].items():
                    if v["to_send_wei"] > 0:
                        ch.fund(r, v["to_send_wei"])
                assert_funded(funding_plan(ch, gas, src))  # re-read every balance (and the fee cap) from chain
            s["detail"] = f"chain {cid}; roles: " + ", ".join(f"{r}={ch.addr(r)[:10]}…" for r in net.keys)
            s["metrics"].update(chain_id=cid, block_time=ch.block_timestamp(), zk_mode=self.zk_mode)

        # ---------------------------------------------------------- 2 deploy
        with self.step("deploy", "Deploy contracts and wire roles") as s:
            c = self.c
            c["ProductionOracle"] = ch.deploy("ProductionOracle")
            c["SliceLedger"] = ch.deploy("SliceLedger")
            c["MLDSA_F1600Helper"] = ch.deploy_runtime(pq.helper_runtime(), label="deploy ML-DSA Keccak helper")
            c["MLDSA44Verifier"] = ch.deploy("MLDSA44Verifier", [c["MLDSA_F1600Helper"]])
            ka, kb = pq.issuer_key("A"), pq.issuer_key("B")
            c["IssuerA_PQKey"] = ch.deploy_runtime(ka["blob"], label="deploy issuer A ML-DSA public key")
            c["IssuerB_PQKey"] = ch.deploy_runtime(kb["blob"], label="deploy issuer B ML-DSA public key")
            c["RegistryA"] = ch.deploy("CertRegistry", ["Registry A", c["SliceLedger"], c["ProductionOracle"], c["MLDSA44Verifier"]])
            c["RegistryB"] = ch.deploy("CertRegistry", ["Registry B", c["SliceLedger"], c["ProductionOracle"], c["MLDSA44Verifier"]])
            if self.zk_mode == "real":
                name = json.loads(zk.ZK_META.read_text())["verifier_contract"]
                c["HonkVerifier"] = ch.deploy(name, label="deploy UltraHonk verifier")
            else:
                c["MockZKVerifier"] = ch.deploy("MockZKVerifier", label="deploy MOCK ZK verifier (test mode)")
            zkv = c.get("HonkVerifier") or c["MockZKVerifier"]
            c["ClaimManager"] = ch.deploy("ClaimManager", [zkv])
            if self.mode == "carbon":
                c["IntensityOracle"] = ch.deploy("IntensityOracle")
                if self.zk_mode == "real":
                    ename = json.loads(zk.ZK_META.read_text())["emissions_verifier_contract"]
                    c["EmissionsHonkVerifier"] = ch.deploy(ename, label="deploy UltraHonk emissions verifier")
                else:
                    c["MockEmissionsZKVerifier"] = ch.deploy("MockZKVerifier",
                                                             label="deploy MOCK emissions ZK verifier (test mode)")
            c["AgentCommitLog"] = ch.deploy("AgentCommitLog")
            c["TestUSD"] = ch.deploy("TestUSD")
            deadline = ws + (HOURS * 3600) + 2 * DAY if net.name == "local" else ch.block_timestamp() + 600
            kind, target = ((KPI_RESIDUAL_EMISSIONS, info["residual_target_kg"]) if self.mode == "carbon"
                            else (KPI_COVERAGE, self.target_bps))
            c["SustainabilityLinkedNote"] = ch.deploy("SustainabilityLinkedNote", [
                c["ClaimManager"], c["TestUSD"], ch.addr("buyer"), ws, kind, target, 500, 100, deadline])
            ch.send(c["ProductionOracle"], "setPoster(address,bool)", [ch.addr("oracle"), "true"])
            for r in ("RegistryA", "RegistryB"):
                ch.send(c["SliceLedger"], "setRegistry(address,bool)", [c[r], "true"])
                ch.send(c["ClaimManager"], "setRegistry(address,bool)", [c[r], "true"])
                ch.send(c[r], "setClaimSink(address)", [c["ClaimManager"]])
            ch.send(c["RegistryA"], "registerIssuer(bytes32,address)", [b32("issuer-A"), c["IssuerA_PQKey"]])
            ch.send(c["RegistryB"], "registerIssuer(bytes32,address)", [b32("issuer-B"), c["IssuerB_PQKey"]])
            ch.send(c["ClaimManager"], "setDataHub(address,bool)", [ch.addr("datahub"), "true"])
            if self.mode == "carbon":
                ch.send(c["IntensityOracle"], "setOracle(address,bool)", [ch.addr("oracle"), "true"])
                ch.send(c["ClaimManager"], "setEmissionsVerifier(address)",
                        [c.get("EmissionsHonkVerifier") or c["MockEmissionsZKVerifier"]])
                ch.send(c["ClaimManager"], "setIntensityOracle(address,bytes32)", [c["IntensityOracle"], b32(ZONE)])
            self.state["contracts"] = {k: {"address": v, "url": net.addr_url(v)} for k, v in c.items()}
            self.state["note_terms"] = {"kpi": "RESIDUAL_EMISSIONS" if self.mode == "carbon" else "COVERAGE",
                                        "target_bps": self.target_bps, "base_coupon_bps": 500, "step_up_bps": 100,
                                        "deadline_unix": deadline}
            if self.mode == "carbon":
                self.state["note_terms"] |= {"target_residual_kg": info["residual_target_kg"],
                                             "target_rule": info["residual_target_rule"],
                                             "target_basis": info["residual_target_basis"]}
            s["detail"] = f"{len(c)} contracts"

        # ---------------------------------------------------------- 3 agent commits plans before each day
        title = ("AI agent commits its 7 day plans (certificate purchases, CO2 forecast, planned load shift) "
                 "on-chain before each day starts" if self.mode == "carbon"
                 else "AI agent commits its 7 day plans on-chain before each day starts")
        with self.step("agent_commit", title) as s:
            commits = []
            (self.dir / "plans").mkdir(exist_ok=True)
            for i in range(7):
                day = pd.Timestamp(info["window_start_utc"]) + pd.Timedelta(days=i)
                plan = self.day_plan(day)
                (self.dir / "plans" / f"{day:%Y-%m-%d}.json").write_bytes(plan)
                h = keccak_hex(plan)
                tx = ch.send(c["AgentCommitLog"], "commit(bytes32,uint64,bytes32)", [b32(AGENT_ID), ws + i * DAY, h],
                             role="agent", label=f"commit plan {day:%Y-%m-%d}")
                early = ch.call(c["AgentCommitLog"], "entries(address,bytes32,uint64)(bytes32,uint64,bool,bool)",
                                [ch.addr("agent"), b32(AGENT_ID), ws + i * DAY]).splitlines()[2] == "true"
                commits.append({"day": f"{day:%Y-%m-%d}", "plan_hash": h, "early": early, "tx": tx.hash})
            s["metrics"]["commits"] = commits
            s["detail"] = f"{sum(x['early'] for x in commits)}/7 committed before their day started (chain clock)"
            if net.name != "local":
                s["detail"] += " — on a public chain a past week is necessarily committed late; see `live` mode"

        # ---------------------------------------------------------- 4 oracle posts metered production
        with self.step("oracle", "Oracle posts metered hourly production (Energinet, whole MWh)") as s:
            hrs = [ws + 3600 * i for i in range(HOURS)]
            for asset, prod in ((ASSET, info["wind_production_mwh"]), (ASSET_OTHER, info["other_production_mwh"])):
                for a in range(0, HOURS, 84):
                    ch.send(c["ProductionOracle"], "post(bytes32,bytes32,uint64[],uint32[])",
                            [b32(ZONE), b32(asset), _arr(hrs[a:a + 84]), _arr(prod[a:a + 84])], role="oracle",
                            label=f"post {asset} hours {a}-{a + 83}")
            s["detail"] = f"{sum(info['wind_production_mwh']):,} MWh wind + {sum(info['other_production_mwh']):,} MWh other clean"

        if self.mode == "carbon":
            with self.step("intensity", "Oracle posts the week's hourly grid CO2 intensity (Energinet, whole g/kWh)") as s:
                g = info["intensity_g_per_kwh"]
                for a in range(0, HOURS, 84):
                    ch.send(c["IntensityOracle"], "post(bytes32,uint64[],uint32[])",
                            [b32(ZONE), _arr(hrs[a:a + 84]), _arr(g[a:a + 84])], role="oracle",
                            label=f"post intensity hours {a}-{a + 83}")
                s["detail"] = (f"168 hours, {min(g)}-{max(g)} g/kWh (location-based average, 125 % method); "
                               "write-once")
                s["metrics"].update(intensity_g_per_kwh=g, co2_forecast_g_per_kwh=info["co2_forecast_g_per_kwh"])

        # ---------------------------------------------------------- 5 PQ-signed issuance (daily batches)
        with self.step("issue", "Issuer A issues hourly certificates, one ML-DSA-44-signed batch per day") as s:
            ka = pq.issuer_key("A")
            buyer = ch.addr("buyer")
            cert_ids: list[int] = []
            for dday in range(7):
                batch = []
                for i in range(dday * 24, dday * 24 + 24):
                    h = ws + 3600 * i
                    base, tw, to = info["base_mwh"][i], info["topup_wind_mwh"][i], info["topup_other_mwh"][i]
                    if base + tw > 0:
                        batch.append((b32(ZONE), b32(ASSET), h, 0, base + tw, buyer))
                    if to > 0:
                        batch.append((b32(ZONE), b32(ASSET_OTHER), h, 0, to, buyer))
                tup = _tuples(batch)
                msg = ch.call(c["RegistryA"], "batchMessage(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[])(bytes)",
                              [b32("issuer-A"), tup])
                sig = pq.sign(ka["sk"], bytes.fromhex(msg.removeprefix("0x")))
                first = int(ch.call(c["RegistryA"], "nextId()(uint256)").split()[0])
                ch.send(c["RegistryA"], "issueBatch(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[],bytes)",
                        [b32("issuer-A"), tup, sig], role="issuer_ops", label=f"issue day {dday + 1} ({len(batch)} certs)")
                cert_ids += list(range(first, first + len(batch)))
            self.state["cert_ids"] = cert_ids
            s["detail"] = f"{len(cert_ids)} certificates, {sum(info['cert_mwh']):,} MWh, 7 post-quantum signatures checked on-chain"

        # ---------------------------------------------------------- 6 buyer cancels into its claim
        with self.step("claim", "Buyer opens a claim for the week and cancels its certificates into it") as s:
            ch.send(c["ClaimManager"], "openClaim(uint64)", [ws], role="buyer")
            claim_id = int(ch.call(c["ClaimManager"], "nextClaimId()(uint256)").split()[0]) - 1
            for a in range(0, len(cert_ids), 40):
                ch.send(c["RegistryA"], "cancelBatch(uint256[],uint256,bytes32)",
                        [_arr(cert_ids[a:a + 40]), claim_id, b32(f"claim-{claim_id}")], role="buyer",
                        label=f"cancel certificates {a + 1}-{min(a + 40, len(cert_ids))}")
            onchain = [int(x) for x in _parse_list(ch.call(c["ClaimManager"], "certVector(uint256)(uint32[])", [claim_id]))]
            if onchain != info["cert_mwh"]:
                raise RuntimeError("on-chain certificate vector differs from the issued certificates")
            self.state["claim_id"] = claim_id
            s["detail"] = f"claim #{claim_id}: {sum(onchain):,} MWh cancelled across {sum(1 for x in onchain if x)} hours"

        # ---------------------------------------------------------- 7 attacks on issuance / double counting
        peak = int(np.argmax(info["base_mwh"]))
        ph = ws + 3600 * peak
        kb = pq.issuer_key("B")
        with self.step("attacks_supply", "Attacks: ghost double claim, over-issuance, forged signature") as s:
            def ghost():
                batch = _tuples([(b32(ZONE), b32(ASSET), ph, 0, 50, ch.addr("ghost"))])
                msg = ch.call(c["RegistryB"], "batchMessage(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[])(bytes)",
                              [b32("issuer-B"), batch])
                first = int(ch.call(c["RegistryB"], "nextId()(uint256)").split()[0])
                ch.send(c["RegistryB"], "issueBatch(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[],bytes)",
                        [b32("issuer-B"), batch, pq.sign(kb["sk"], bytes.fromhex(msg[2:]))], role="issuer_ops",
                        label="registry B issues the SAME MWh (legitimately signed)")
                ch.send(c["RegistryB"], "cancelBatch(uint256[],uint256,bytes32)", [_arr([first]), 0, b32("ghost-claim")],
                        role="ghost", label="ghost buyer cancels the same MWh")
            self.attack("double_claim", f"Registry B re-sells 50 MWh of hour {peak} that the buyer already claimed",
                        "SliceAlreadyClaimed", ghost)

            def over():
                prod = info["wind_production_mwh"][peak]
                batch = _tuples([(b32(ZONE), b32(ASSET), ph, prod, 1, ch.addr("ghost"))])
                msg = ch.call(c["RegistryB"], "batchMessage(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[])(bytes)",
                              [b32("issuer-B"), batch])
                ch.send(c["RegistryB"], "issueBatch(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[],bytes)",
                        [b32("issuer-B"), batch, pq.sign(kb["sk"], bytes.fromhex(msg[2:]))], role="issuer_ops",
                        label="issue 1 MWh more than was produced")
            self.attack("over_issuance", "Issuer certifies 1 MWh more than the metered production of that hour",
                        "ExceedsProduction", over)

            def forged():
                batch = _tuples([(b32(ZONE), b32(ASSET), ph + 3600, 0, 1, ch.addr("ghost"))])
                msg = ch.call(c["RegistryA"], "batchMessage(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[])(bytes)",
                              [b32("issuer-A"), batch])
                sig = bytearray(bytes.fromhex(pq.sign(kb["sk"], bytes.fromhex(msg[2:]))[2:]))  # signed with the WRONG key
                ch.send(c["RegistryA"], "issueBatch(bytes32,(bytes32,bytes32,uint64,uint32,uint32,address)[],bytes)",
                        [b32("issuer-A"), batch, "0x" + sig.hex()], role="issuer_ops", label="impersonate issuer A")
            self.attack("forged_signature", "Someone impersonates issuer A with a different ML-DSA key",
                        "BadIssuerSignature", forged)
            s["detail"] = "all three blocked on-chain"

        # ---------------------------------------------------------- 8 data hub attests the load commitment
        salt = secrets.randbelow(2**200)
        load_kwh = info["load_kwh"]
        with self.step("attest", "Metering data hub attests a commitment to the buyer's hourly load") as s:
            commitment = zk.commit_load(load_kwh, salt)
            self.state["commitment"] = commitment
            ch.send(c["ClaimManager"], "attestLoad(address,uint64,bytes32)", [ch.addr("buyer"), ws, commitment],
                    role="datahub")
            s["detail"] = f"commitment {commitment[:18]}…; the load itself never goes on-chain"
            s["metrics"]["commitment"] = commitment

        # ---------------------------------------------------------- 9 zero-knowledge coverage proof
        cert_kwh = [m * 1000 for m in info["cert_mwh"]]
        truth = info["coverage_agent_bps"]
        claim_bps = min(self.target_bps, truth)
        with self.step("prove", f"Buyer proves hourly coverage ≥ {claim_bps / 100:.2f}% in zero knowledge") as s:
            if self.zk_mode == "real":
                proof = zk.prove(load_kwh, salt, claim_bps, cert_kwh, self.dir / "proof")
                expected = _parse_list(ch.call(c["ClaimManager"], "publicInputs(uint256,uint32)(bytes32[])",
                                               [self.state["claim_id"], claim_bps]))
                if [x.lower() for x in expected] != [x.lower() for x in proof["public_inputs"]]:
                    raise RuntimeError("prover's public inputs differ from what ClaimManager will rebuild")
                s["metrics"].update(prove_seconds=proof["prove_seconds"], proof_bytes=proof["proof_bytes"],
                                    native_verify=proof["native_verify"])
                proof_hex = proof["proof"]
            else:
                proof_hex = "0x" + b"MOCK-PROOF-NOT-ZERO-KNOWLEDGE".hex()
                pub = _parse_list(ch.call(c["ClaimManager"], "publicInputs(uint256,uint32)(bytes32[])",
                                          [self.state["claim_id"], claim_bps]))
                ch.send(c["MockZKVerifier"], "expect(bytes,bytes32[])", [proof_hex, "[" + ",".join(pub) + "]"],
                        label="MOCK: preload expected proof")
            tx = ch.send(c["ClaimManager"], "submitProof(uint256,uint32,bytes)", [self.state["claim_id"], claim_bps, proof_hex],
                         role="buyer", label="submit coverage proof")
            proven = int(ch.call(c["ClaimManager"], "bestProvenBps(address,uint64)(uint32)", [ch.addr("buyer"), ws]).split()[0])
            s["metrics"].update(threshold_bps=claim_bps, proven_bps=proven, verify_gas=tx.gas,
                                true_coverage_private_bps=truth)
            s["detail"] = f"on-chain: coverage ≥ {proven / 100:.2f}% (true value stays private); {tx.gas:,} gas"

        with self.step("attacks_proof", "Attacks: over-claim the coverage, replay the proof for more") as s:
            def overclaim():
                zk.prove(load_kwh, salt, truth + 1, cert_kwh, self.dir / "proof_overclaim")
            if self.zk_mode == "real":
                self.attack("overclaim", f"Buyer tries to prove {(truth + 1) / 100:.2f}% (one basis point above the truth)",
                            "ProverRefused", overclaim)
            def replay():
                ch.send(c["ClaimManager"], "submitProof(uint256,uint32,bytes)",
                        [self.state["claim_id"], min(claim_bps + 500, 10000), proof_hex], role="buyer",
                        label="resubmit the same proof for a higher threshold")
            self.attack("replay_higher", "Buyer resubmits the valid proof claiming 5 points more", "ProofRejected", replay)
            s["detail"] = "blocked"

        if self.mode == "carbon":
            self._emissions(info, load_kwh, salt, cert_kwh, claim_bps)

        # ---------------------------------------------------------- 10 sustainability-linked note
        with self.step("note", "Sustainability-linked note settles on the proven KPI") as s:
            n, usd = c["SustainabilityLinkedNote"], c["TestUSD"]
            ch.send(usd, "mint(address,uint256)", [ch.addr("investor"), str(10**21)], label="mint test USD to investor")
            ch.send(usd, "mint(address,uint256)", [ch.addr("buyer"), str(10**21)], label="mint test USD to issuer")
            ch.send(usd, "approve(address,uint256)", [n, str(2**256 - 1)], role="investor")
            ch.send(usd, "approve(address,uint256)", [n, str(2**256 - 1)], role="buyer")
            ch.send(n, "subscribe(uint256)", [str(10**21)], role="investor", label="investor buys 1,000 notes")
            if self.mode == "carbon":
                proven_kg = int(ch.call(c["ClaimManager"], "bestResidualKgOf(address,uint64)(uint64)",
                                        [ch.addr("buyer"), ws]).split()[0])
                met_by_proof = proven_kg <= info["residual_target_kg"]
            else:
                proven = int(ch.call(c["ClaimManager"], "bestProvenBps(address,uint64)(uint32)", [ch.addr("buyer"), ws]).split()[0])
                met_by_proof = proven >= self.target_bps
            if not met_by_proof:
                if net.name == "local":
                    ch.rpc("evm_increaseTime", 30 * DAY)
                    ch.rpc("evm_mine")
                else:
                    dl = self.state["note_terms"]["deadline_unix"]
                    while ch.block_timestamp() < dl:
                        time.sleep(10)
            ch.send(n, "settle()", [], role="investor", label="settle the note")
            ch.send(n, "fundCoupon()", [], role="buyer", label="issuer funds the coupon")
            ch.send(n, "claimCoupon()", [], role="investor", label="investor claims coupon")
            met = ch.call(n, "kpiMet()(bool)") == "true"
            cbps = int(ch.call(n, "couponBps()(uint32)").split()[0])
            paid = int(ch.call(usd, "balanceOf(address)(uint256)", [ch.addr("investor")]).split()[0])
            s["metrics"].update(kpi_met=met, coupon_bps=cbps, coupon_paid_tusd=paid / 1e18, target_bps=self.target_bps)
            kpi = "KPI"
            if self.mode == "carbon":
                s["metrics"].update(kpi="RESIDUAL_EMISSIONS", target_residual_kg=info["residual_target_kg"],
                                    proven_residual_kg=proven_kg)
                kpi = (f"KPI residual <= {info['residual_target_kg'] / 1000:,.1f} t (proven <= "
                       f"{proven_kg / 1000:,.1f} t)")
            s["detail"] = (f"{kpi} {'met' if met else 'missed'} → coupon {cbps / 100:.2f}% "
                           f"({paid / 1e18:,.0f} tUSD on 1,000 notes)")

        # ---------------------------------------------------------- 11 reveal plans
        with self.step("agent_reveal", "Agent reveals its plans; the chain checks them against the commitments") as s:
            for i in range(7):
                day = pd.Timestamp(info["window_start_utc"]) + pd.Timedelta(days=i)
                plan = self.day_plan(day)
                ch.send(c["AgentCommitLog"], "reveal(bytes32,uint64,bytes)", [b32(AGENT_ID), ws + i * DAY, "0x" + plan.hex()],
                        role="agent", label=f"reveal plan {day:%Y-%m-%d}")
            s["detail"] = "7/7 plans revealed and matched"

        self.state["summary"].update({
            "coverage_naive_bps": info["coverage_naive_bps"], "coverage_agent_private_bps": truth,
            "proven_bps": int(ch.call(c["ClaimManager"], "bestProvenBps(address,uint64)(uint32)", [ch.addr("buyer"), ws]).split()[0]),
            "attacks_blocked": sum(a["status"] == "blocked" for a in self.state["attacks"]),
            "attacks_total": len(self.state["attacks"]),
        })
        if self.mode == "carbon":
            self.state["summary"].update({
                "mode": "carbon",
                "proven_residual_kg": int(ch.call(c["ClaimManager"], "bestResidualKgOf(address,uint64)(uint64)",
                                                  [ch.addr("buyer"), ws]).split()[0]),
                "residual_private_kg": info["residual_kg"], "residual_target_kg": info["residual_target_kg"],
                "coverage_procurement_load_bps": info["coverage_procurement_load_bps"],
                "co2_mae_week_g_per_kwh": info["co2_mae_week_g_per_kwh"],
            })

        with self.step("verify", "Independent check: receipts, contract code, wiring, and both proofs re-verified "
                                 "on-chain from the submitted transactions") as s:
            from .verify import verify_run
            r = verify_run(ch, self.state)
            s["metrics"]["checks"] = r["checks"]
            failed = [x for x in r["checks"] if not x["ok"]]
            if failed:
                raise RuntimeError(f"independent verification failed: {failed[:3]}")
            s["detail"] = f"{len(r['checks'])} checks passed against {net.name}; {r['transactions']} receipts confirmed"
        self.state["summary"]["verified_checks"] = len(r["checks"])

    # ------------------------------------------------------------------ carbon mode: the emissions proof
    def _emissions(self, info: dict, load_kwh: list[int], salt: int, cert_kwh: list[int], claim_bps: int) -> None:
        ch, c, ws = self.chain, self.c, info["window_start_unix"]
        g = info["intensity_g_per_kwh"]
        claim_id = self.state["claim_id"]
        cap = zk.min_cap_kg(load_kwh, cert_kwh, g)  # the tightest cap the truth supports (rounded up to a kg)
        pub_sig = "emissionsPublicInputs(uint256,uint32,uint64)(bytes32[])"
        verifier = c.get("EmissionsHonkVerifier") or c.get("MockEmissionsZKVerifier")

        def make_proof(intensity: list[int], cap_kg: int, outdir: str) -> dict:
            """A proof for (threshold, cap) over `intensity`. Mock mode preloads the mock with the inputs the
            prover would use (exactly what a real proof would bind)."""
            if self.zk_mode == "real":
                pr = zk.prove_emissions(load_kwh, salt, claim_bps, cap_kg, cert_kwh, intensity, self.dir / outdir)
                return pr
            pub = ([f"0x{claim_bps:064x}", f"0x{cap_kg:064x}"] + [f"0x{x:064x}" for x in cert_kwh]
                   + [f"0x{x:064x}" for x in intensity] + [self.state["commitment"]])
            proof_hex = "0x" + f"MOCK-EMISSIONS-PROOF-{outdir}".encode().hex()
            ch.send(verifier, "expect(bytes,bytes32[])", [proof_hex, "[" + ",".join(pub) + "]"],
                    label="MOCK: preload expected emissions proof")
            return {"proof": proof_hex, "public_inputs": pub}

        with self.step("prove_emissions", f"Buyer proves residual emissions ≤ {cap / 1000:,.1f} t AND coverage ≥ "
                                          f"{claim_bps / 100:.2f}% in zero knowledge (same attestation)") as s:
            pr = make_proof(g, cap, "proof_emissions")
            expected = _parse_list(ch.call(c["ClaimManager"], pub_sig, [claim_id, claim_bps, cap]))
            if [x.lower() for x in expected] != [x.lower() for x in pr["public_inputs"]]:
                raise RuntimeError("prover's emissions public inputs differ from what ClaimManager will rebuild")
            if pr["public_inputs"][-1].lower() != self.state["commitment"].lower():
                raise RuntimeError("emissions proof is not bound to the data hub's attested commitment")
            tx = ch.send(c["ClaimManager"], "submitEmissionsProof(uint256,uint32,uint64,bytes)",
                         [claim_id, claim_bps, cap, pr["proof"]], role="buyer", label="submit emissions proof")
            proven = int(ch.call(c["ClaimManager"], "bestProvenResidualKg(uint256)(uint64)", [claim_id]).split()[0])
            s["metrics"].update(cap_kg=cap, proven_residual_kg=proven, threshold_bps=claim_bps, verify_gas=tx.gas,
                                residual_private_kg=info["residual_kg"], target_residual_kg=info["residual_target_kg"],
                                public_inputs=len(expected))
            if self.zk_mode == "real":
                s["metrics"].update(prove_seconds=pr["prove_seconds"], proof_bytes=pr["proof_bytes"],
                                    native_verify=pr["native_verify"])
            s["detail"] = (f"on-chain: residual ≤ {proven / 1000:,.1f} t CO2 and coverage ≥ {claim_bps / 100:.2f}%; "
                           f"hourly load stays private; {tx.gas:,} gas")
        self.state["emissions_proof"] = {"proof": pr["proof"], "cap_kg": cap}

        with self.step("attacks_emissions", "Attacks: under-state the residual, re-post a cleaner intensity, "
                                            "prove on a fake intensity vector") as s:
            if self.zk_mode == "real":
                def under():
                    zk.prove_emissions(load_kwh, salt, claim_bps, cap - 1, cert_kwh, g, self.dir / "proof_emissions_under")
                self.attack("residual_understated", f"Buyer tries to prove residual ≤ {(cap - 1) / 1000:,.3f} t "
                                                    "(1 kg below the truth)", "ProverRefused", under)

            dirty = int(np.argmax(g))

            def repost():
                ch.send(c["IntensityOracle"], "post(bytes32,uint64[],uint32[])",
                        [b32(ZONE), _arr([ws + 3600 * dirty]), _arr([max(g[dirty] - 100, 0)])], role="oracle",
                        label=f"re-post hour {dirty} intensity 100 g/kWh lower")
            self.attack("intensity_repost", f"Oracle re-posts hour {dirty} ({g[dirty]} g/kWh) 100 g/kWh cleaner",
                        "AlreadyPosted", repost)

            fake = [x * 7 // 10 for x in g]  # every hour 30 % cleaner than what the oracle posted
            fake_cap = zk.min_cap_kg(load_kwh, cert_kwh, fake)

            def fake_vector():
                pf = make_proof(fake, fake_cap, "proof_fake_intensity")  # a VALID proof of a false public input
                ch.send(c["ClaimManager"], "submitEmissionsProof(uint256,uint32,uint64,bytes)",
                        [claim_id, claim_bps, fake_cap, pf["proof"]], role="buyer",
                        label="submit a proof built on a 30 % cleaner intensity vector")
            self.attack("fake_intensity", f"Buyer proves residual ≤ {fake_cap / 1000:,.1f} t on a fake intensity vector "
                                          "30 % cleaner than the oracle's", "ProofRejected", fake_vector)
            s["detail"] = "blocked (the contract rebuilds the intensity vector from the oracle)"


def week_certs(w: pd.DataFrame, d: pd.DataFrame) -> dict[str, np.ndarray]:
    """Whole-MWh certificates for a week: the base portfolio plus the agent's top-ups, each capped by what was
    produced (wind first, then other clean production)."""
    base = np.floor(w["base_cert_mwh"].to_numpy()).astype(int)
    wind_prod = np.floor(d["wind_mwh"].to_numpy()).astype(int)
    other_prod = np.floor(np.maximum(d["clean_mwh"] - d["wind_mwh"], 0).to_numpy()).astype(int)
    topup = np.floor(w["agent_buy_mwh"].to_numpy()).astype(int)
    top_wind = np.minimum(topup, np.maximum(wind_prod - base, 0))
    top_other = np.minimum(topup - top_wind, other_prod)
    return {"base": base, "wind_prod": wind_prod, "other_prod": other_prod, "top_wind": top_wind,
            "top_other": top_other, "cert": base + top_wind + top_other}


def carbon_hours() -> pd.DataFrame:
    return pd.read_csv(CARBON_BACKTEST_JSON.with_suffix(".hours.csv"), parse_dates=["hour_utc"]).set_index("hour_utc")


def residual_target(hours: pd.DataFrame, df: pd.DataFrame, ch: pd.DataFrame, E: pd.DataFrame,
                    start: pd.Timestamp) -> tuple[int, list[dict]]:
    """RESIDUAL_TARGET_RULE: uses only weeks that ended at least one week before the window starts."""
    basis = []
    for k in range(2, RESIDUAL_TARGET_WEEKS + 2):
        idx = pd.date_range(start - pd.Timedelta(weeks=k), periods=HOURS, freq="h")
        w, cw, inten = hours.reindex(idx), ch.reindex(idx), E["co2_g_per_kwh"].reindex(idx)
        if w[["base_cert_mwh", "agent_buy_mwh"]].isna().any().any() or cw["carbon_model_load"].isna().any() \
                or inten.isna().any() or not idx.isin(df.index).all():
            continue
        cert_kwh = (week_certs(w, df.loc[idx])["cert"] * 1000).tolist()
        load_kwh = np.rint(cw["carbon_model_load"].to_numpy() * 1000).astype(int).tolist()
        basis.append({"week_utc": str(idx[0].date()),
                      "residual_kg": zk.residual_g(load_kwh, cert_kwh, carbon.intensity_g(inten)) / 1000})
    if len(basis) < RESIDUAL_TARGET_WEEKS:
        raise SystemExit(f"the residual target needs {RESIDUAL_TARGET_WEEKS} complete weeks ending a week before "
                         f"{start:%Y-%m-%d} inside the backtests (found {len(basis)}); pick a later --window")
    return int(np.floor(np.mean([b["residual_kg"] for b in basis]))), basis


def ensure_contracts_built() -> None:
    """Build contracts if needed (forge is incremental, so this is cheap when nothing changed)."""
    from .chain import run, tool
    from .config import CONTRACTS
    out = run([tool("forge"), "build"], cwd=CONTRACTS, timeout=1800)
    if out.returncode:
        raise RuntimeError(f"forge build failed:\n{(out.stdout + out.stderr)[-2000:]}")
    Chain.artifact.cache_clear()
    Chain.error_map.cache_clear()


def _parse_list(text: str) -> list[str]:
    body = text.strip().strip("[]").strip()
    return [x.strip().split(" ")[0] for x in body.split(",")] if body else []


def _arr(xs) -> str:
    return "[" + ",".join(str(int(x)) if not isinstance(x, str) else x for x in xs) + "]"


def _tuples(rows) -> str:
    return "[" + ",".join("(" + ",".join(str(v) for v in r) + ")" for r in rows) + "]"
