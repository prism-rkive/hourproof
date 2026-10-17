"""The static dashboard (Vercel): config, committed snapshot, exporter guards and the build script."""
import csv
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hourproof import site
from hourproof.config import ANVIL_KEYS, ROOT

SNAP = ROOT / "deploy" / "snapshot"


class VercelConfigTests(unittest.TestCase):
    def test_every_api_path_the_frontend_reads_is_rewritten_to_a_snapshot(self):
        js = (ROOT / "web" / "app.js").read_text() + (ROOT / "web" / "carbon.js").read_text()
        read = set(re.findall(r'(?:getJSON|fetch)\("(/api/[a-z]+)"\)', js))
        self.assertEqual(read, {"/api/overview", "/api/week", "/api/carbon"})
        rewrites = {r["source"]: r["destination"] for r in json.loads((ROOT / "vercel.json").read_text())["rewrites"]}
        for path in read:
            self.assertEqual(rewrites[path], path + ".json")
            self.assertTrue((SNAP / Path(path).name).with_suffix(".json").is_file(), path)

    def test_vercel_uploads_only_the_frontend(self):
        ignore = (ROOT / ".vercelignore").read_text().split()
        self.assertEqual(ignore[ignore.index("/*") + 1:][:3], ["!/web", "!/deploy", "!/scripts"])
        self.assertNotIn("!/data", ignore)
        self.assertNotIn("!/.env", ignore)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_the_verified_base_sepolia_run(self):
        o = json.loads((SNAP / "overview.json").read_text())
        self.assertEqual(o["static_snapshot"]["run_id"], site.VERIFIED_RUN)
        self.assertEqual((o["demo"]["network"], o["demo"]["status"], o["demo"]["zk_mode"]), ("base-sepolia", "done", "real"))
        self.assertIn("VERIFIED:", o["static_snapshot"]["verification"])
        self.assertFalse(o["running"])
        self.assertTrue(all(t["url"].startswith("https://sepolia.basescan.org/tx/")
                            for s in o["demo"]["steps"] for t in s["txs"]))

    def test_snapshot_contains_no_private_key(self):
        text = "".join(p.read_text() for p in SNAP.glob("*.json")).lower()
        for k in ANVIL_KEYS:  # the only private keys this repository knows; real keys are checked by the secret scan
            self.assertNotIn(k[2:], text)
        self.assertNotIn("private_key", text)

    def test_annual_match_is_100_percent_from_the_hourly_data(self):
        with open(ROOT / "data" / "hourly.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        k = json.loads((ROOT / "data" / "agent_backtest.json").read_text())["portfolio_share_k"]
        annual = k * sum(float(r["wind_mwh"]) for r in rows) / sum(float(r["load_mwh"]) for r in rows)
        self.assertAlmostEqual(annual, 1.0, places=6)
        self.assertAlmostEqual(json.loads((SNAP / "overview.json").read_text())["annual_match"], annual, places=9)

    def test_frozen_carbon_config_matches_the_backtest(self):
        frozen = json.loads((ROOT / "data" / "carbon_backtest.json").read_text())["frozen_config"]
        snap = json.loads((SNAP / "carbon.json").read_text())["frozen_config"]
        self.assertEqual(snap, {k: frozen[k] for k in ("flex_share", "flex_cap")})

    def test_note_count_is_read_from_the_note_contract(self):
        o = json.loads((SNAP / "overview.json").read_text())
        m = next(s for s in o["demo"]["steps"] if s["id"] == "note")["metrics"]
        self.assertGreater(m["notes_subscribed"], 0)
        self.assertIn(o["demo"]["contracts"]["SustainabilityLinkedNote"]["address"], m["notes_subscribed_source"])
        self.assertIn("totalSupply()", m["notes_subscribed_source"])

    def test_carbon_test_period_is_jul_to_dec_2025(self):  # the "What this does not claim" text names this period
        start, end = json.loads((SNAP / "carbon.json").read_text())["test_period"]
        self.assertEqual((start[:7], end[:7]), ("2025-07", "2025-12"))

    def test_exporter_refuses_an_unverified_or_unfinished_run(self):
        with tempfile.TemporaryDirectory() as d:
            ev = Path(d)
            st = json.loads((site.EVIDENCE / "state.json").read_text())
            (ev / "state.json").write_text(json.dumps(st | {"status": "failed"}))
            (ev / "verify.txt").write_text("VERIFIED: run x")
            with self.assertRaises(SystemExit):
                site.export(ev, ev / "out")
            (ev / "state.json").write_text(json.dumps(st))
            (ev / "verify.txt").write_text("FAILED: run x")
            with self.assertRaises(SystemExit):
                site.export(ev, ev / "out")


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class BuildScriptTests(unittest.TestCase):
    def test_build_produces_the_static_site(self):
        out = subprocess.run(["bash", "scripts/build_site.sh"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        files = sorted(p.relative_to(ROOT / "site").as_posix() for p in (ROOT / "site").rglob("*") if p.is_file())
        self.assertEqual(files, ["api/carbon.json", "api/overview.json", "api/week.json", "index.html",
                                 "static/app.js", "static/carbon.js", "static/styles.css"])


if __name__ == "__main__":
    unittest.main()
