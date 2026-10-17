"""Integration: the full on-chain scenario on a local anvil chain.
Uses the TEST-ONLY synthetic year and the MOCK ZK verifier, so it runs offline in ~1 min.
The real-data, real-proof run is `python -m hourproof e2e`."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

TOOLS = all(shutil.which(t) for t in ("anvil", "cast", "forge", "nargo"))
try:
    import dilithium_py  # noqa: F401
except ImportError:
    TOOLS = False


def _carbon_fixture(df: pd.DataFrame, d: Path) -> None:
    """TEST-ONLY carbon inputs aligned with the synthetic year: intensity, forecasts and prices are random, the
    'forecast' is persistence (no model training), so the carbon demo path runs offline in seconds."""
    from hourproof import carbon, dataset
    rng = np.random.default_rng(7)
    E = pd.DataFrame(index=df.index)
    E["wind_mwh"] = df["wind_mwh"].to_numpy()
    E["co2_g_per_kwh"] = np.clip(150 + 80 * np.sin(np.arange(len(df)) / 37) + rng.normal(0, 25, len(df)), 5, 600)
    E["load_mwh"] = df["load_mwh"].to_numpy()
    for c in dataset.CARBON_FC_COLUMNS:
        E[c] = rng.uniform(0, 1000, len(df))
    E["price_eur"] = rng.uniform(-10, 200, len(df))
    dataset._write_carbon(E, {"source": "synthetic test fixture"})
    meta = json.loads((d / "carbon_hourly_meta.json").read_text())
    meta["synthetic"] = True
    (d / "carbon_hourly_meta.json").write_text(json.dumps(meta))
    D, k = carbon.test_frame(E, E["co2_g_per_kwh"].shift(168), start=pd.Timestamp("2025-06-01"))
    plans: dict = {}
    new = carbon.strategy_load(D, k, "carbon_model", carbon.FROZEN, plans)
    pd.DataFrame({"hour_utc": D.index, "load": D["load_mwh"].to_numpy(), "carbon_model_load": new.to_numpy(),
                  "base_cert": D["base"].to_numpy(), "co2_actual": D["co2_g_per_kwh"].to_numpy(),
                  "co2_forecast": D["I_model"].to_numpy()}).to_csv(d / "carbon_backtest.hours.csv", index=False)
    (d / "carbon_backtest.json").write_text(json.dumps({"fixture": True}))
    (d / "carbon_plans").mkdir()
    for day, shift in plans.items():
        g = D.loc[day: day + pd.Timedelta(hours=23)]
        (d / "carbon_plans" / f"{day:%Y-%m-%d}.json").write_bytes(carbon.plan_json(day, g["I_model"], shift, g["load_hat"]))


@unittest.skipUnless(TOOLS and os.environ.get("HOURPROOF_SKIP_E2E") != "1", "needs foundry + nargo + dilithium-py")
class LocalScenario(unittest.TestCase):
    def _run(self, mode: str, window: str | None = None) -> dict:
        from hourproof import agent, carbon, config, dataset, demo
        from tests.synthetic import synthetic_year
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            patches = {
                "DATASET_CSV": d / "hourly.csv", "DATASET_META": d / "hourly_meta.json",
                "BACKTEST_JSON": d / "agent_backtest.json", "PLANS_DIR": d / "plans",
                "DEMO_STATE": d / "demo_state.json", "RUNS": d / "runs",
                "CARBON_CSV": d / "carbon_hourly.csv", "CARBON_META": d / "carbon_hourly_meta.json",
                "CARBON_BACKTEST_JSON": d / "carbon_backtest.json", "CARBON_PLANS_DIR": d / "carbon_plans",
            }
            mods = [config, dataset, agent, carbon, demo]
            ctx = [mock.patch.object(m, k, v) for m in mods for k, v in patches.items() if hasattr(m, k)]
            ctx.append(mock.patch.object(config, "KEYS", d))
            for c in ctx:
                c.start()
            try:
                (d / "runs").mkdir()
                df = synthetic_year()
                dataset._write(df, {"source": "synthetic test fixture"})
                meta = json.loads((d / "hourly_meta.json").read_text())
                meta["synthetic"] = True
                (d / "hourly_meta.json").write_text(json.dumps(meta))
                agent.backtest(df)
                if mode == "carbon":
                    _carbon_fixture(df, d)
                with mock.patch("hourproof.pq.KEYS", d):
                    return demo.Run(network="local", zk_mode="mock", allow_synthetic=True, port=8599, mode=mode,
                                    window=window).execute()
            finally:
                for c in reversed(ctx):
                    c.stop()

    def test_full_scenario_mock_zk(self):
        st = self._run("procurement")
        self.assertEqual(st["status"], "done", st.get("error"))
        self.assertEqual(st["summary"]["attacks_blocked"], st["summary"]["attacks_total"])
        expected = {"double_claim": "SliceAlreadyClaimed", "over_issuance": "ExceedsProduction",
                    "forged_signature": "BadIssuerSignature", "replay_higher": "ProofRejected"}
        got = {a["id"]: a["observed"] for a in st["attacks"]}
        for k, v in expected.items():
            self.assertEqual(got.get(k), v)
        note = next(s for s in st["steps"] if s["id"] == "note")["metrics"]
        self.assertIn(note["coupon_bps"], (500, 600))

    def test_carbon_scenario_mock_zk(self):
        st = self._run("carbon", window="2025-09-01")
        self.assertEqual(st["status"], "done", st.get("error"))
        self.assertEqual(st["summary"]["attacks_blocked"], st["summary"]["attacks_total"])
        expected = {"double_claim": "SliceAlreadyClaimed", "over_issuance": "ExceedsProduction",
                    "forged_signature": "BadIssuerSignature", "replay_higher": "ProofRejected",
                    "intensity_repost": "AlreadyPosted", "fake_intensity": "ProofRejected"}
        got = {a["id"]: a["observed"] for a in st["attacks"]}
        for k, v in expected.items():
            self.assertEqual(got.get(k), v)
        steps = {s["id"]: s for s in st["steps"]}
        self.assertIn("intensity", steps)
        em = steps["prove_emissions"]["metrics"]
        self.assertEqual(em["public_inputs"], 339)
        self.assertEqual(em["proven_residual_kg"], em["cap_kg"])
        self.assertEqual(em["cap_kg"], em["residual_private_kg"]["carbon_agent"])
        note = steps["note"]["metrics"]
        self.assertEqual(note["kpi"], "RESIDUAL_EMISSIONS")
        self.assertEqual(note["kpi_met"], em["cap_kg"] <= note["target_residual_kg"])
        self.assertEqual(note["coupon_bps"], 500 if note["kpi_met"] else 600)
        # the target was set from weeks that ended at least one week before the window
        basis = st["note_terms"]["target_basis"]
        self.assertEqual(len(basis), 4)
        self.assertTrue(all(pd.Timestamp(b["week_utc"]) + pd.Timedelta(days=7) <= pd.Timestamp("2025-08-25")
                            for b in basis))
        # every committed plan carries the CO2 forecast and the planned shift
        commits = steps["agent_commit"]["metrics"]["commits"]
        self.assertEqual(len(commits), 7)
        self.assertTrue(all(c["early"] for c in commits))
        self.assertEqual(len(st["window"]["co2_forecast_g_per_kwh"]), 168)
        self.assertNotIn("load_kwh", st["window"])
        self.assertNotIn("procurement_load_kwh", st["window"])


if __name__ == "__main__":
    unittest.main()
