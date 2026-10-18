"""HourProof command line.  python -m hourproof --help"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from .config import BACKTEST_JSON, CONTRACTS, DATASET_META, ROOT


def _p(title: str) -> None:
    print(f"\n=== {title} ===")


def cmd_doctor(_a=None) -> bool:
    ok = True
    _p("toolchain")
    want = {"forge": ["--version"], "cast": ["--version"], "anvil": ["--version"], "nargo": ["--version"], "bb": ["--version"]}
    for t, args in want.items():
        path = shutil.which(t) or next((str(p) for p in (Path.home() / ".foundry/bin" / t, Path.home() / ".nargo/bin" / t,
                                                          Path.home() / ".bb" / t) if p.exists()), None)
        if not path:
            print(f"  ✗ {t:6} missing  -> ./scripts/install_tools.sh")
            ok = False
            continue
        v = subprocess.run([path, *args], capture_output=True, text=True).stdout.strip().splitlines()
        print(f"  ✓ {t:6} {v[0] if v else '?'}")
    _p("python packages")
    for m in ("pandas", "numpy", "sklearn", "requests", "starlette", "uvicorn", "dilithium_py"):
        try:
            __import__(m)
            print(f"  ✓ {m}")
        except ImportError:
            print(f"  ✗ {m} missing -> pip install -r requirements.txt")
            ok = False
    _p("data and artifacts")
    crs_dir = Path.home() / ".bb-crs"
    crs = next((f for f in (crs_dir / "bn254_g1.dat", crs_dir / "bn254_g1_compressed.dat") if f.exists()), None)
    print(f"  {'✓' if DATASET_META.exists() else '·'} dataset          {DATASET_META if DATASET_META.exists() else 'not fetched yet: python -m hourproof data fetch'}")
    print(f"  {'✓' if BACKTEST_JSON.exists() else '·'} agent backtest   {'done' if BACKTEST_JSON.exists() else 'python -m hourproof agent backtest'}")
    print(f"  {'✓' if (CONTRACTS / 'src/generated/HonkVerifier.sol').exists() else '·'} ZK verifier      "
          f"{'generated' if (CONTRACTS / 'src/generated/HonkVerifier.sol').exists() else 'python -m hourproof zk build'}")
    emis = CONTRACTS / "src/generated/EmissionsHonkVerifier.sol"
    print(f"  {'✓' if emis.exists() else '·'} emissions verifier {'generated' if emis.exists() else 'python -m hourproof zk build'}")
    print(f"  {'✓' if crs else '·'} bb CRS cache    {crs if crs else 'downloaded automatically on first proof (needs internet)'}")
    _p("network")
    net_ok = False
    try:
        import requests
        r = requests.get("https://api.energidataservice.dk/dataset/Forecasts_Hour?limit=1", timeout=15)
        net_ok = r.ok
        print(f"  {'✓' if r.ok else '✗'} Energi Data Service HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ Energi Data Service unreachable: {str(e)[:160]}")
    if not ok:
        print("\nFix the ✗ lines above.")
    elif not net_ok:
        print("\nTools OK. No internet to Energinet: data fetch, live mode and the first proof (CRS download) need it.")
    else:
        print("\nALL GOOD")
    return ok


def cmd_data(a) -> None:
    from . import dataset
    if a.action == "fetch":
        dataset.build(year=a.year, branch_code=a.branch)
    elif a.action == "import":
        dataset.import_k1_csv(a.path, label=a.branch)
    elif a.action == "import-carbon":
        dataset.import_carbon(a.path or str(ROOT / "hp_ai"))
    elif a.action == "fetch-carbon":
        dataset.build_carbon(year=a.year)
    else:
        print(json.dumps(json.loads(DATASET_META.read_text()), indent=2) if DATASET_META.exists() else "no dataset")


def cmd_carbon(_a=None) -> None:
    from . import carbon
    r = carbon.run()
    print(json.dumps({"test_period": r["periods"]["test"], "forecast_mae_g_per_kwh": r["forecast"]["test_mae_g_per_kwh"],
                      "emissions_t": {s: round(v["emissions_t"], 1) for s, v in r["strategies"].items()},
                      "coverage": {s: round(v["coverage"], 4) for s, v in r["strategies"].items()},
                      "reductions_vs_no_shift": r["reductions_vs_no_shift"],
                      "max_abs_rel_diff_vs_killtest": max(abs(v) for v in r["reproduction_rel_diff"].values())}, indent=2))


def ensure_carbon_data() -> None:
    from .config import CARBON_CSV
    if CARBON_CSV.exists():
        return
    from . import dataset
    if (ROOT / "hp_ai" / "energinet_hourly.csv").exists():
        dataset.import_carbon(str(ROOT / "hp_ai"))
    else:
        dataset.build_carbon()


def cmd_agent(a) -> None:
    if a.action == "carbon":
        ensure_carbon_data()
        return cmd_carbon(a)
    from . import agent, dataset
    df, _ = dataset.load()
    params = agent.AgentParams(flex_share=a.flex, topup_share=a.topup)
    if a.action == "select":
        cfg = agent.freeze(df, params, force=a.force)
        print(f"frozen on validation {agent.periods(df)['validation']}: {cfg.tag()}")
    elif a.action == "ablate":
        print(json.dumps(agent.ml_ablation(df, params), indent=2))
    elif a.action == "backtest":
        r = agent.run_backtest(df, params)
        print(json.dumps({k: r[k] for k in ("test_period", "selected_config", "coverage", "extra_share_of_test_load",
                                            "forecast_skill", "gain_vs_same_mwh_pp")}, indent=2))
    else:
        for row in agent.sensitivity(df):
            print(json.dumps(row))


def cmd_zk(a) -> None:
    from . import zk
    if a.action == "build":
        zk.compile_circuits()
        meta = zk.build_verifier()
        r = subprocess.run(["forge", "build"], cwd=CONTRACTS)
        if r.returncode:
            raise SystemExit("forge build failed after generating the verifiers")
        meta["runtime_bytes"] = zk.check_eip170()  # STOP if a verifier cannot be deployed
        print(json.dumps(meta, indent=2))
    elif a.action == "fixture":
        import secrets
        from .demo import Run
        info = Run(network="local", mode="procurement").prepare_data(persist=False)
        salt = secrets.randbelow(2**200)
        bps = min(a.target, info["coverage_agent_bps"])
        cert_kwh = [m * 1000 for m in info["cert_mwh"]]
        commitment = zk.commit_load(info["load_kwh"], salt)
        proof = zk.prove(info["load_kwh"], salt, bps, cert_kwh, Path(ROOT / "data" / "fixture_proof"))
        if proof["public_inputs"][-1].lower() != commitment.lower():
            raise SystemExit("commitment mismatch between load_commit and coverage circuits")
        out = CONTRACTS / "test" / "fixtures" / "zk" / "fixture.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"window_start": info["window_start_unix"], "threshold_bps": bps, "proof": proof["proof"],
                                   "load_commitment": commitment, "cert_mwh": info["cert_mwh"],
                                   "note": "real Energinet week; load stays private (only its commitment is here)"}, indent=1))
        print(f"wrote {out}  (prove {proof['prove_seconds']} s, {proof['proof_bytes']} bytes, native verify {proof['native_verify']})")
        emissions_fixture()


def emissions_fixture() -> dict:
    """Real emissions proof over the kill test's K4 week (real Energinet load, wind and intensity), for
    EmissionsIntegration.t.sol. Also checks: the commitment equals load_commit's (one attestation serves both
    proofs), the cap 1 kg lower is refused by the prover, and the numbers match the kill test."""
    import secrets
    from . import carbon, dataset, zk
    ensure_carbon_data()
    E, _ = dataset.load_carbon()
    wk = carbon.zk_week(E, carbon.K4_WEEK)
    salt = secrets.randbelow(2**200)
    commitment = zk.commit_load(wk["load_kwh"], salt)
    outdir = ROOT / "data" / "fixture_proof_emissions"
    proof = zk.prove_emissions(wk["load_kwh"], salt, wk["threshold_bps"], wk["cap_kg"], wk["cert_kwh"],
                               wk["intensity_g_per_kwh"], outdir)
    if proof["public_inputs"][-1].lower() != commitment.lower():
        raise SystemExit("commitment mismatch between load_commit and emissions circuits")
    try:
        zk.prove_emissions(wk["load_kwh"], salt, wk["threshold_bps"], wk["cap_kg"] - 1, wk["cert_kwh"],
                           wk["intensity_g_per_kwh"], ROOT / "data" / "fixture_proof_emissions_refused")
        refused = False
    except zk.ProverRefused:
        refused = True
    if not refused:
        raise SystemExit("the emissions prover accepted a cap 1 kg below the truth")
    gates_out = subprocess.run([zk.tool("bb"), "gates", "-b", str(zk.TARGET / "emissions.json")], capture_output=True,
                               text=True).stdout
    import re
    m = re.search(r'"circuit_size":\s*(\d+)', gates_out)
    out = CONTRACTS / "test" / "fixtures" / "zk" / "emissions_fixture.json"
    out.write_text(json.dumps({
        "window_start": wk["window_start_unix"], "threshold_bps": wk["threshold_bps"], "cap_kg": wk["cap_kg"],
        "proof": proof["proof"], "load_commitment": commitment, "cert_mwh": wk["cert_mwh"],
        "intensity_g_per_kwh": wk["intensity_g_per_kwh"],
        "note": "real Energinet week (the carbon kill test's K4 week); load stays private (only its commitment is here)"},
        indent=1))
    meta = {"week_utc": wk["window_start_utc"], "threshold_bps": wk["threshold_bps"], "cap_kg": wk["cap_kg"],
            "residual_t": wk["residual_g"] / 1e6, "prove_seconds": proof["prove_seconds"],
            "proof_bytes": proof["proof_bytes"], "native_verify": proof["native_verify"], "cap_minus_1kg_refused": refused,
            "circuit_gates": int(m.group(1)) if m else None, "public_inputs": len(proof["public_inputs"]),
            "commitment_equals_load_commit": True, "killtest_reference": carbon.K4_REFERENCE}
    (ROOT / "data" / "zk_emissions_fixture.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {out}  (week {wk['window_start_utc'][:10]}: coverage >= {wk['threshold_bps'] / 100:.2f}%, residual <= "
          f"{wk['cap_kg'] / 1000:,.1f} t; prove {proof['prove_seconds']} s, native verify {proof['native_verify']}, "
          f"cap 1 kg lower refused, {meta['circuit_gates']} gates)")
    return meta


def cmd_demo(a) -> None:
    from .demo import Run
    st = Run(network=a.network, zk_mode=a.zk, target_bps=a.target, window=a.window, port=a.port, mode=a.mode).execute()
    _p("result")
    print(json.dumps({"status": st["status"], **st.get("summary", {})}, indent=2))
    if st["status"] != "done":
        raise SystemExit(1)


def cmd_serve(a) -> None:
    import uvicorn
    from .server import FRONTEND_DIST
    if not (FRONTEND_DIST / "spa.html").exists():
        print("The dashboard is not built: run `make web` first (needs Node 22; see 'The dashboard' in the README).\n"
              "The API still starts, and the page explains this until the build exists.")
    print(f"HourProof dashboard: http://127.0.0.1:{a.port}")
    uvicorn.run("hourproof.server:app", host="127.0.0.1", port=a.port, log_level="warning")


def cmd_live(a) -> None:
    from . import live
    (live.commit if a.action == "commit" else live.score)(network=a.network, **({"day": a.day} if a.action == "commit" else {}))


def wallet_new() -> None:
    """Create a THROWAWAY testnet key straight into .env. The key is never printed; only the address is."""
    import re
    from .chain import run, tool
    from .config import testnet_key
    env = ROOT / ".env"
    text = env.read_text() if env.exists() else (ROOT / ".env.example").read_text()
    m = re.search(r"^PRIVATE_KEY=(.*)$", text, re.M)
    if env.exists() and m:
        try:
            testnet_key(m.group(1).strip().strip('"').strip("'"))
            raise SystemExit(f"{env} already holds a valid PRIVATE_KEY; not overwriting it. "
                             "Run `python -m hourproof wallet check` to see its address and balance.")
        except SystemExit as e:
            if "already holds" in str(e):
                raise
    out = run([tool("cast"), "wallet", "new", "--json"])
    if out.returncode:
        raise SystemExit("cast wallet new failed")
    w = json.loads(out.stdout)
    w = w.get("data", w) if isinstance(w, dict) else w  # newer Foundry: {"success", "data": [...], ...}
    w = w[0] if isinstance(w, list) else w
    key, address = testnet_key(w["private_key"]), w["address"]
    line = f"PRIVATE_KEY={key}"
    text = re.sub(r"^PRIVATE_KEY=.*$", lambda _: line, text, flags=re.M) if m else text.rstrip("\n") + "\n" + line + "\n"
    env.write_text(text)
    try:
        env.chmod(0o600)
    except OSError:
        pass
    print(f"Wrote a new THROWAWAY key to {env} (git-ignored; the key itself is not shown).")
    print(f"Address to fund on Base Sepolia: {address}")
    print("Next: get Base Sepolia ETH for that address from a faucet, then run `python -m hourproof wallet check`.")


def wallet_check(mode: str = "carbon") -> bool:
    """Read-only Base Sepolia preflight: RPC chain id, the admin address, fee cap, balances, the funding needed for
    the same week and mode `make demo-base` will run, and the local artifacts. Sends nothing, never prints the key.
    Fails closed: any missing input (RPC data, the measured local run, the verifiers) means NOT READY."""
    import pandas as pd
    from . import zk
    from .chain import Chain
    from .config import BASE_SEPOLIA_CHAIN_ID, base_sepolia_network
    from .demo import ensure_contracts_built, funding_plan, planned_gas_by_role, representative_week
    net = base_sepolia_network()
    ch = Chain(net)
    cid = ch.chain_id()
    print(f"RPC            {net.rpc}")
    print(f"chain id       {cid} {'(Base Sepolia)' if cid == BASE_SEPOLIA_CHAIN_ID else '!! NOT Base Sepolia'}")
    if cid != BASE_SEPOLIA_CHAIN_ID:
        raise SystemExit(f"refusing: the RPC reports chain {cid}, expected {BASE_SEPOLIA_CHAIN_ID}")
    print(f"latest block   {ch.block_timestamp()} (unix time)")
    hours = pd.read_csv(BACKTEST_JSON.with_suffix(".hours.csv"), parse_dates=["hour_utc"]).set_index("hour_utc")
    week = representative_week(hours)
    gas, src = planned_gas_by_role(mode, int(week.tz_localize("UTC").timestamp()))
    plan = funding_plan(ch, gas, src)
    eth = lambda w: f"{w / 1e18:.6f}"  # noqa: E731
    print(f"plan           {mode} demo, week of {week:%Y-%m-%d}; gas per role from real local run {src}; "
          f"{plan['margin']}x margin")
    print(f"fee cap        {plan['fee_cap_gwei']:.4f} gwei (max(gas price, 2 x base fee + priority fee)); "
          f"at most {eth(plan['max_spend_wei'])} ETH spent per run (L1 data fee is negligible here)")
    print(f"admin wallet   {plan['admin_address']}  balance {eth(plan['admin_balance_wei'])} ETH")
    for r, v in plan["roles"].items():
        print(f"  {r:10}   {v['address']}  balance {eth(v['balance_wei'])}  target {eth(v['target_wei'])}  "
              f"will send {eth(v['to_send_wei'])}")
    print(f"admin needs    >= {eth(plan['admin_needs_wei'])} ETH (top-ups + {eth(plan['admin_target_wei'])} for its own "
          f"gas); shortfall {eth(plan['shortfall_wei'])} ETH")
    ensure_contracts_built()
    art = zk.verifier_ready() and zk.emissions_verifier_ready()
    print(f"ZK verifiers   {'generated' if art else 'MISSING: python -m hourproof zk build'}")
    ok = plan["ready"] and art
    print("\nREADY: nothing has been sent. `make demo-base` will broadcast real transactions." if ok else
          "\nNOT READY: fund the admin address above (or fix the missing items).")
    return ok


def cmd_wallet(a) -> None:
    if a.action == "new":
        wallet_new()
    elif not wallet_check():
        raise SystemExit(1)


def cmd_verify(a) -> None:
    from .verify import verify_saved_run
    r = verify_saved_run(a.run, a.state)
    for c in r["checks"]:
        print(f"  {'✓' if c['ok'] else '✗'} {c['check']:58} {c['detail']}")
    print(f"\n{'VERIFIED' if r['ok'] else 'FAILED'}: run {r['run_id']} on {r['network']} ({r['transactions']} transactions)")
    if not r["ok"]:
        raise SystemExit(1)


def cmd_site(a) -> None:
    from . import site
    sizes = site.export()
    print(json.dumps({"snapshot": str(site.SNAPSHOT_DIR), "bytes": sizes}, indent=2))


def run_python_tests() -> bool:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


def cmd_test(_a) -> None:
    ok = run_python_tests()
    ok &= subprocess.run(["forge", "test"], cwd=CONTRACTS).returncode == 0
    ok &= subprocess.run(["nargo", "test", "--workspace"], cwd=ROOT / "circuits").returncode == 0
    raise SystemExit(0 if ok else 1)


def cmd_e2e(a) -> None:
    """Everything, in order, with a checklist at the end."""
    results: list[tuple[str, bool, str]] = []

    def check(name, fn):
        t0 = time.time()
        try:
            r = fn()
            ok = r is not False
            results.append((name, ok, f"{time.time() - t0:.0f}s"))
        except SystemExit as e:
            results.append((name, e.code in (0, None), f"exit {e.code}"))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {str(e)[:160]}"))
        print(f"\n{'✓' if results[-1][1] else '✗'} {name}")
        return results[-1][1]

    check("doctor", cmd_doctor)
    if not DATASET_META.exists():
        check("data fetch (real Energinet data, ~30-50 min first time)", lambda: cmd_data(argparse.Namespace(action="fetch", year=2025, branch=None)))
    check("python unit tests", run_python_tests)
    check("noir circuit tests", lambda: subprocess.run(["nargo", "test", "--workspace"], cwd=ROOT / "circuits").returncode == 0)
    check("agent backtest (real data)", lambda: cmd_agent(argparse.Namespace(action="backtest", flex=0.10, topup=0.05)))
    check("carbon backtest (real data, frozen choices)", lambda: cmd_agent(argparse.Namespace(action="carbon")))
    check("zk build (verifier from circuit)", lambda: cmd_zk(argparse.Namespace(action="build")))
    check("zk fixture (real proof over a real week)", lambda: cmd_zk(argparse.Namespace(action="fixture", target=a.target)))
    check("solidity tests incl. real ZK + real ML-DSA", lambda: subprocess.run(["forge", "test"], cwd=CONTRACTS).returncode == 0)
    check("end-to-end demo, procurement mode (coverage note)",
          lambda: cmd_demo(argparse.Namespace(network="local", zk="real", target=a.target, window=None, port=8545,
                                              mode="procurement")))
    check("end-to-end demo on local replay chain (carbon-aware)",
          lambda: cmd_demo(argparse.Namespace(network="local", zk="real", target=a.target, window=None, port=8545,
                                              mode="carbon")))
    _p("E2E CHECKLIST")
    for name, ok, info in results:
        print(f"  {'✓' if ok else '✗'} {name:55} {info}")
    raise SystemExit(0 if all(ok for _, ok, _ in results) else 1)


def main(argv: list[str] | None = None) -> None:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    ap = argparse.ArgumentParser(prog="hourproof", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check tools, packages, data, network").set_defaults(fn=cmd_doctor)
    d = sub.add_parser("data", help="real Energinet dataset")
    d.add_argument("action", choices=["fetch", "import", "info", "import-carbon", "fetch-carbon"],
                   help="import-carbon: reuse the carbon kill test's downloads (energinet_hourly.csv + cache/*.json); "
                        "fetch-carbon: download them with the cached client")
    d.add_argument("path", nargs="?", help="K1 hourly_2025.csv for `import`; the hp_ai folder for `import-carbon`")
    d.add_argument("--year", type=int, default=2025)
    d.add_argument("--branch", default=None,
                   help="fetch: DK36 code of the buyer branch (default: IT/telecom); import: a label for the branch")
    d.set_defaults(fn=cmd_data)
    g = sub.add_parser("agent", help="AI agent backtest")
    g.add_argument("action", choices=["select", "backtest", "ablate", "sensitivity", "carbon"],
                   help="select: choose and freeze the config on validation; backtest: run the test period with it; "
                        "ablate: frozen config with raw forecast / last-week load on the test period; "
                        "carbon: carbon-aware shifting backtest with the frozen kill-test choices")
    g.add_argument("--force", action="store_true", help="select: overwrite an existing frozen config")
    g.add_argument("--flex", type=float, default=0.10, help="flexible share of hourly load (scenario parameter)")
    g.add_argument("--topup", type=float, default=0.05, help="extra certificate budget, share of annual load")
    g.set_defaults(fn=cmd_agent)
    z = sub.add_parser("zk", help="circuits, verifier, proof fixture")
    z.add_argument("action", choices=["build", "fixture"])
    z.add_argument("--target", type=int, default=7500)
    z.set_defaults(fn=cmd_zk)
    m = sub.add_parser("demo", help="full on-chain scenario with attacks")
    m.add_argument("--network", choices=["local", "base-sepolia"], default="local")
    m.add_argument("--zk", choices=["real", "mock"], default="real", help="mock = test-only, no real proof")
    m.add_argument("--target", type=int, default=7500, help="note KPI: hourly coverage target in basis points")
    m.add_argument("--window", default=None, help="week start (UTC, a Monday inside the agent test period)")
    m.add_argument("--port", type=int, default=8545)
    m.add_argument("--mode", choices=["carbon", "procurement"], default="carbon",
                   help="carbon: carbon-aware load shift, intensity oracle, coverage + residual-emissions proofs, "
                        "RESIDUAL_EMISSIONS note; procurement: the original coverage-only scenario")
    m.set_defaults(fn=cmd_demo)
    s = sub.add_parser("serve", help="dashboard")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    lv = sub.add_parser("live", help="commit tomorrow's agent forecast on-chain / score past days")
    lv.add_argument("action", choices=["commit", "score"])
    lv.add_argument("--network", choices=["local", "base-sepolia"], default="base-sepolia")
    lv.add_argument("--day", default=None, help="UTC day to commit for (default: tomorrow)")
    lv.set_defaults(fn=cmd_live)
    wl = sub.add_parser("wallet", help="throwaway testnet wallet: create it in .env / read-only Base Sepolia preflight")
    wl.add_argument("action", choices=["new", "check"])
    wl.set_defaults(fn=cmd_wallet)
    vf = sub.add_parser("verify", help="re-check a public-chain demo run against the chain (receipts, code, proofs)")
    vf.add_argument("--run", default=None, help="run id under data/runs (default: the latest public-chain run)")
    vf.add_argument("--state", default=None, help="a saved run state file instead, e.g. the evidence bundle's")
    vf.set_defaults(fn=cmd_verify)
    st = sub.add_parser("site", help="static dashboard snapshot of the verified Base Sepolia run (for Vercel)")
    st.add_argument("action", choices=["export"])
    st.set_defaults(fn=cmd_site)
    sub.add_parser("test", help="python + solidity + noir tests").set_defaults(fn=cmd_test)
    e = sub.add_parser("e2e", help="run everything and print a checklist")
    e.add_argument("--target", type=int, default=7500)
    e.set_defaults(fn=cmd_e2e)
    a = ap.parse_args(argv)
    r = a.fn(a)
    if a.cmd == "doctor" and r is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
