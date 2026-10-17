#!/usr/bin/env python3
"""Independent, read-only re-check of a recorded HourProof public run, using only Foundry's `cast` and the run's state
file (no keys, no project code). Complements `python -m hourproof verify` (receipts, contract code, both ZK proofs
re-verified on-chain) with: the note's settlement, the ML-DSA issuance record, the on-chain outcome of the refused
attacks, and a nonce reconciliation of every wallet against every recorded public attempt.

    python3 scripts/check_public_run.py [evidence/base-sepolia-20261017T141639Z/state.json]

Sends nothing. Exit code 0 only if every check passes.
"""
from __future__ import annotations

import collections
import glob
import json
import subprocess
import sys
from pathlib import Path

RPC = "https://sepolia.base.org"
HERE = Path(__file__).resolve().parent.parent


def cast(*a: str, rpc: bool = True) -> str:
    args = ["cast", *a] + (["--rpc-url", RPC] if rpc else [])
    return subprocess.run(args, capture_output=True, text=True, timeout=120).stdout.strip()


def call(addr: str, sig: str, *args) -> str:
    return cast("call", addr, sig, *map(str, args)).split()[0]


def b32(s: str) -> str:
    return "0x" + s.encode().hex().ljust(64, "0")


def topic(sig: str) -> str:
    return cast("keccak", sig, rpc=False).lower()  # local hash: no RPC flag


def receipt(h: str) -> dict:
    return json.loads(cast("receipt", h, "--json"))


