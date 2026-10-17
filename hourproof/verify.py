"""Independent check of a demo run against the chain itself (no trust in the run's own log).

For every transaction the run recorded: the receipt exists, succeeded, and matches block, gas and target. For every
contract: code is deployed. The wiring: ClaimManager points at the deployed verifiers and the intensity oracle. The
proofs: the exact bytes submitted in the submitProof / submitEmissionsProof transactions are re-verified with an
eth_call to the deployed UltraHonk verifier against the public inputs ClaimManager rebuilds now, and the same proof
with one flipped byte must fail. Finally the on-chain results (proven coverage, proven residual, revealed plans)
must equal what the run reported. Read-only: sends no transaction.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .chain import Chain, b32, tool
from .config import AGENT_ID, BASE_SEPOLIA_CHAIN_ID, RUNS, Network

MIN_VERIFIER_CODE = 10_000  # bytes: the generated UltraHonk verifiers are ~18 KB; a mock is a few hundred


def _decode_submit(input_hex: str, n_static: int) -> tuple[list[int], bytes]:
    """ABI-decode submitProof(uint256,uint32,bytes) / submitEmissionsProof(uint256,uint32,uint64,bytes) calldata:
    `n_static` static words, then the offset of the dynamic bytes."""
    data = bytes.fromhex(input_hex.removeprefix("0x"))[4:]
    words = [int.from_bytes(data[32 * i:32 * i + 32], "big") for i in range(n_static + 1)]
    off = words[n_static]
    length = int.from_bytes(data[off:off + 32], "big")
    return words[:n_static], data[off + 32:off + 32 + length]


def _list(text: str) -> list[str]:
    body = text.strip().strip("[]").strip()
    return [x.strip().split(" ")[0] for x in body.split(",")] if body else []


def _verify_call(ch: Chain, verifier: str, proof: bytes, pubs: list[str]) -> bool:
    try:
        return ch.call(verifier, "verify(bytes,bytes32[])(bool)", ["0x" + proof.hex(), "[" + ",".join(pubs) + "]"]) == "true"
    except Exception:  # noqa: BLE001  (the generated verifier reverts on a malformed or wrong proof)
        return False


def verify_run(ch: Chain, state: dict) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    c = {k: v["address"] for k, v in state["contracts"].items()}
    txs = [t for s in state["steps"] for t in s.get("txs", [])]
    check("chain id", ch.chain_id() == ch.net.chain_id, f"{ch.chain_id()}")

    bad = []
    for t in txs:
        out = ch._read([tool("cast"), "receipt", t["hash"], "--json", "--rpc-url", ch.net.rpc])
        if out.returncode:
            bad.append(f"{t['label']}: no receipt")
            continue
        rc = json.loads(out.stdout[out.stdout.index("{"):])
        target = (rc.get("contractAddress") or rc.get("to") or "").lower()
        if rc.get("status") not in ("0x1", 1, "1"):
            bad.append(f"{t['label']}: status {rc.get('status')}")
        elif int(rc["blockNumber"], 16) != t["block"] or int(rc["gasUsed"], 16) != t["gas"]:
            bad.append(f"{t['label']}: block/gas differ")
        elif t.get("to") and target != t["to"].lower():
            bad.append(f"{t['label']}: target differs")
    check("receipts", not bad, f"{len(txs) - len(bad)}/{len(txs)} succeeded and match" + (f"; {bad[:3]}" if bad else ""))

    empty = []
    for name, addr in c.items():
        out = ch._read([tool("cast"), "codesize", addr, "--rpc-url", ch.net.rpc])
        if out.returncode or int(out.stdout.strip() or 0) == 0:
            empty.append(name)
    check("contract code deployed", not empty, f"{len(c) - len(empty)}/{len(c)}" + (f"; empty: {empty}" if empty else ""))

    real = state.get("zk_mode") == "real"
    cm = c["ClaimManager"]
    cov_v = c.get("HonkVerifier") or c.get("MockZKVerifier")
    check("ClaimManager uses the deployed coverage verifier", ch.call(cm, "verifier()(address)").lower() == cov_v.lower(), cov_v)
    em_v = c.get("EmissionsHonkVerifier") or c.get("MockEmissionsZKVerifier")
    if em_v:
        check("ClaimManager uses the deployed emissions verifier",
              ch.call(cm, "emissionsVerifier()(address)").lower() == em_v.lower(), em_v)
        check("ClaimManager reads the deployed intensity oracle",
              ch.call(cm, "intensityOracle()(address)").lower() == c["IntensityOracle"].lower(), c["IntensityOracle"])

    submits = [("coverage", "submit coverage proof", cov_v, 2), ("emissions", "submit emissions proof", em_v, 3)]
    for kind, label, verifier, n_static in submits:
        t = next((t for t in txs if t["label"] == label), None)
        if t is None:
            continue
        if not real:
            checks.append({"check": f"{kind} proof", "ok": True, "detail": "not checked: MOCK verifier (test mode)"})
            continue
        size = int(ch._read([tool("cast"), "codesize", verifier, "--rpc-url", ch.net.rpc]).stdout.strip() or 0)
        if real:
            check(f"{kind} verifier is the real UltraHonk verifier (code size)", size >= MIN_VERIFIER_CODE, f"{size:,} bytes")
        out = ch._read([tool("cast"), "tx", t["hash"], "input", "--rpc-url", ch.net.rpc])
        args, proof = _decode_submit(out.stdout.strip(), n_static)
        if kind == "coverage":
            pubs = _list(ch.call(cm, "publicInputs(uint256,uint32)(bytes32[])", args[:2]))
        else:
            pubs = _list(ch.call(cm, "emissionsPublicInputs(uint256,uint32,uint64)(bytes32[])", args[:3]))
        ok = _verify_call(ch, verifier, proof, pubs)
        check(f"{kind} proof from the tx re-verifies on-chain", ok,
              f"{len(proof):,}-byte proof, {len(pubs)} public inputs rebuilt by ClaimManager")
        if real:
            bad_proof = bytearray(proof)
            bad_proof[len(bad_proof) // 2] ^= 0x01
            check(f"{kind} proof with one flipped byte is rejected", not _verify_call(ch, verifier, bytes(bad_proof), pubs))

    ws = state["window"]["window_start_unix"]
    buyer_addr = ch.addr("buyer")
    s = state["summary"]
    onchain_bps = int(ch.call(cm, "bestProvenBps(address,uint64)(uint32)", [buyer_addr, ws]).split()[0])
    check("proven coverage on-chain", onchain_bps == s.get("proven_bps"), f"{onchain_bps / 100:.2f}%")
    if "proven_residual_kg" in s:
        kg = int(ch.call(cm, "bestResidualKgOf(address,uint64)(uint64)", [buyer_addr, ws]).split()[0])
        check("proven residual on-chain", kg == s["proven_residual_kg"], f"{kg / 1000:,.1f} t")
    log = c["AgentCommitLog"]
    revealed = sum(ch.call(log, "entries(address,bytes32,uint64)(bytes32,uint64,bool,bool)",
                           [ch.addr("agent"), b32(AGENT_ID), ws + i * 86400]).splitlines()[3] == "true" for i in range(7))
    check("agent plans revealed on-chain", revealed == 7, f"{revealed}/7")
    return {"ok": all(x["ok"] for x in checks), "checks": checks, "transactions": len(txs), "zk_mode": state.get("zk_mode")}


def verify_saved_run(run_id: str | None = None, state_path: str | None = None) -> dict:
    """Re-check a finished public-chain run from data/runs/<id>/state.json, or from any saved state file (e.g. the
    evidence bundle in a fresh clone). Local replay chains are gone after a run, so only public runs qualify.
    No private key is needed: every role address is read from the run's own transaction receipts."""
    runs = sorted(RUNS.glob("*/state.json"))
    if state_path:
        path = Path(state_path)
    else:
        path = RUNS / run_id / "state.json" if run_id else next(
            (p for p in reversed(runs) if json.loads(p.read_text())["network"] != "local"), None)
    if not path or not path.exists():
        raise SystemExit("no public-chain run to verify (local replay chains are verified inside the run)")
    state = json.loads(path.read_text())
    if state["network"] != "base-sepolia":
        raise SystemExit(f"{path}: ran on '{state['network']}', not Base Sepolia; local replay chains no longer exist "
                         "(their in-run verification step is in the state file)")
    net = Network("base-sepolia", os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org"), BASE_SEPOLIA_CHAIN_ID,
                  "https://sepolia.basescan.org", {})  # read-only: no signing keys at all
    ch = Chain(net)
    for s in state["steps"]:  # role -> address, from the chain itself
        for t in s.get("txs", []):
            if t.get("role") and t["role"] not in ch._addr:
                out = ch._read([tool("cast"), "receipt", t["hash"], "from", "--rpc-url", net.rpc])
                if out.returncode == 0 and out.stdout.strip().startswith("0x"):
                    ch._addr[t["role"]] = out.stdout.strip()
    return verify_run(ch, state) | {"run_id": state["run_id"], "network": state["network"], "state_file": str(path)}
