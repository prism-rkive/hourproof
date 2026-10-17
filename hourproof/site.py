"""Static snapshot of the dashboard, for hosting without a backend (Vercel).

    python -m hourproof site export     # -> deploy/snapshot/{overview,week,carbon}.json (commit these)
    bash scripts/build_site.sh          # -> site/ (what Vercel serves; built by Vercel from vercel.json)

The snapshot is produced by the dashboard's own API handlers (hourproof/server.py), fed with the committed evidence
of the verified Base Sepolia run instead of the last local demo state, so the hosted page shows exactly what the
chain confirmed, with explorer links. The hosted page cannot start runs; `make serve` keeps the full local version.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest import mock

from .config import ROOT

VERIFIED_RUN = "20261017T141639Z"
EVIDENCE = ROOT / "evidence" / f"base-sepolia-{VERIFIED_RUN}"
SNAPSHOT_DIR = ROOT / "deploy" / "snapshot"


def export(evidence=EVIDENCE, out=SNAPSHOT_DIR) -> dict:
    from . import server
    state_file = evidence / "state.json"
    state = json.loads(state_file.read_text())
    if state.get("network") != "base-sepolia" or state.get("status") != "done":
        raise SystemExit(f"{state_file}: not a completed Base Sepolia run; refusing to publish it as verified")
    verify_log = (evidence / "verify.txt").read_text() if (evidence / "verify.txt").exists() else ""
    if "VERIFIED:" not in verify_log:
        raise SystemExit(f"{evidence}/verify.txt does not record a passing `hourproof verify`; run it first")

    async def body(handler):
        return json.loads((await handler(None)).body)

    with mock.patch.object(server, "DEMO_STATE", state_file), mock.patch.dict(server._running, {"active": False}):
        overview = asyncio.run(body(server.overview))
        week = asyncio.run(body(server.week))
        carbon = asyncio.run(body(server.carbon_view))
    overview["static_snapshot"] = {
        "run_id": state["run_id"], "network": state["network"],
        "verification": "re-verified on-chain: " + next(l for l in verify_log.splitlines() if l.startswith("VERIFIED:")),
        "evidence": f"evidence/base-sepolia-{VERIFIED_RUN}/",
        "exported_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    overview["running"] = False
    out.mkdir(parents=True, exist_ok=True)
    files = {"overview.json": overview, "week.json": week, "carbon.json": carbon}
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return {name: (out / name).stat().st_size for name in files}