def main(state_path: str) -> int:
    d = json.loads(Path(state_path).read_text())
    if d.get("network") != "base-sepolia" or d.get("status") != "done":
        print(f"{state_path}: not a completed base-sepolia run")
        return 1
    if cast("chain-id") != "84532":
        print("RPC is not Base Sepolia (84532)")
        return 1
    c = {k: v["address"] for k, v in d["contracts"].items()}
    ws = d["window"]["window_start_unix"]
    txs = {t["label"]: t for s in d["steps"] for t in s["txs"]}
    ok: list[bool] = []

    def check(name: str, good: bool, detail: str = "") -> None:
        ok.append(bool(good))
        print(f"  {'✓' if good else '✗'} {name}{': ' + detail if detail else ''}")

    # wallet addresses from the receipts themselves (sender of each role's txs; recipients of "fund <role>")
    states = sorted(glob.glob(str(HERE / "evidence" / "**" / "state.json"), recursive=True))
    wallets: dict[str, str] = {}
    for p in states:
        for s in json.loads(Path(p).read_text())["steps"]:
            for t in s["txs"]:
                if t.get("role") and t["role"] not in wallets:
                    wallets[t["role"]] = receipt(t["hash"])["from"]
                if t["label"].startswith("fund "):
                    wallets.setdefault(t["label"].split()[1], receipt(t["hash"])["to"])

    print(f"run {d['run_id']} on Base Sepolia (84532), {sum(len(s['txs']) for s in d['steps'])} recorded transactions")
    print("== settlement (SustainabilityLinkedNote, KPI = RESIDUAL_EMISSIONS)")
    n = c["SustainabilityLinkedNote"]
    check("note settled", call(n, "settled()(bool)") == "true")
    check("KPI kind RESIDUAL_EMISSIONS", call(n, "kpiKind()(uint8)") == "1")
    tgt = int(call(n, "targetResidualKg()(uint64)"))
    proven = int(call(c["ClaimManager"], "bestResidualKgOf(address,uint64)(uint64)", wallets["buyer"], ws))
    met = call(n, "kpiMet()(bool)")
    check("KPI outcome follows the proof", (met == "true") == (proven <= tgt),
          f"proven {proven:,} kg vs target {tgt:,} kg, kpiMet={met}")
    cb = int(call(n, "couponBps()(uint32)"))
    check("coupon matches the outcome", cb == (500 if met == "true" else 600), f"{cb} bps")
    st = receipt(txs["settle the note"]["hash"])
    dl = int(call(n, "deadline()(uint64)"))
    ts = int(cast("block", str(int(st["blockNumber"], 16)), "--field", "timestamp"), 0)
    check("settle receipt succeeded" + ("" if met == "true" else " after the deadline"),
          st["status"] == "0x1" and (met == "true" or ts >= dl), f"block time {ts}, deadline {dl}")
    ev = [l for l in st["logs"] if l["topics"][0].lower() == topic("SettledResidual(bool,uint64,uint32)")
          and l["address"].lower() == n.lower()]
    vals = [int(ev[0]["data"][2 + i:66 + i], 16) for i in range(0, 192, 64)] if ev else []
    check("SettledResidual event", vals == [int(met == "true"), proven, cb], f"{vals}")
    inv = int(call(c["TestUSD"], "balanceOf(address)(uint256)", wallets["investor"]))
    check("investor received the coupon", inv == cb * 10**21 // 10000, f"{inv / 1e18:g} tUSD on 1,000 notes")
    check("coupon claimed", call(n, "couponClaimed(address)(bool)", wallets["investor"]) == "true")

    print("== ML-DSA-44 certificate issuance (verified on-chain by MLDSA44Verifier)")
    issue = [t for t in d["steps"] if t["id"] == "issue"][0]["txs"]
    nonce_a = int(cast("call", c["RegistryA"], "issuers(bytes32)(address,bool,uint64)", b32("issuer-A")).splitlines()[2].split()[0])
    check("issuer A batches accepted", nonce_a == len(issue), f"issuer nonce {nonce_a}, {len(issue)} issuance txs")
    bi = topic("BatchIssued(bytes32,uint64,uint256,uint256,bytes32)")
    seen = [int(l["data"][2:66], 16) for t in issue for l in receipt(t["hash"])["logs"]
            if l["topics"][0].lower() == bi and l["address"].lower() == c["RegistryA"].lower()]
    check("BatchIssued in every issuance receipt", seen == list(range(len(issue))), f"nonces {seen}")
    nonce_b = int(cast("call", c["RegistryB"], "issuers(bytes32)(address,bool,uint64)", b32("issuer-B")).splitlines()[2].split()[0])
    check("registry B: only its one legitimate batch", nonce_b == 1, f"issuer nonce {nonce_b}")

    print("== refused attacks left no on-chain effect")
    g = d["window"]["intensity_g_per_kwh"]
    i = max(range(len(g)), key=g.__getitem__)
    v = int(call(c["IntensityOracle"], "intensityOf(bytes32,uint64)(uint32)", b32("DK"), ws + 3600 * i))
    check("intensity re-post: value unchanged", v == g[i], f"hour {i} = {v} g/kWh")
    bps = int(call(c["ClaimManager"], "bestProvenBps(address,uint64)(uint32)", wallets["buyer"], ws))
    check("replayed proof: coverage not raised", bps == d["summary"]["proven_bps"], f"{bps / 100:.2f}%")
    check("fake intensity: residual not lowered", proven == d["summary"]["proven_residual_kg"], f"{proven:,} kg")
    print(f"  · attack outcomes recorded by the run: {[(a['id'], a['observed']) for a in d['attacks']]}")

    print(f"== nonces vs every recorded public attempt ({len(states)} state files)")
    rec = collections.Counter(t["role"] for p in states for s in json.loads(Path(p).read_text())["steps"] for t in s["txs"])
    for r, a in sorted(wallets.items()):
        latest, pending = int(cast("nonce", a)), int(cast("nonce", a, "--block", "pending"))
        check(r, latest == pending == rec[r], f"{a}: recorded {rec[r]}, nonce {latest}, pending {pending}")
    print("ALL CHECKS PASSED" if all(ok) else f"{ok.count(False)} CHECK(S) FAILED")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  str(HERE / "evidence" / "base-sepolia-20261017T141639Z" / "state.json")))
