import unittest
from unittest import mock

import numpy as np
import pandas as pd

from hourproof import carbon, dataset
from hourproof.config import CARBON_CSV


def fixture_frame(seed: int = 0) -> pd.DataFrame:
    """TEST-ONLY hourly frame with the carbon dataset's columns (exercises code paths; never used for results)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", "2026-01-01", freq="h", inclusive="left")
    n = len(idx)
    E = pd.DataFrame(index=idx)
    E["wind_mwh"] = rng.uniform(200, 5000, n)
    E["co2_g_per_kwh"] = rng.uniform(5, 250, n)
    E["load_mwh"] = 190 + 10 * np.sin(idx.hour / 24 * 2 * np.pi) + rng.normal(0, 2, n)
    for c in dataset.CARBON_FC_COLUMNS:
        E[c] = rng.uniform(0, 1000, n)
    E["price_eur"] = rng.uniform(-10, 200, n)
    return E


def _live_inputs(day: pd.Timestamp, seed: int = 0, final_offset: float | None = None):
    """TEST-ONLY Energinet-shaped records for live mode: DeclarationGridEmission (Initial, optionally Final),
    ProductionConsumptionSettlement published only up to 10 days before `day`, Forecasts_Hour and DayAheadPrices."""
    rng = np.random.default_rng(seed)
    hist = pd.date_range(day - pd.Timedelta(days=40), day + pd.Timedelta(days=1), freq="h", inclusive="left")
    ge = []
    for version, off in (("Initial", 0.0), ("Final", final_offset)):
        if off is None:
            continue
        for area, base in (("DK1", 120.0), ("DK2", 60.0)):
            for i, h in enumerate(hist):
                for method, mult in (("125%", 1.0), ("200%", 1.3)):
                    ge.append({"HourUTC": h, "PriceArea": area, "Version": version, "FuelAllocationMethod": method,
                               "CO2PerkWh": mult * (base + 30 * np.sin(i / 9) + off)})
    st_hours = hist[hist < day - pd.Timedelta(days=10)]
    st = pd.DataFrame([{"HourUTC": h, "PriceArea": a, "GrossConsumptionMWh": w * (1 + 0.2 * np.sin(h.hour / 4))}
                       for h in st_hours for a, w in (("DK1", 2000.0), ("DK2", 1500.0))])
    hrs = pd.date_range(day, periods=24, freq="h")
    fc = pd.DataFrame([{"HourUTC": h, "PriceArea": a, "ForecastType": t, "ForecastDayAhead": rng.uniform(0, 1000)}
                       for h in hrs for a in ("DK1", "DK2") for t in ("Offshore Wind", "Onshore Wind", "Solar")])
    qs = pd.date_range(day, periods=96, freq="15min")
    da = pd.DataFrame([{"TimeUTC": t, "PriceArea": a, "DayAheadPriceEUR": rng.uniform(0, 150)}
                       for t in qs for a in ("DK1", "DK2")])
    return pd.DataFrame(ge), st, fc, da


class CarbonLiveTests(unittest.TestCase):
    DAY = pd.Timestamp("2025-12-20")

    def test_weights_fall_back_to_same_hour_whole_weeks_earlier(self):
        ge, st, _, _ = _live_inputs(self.DAY)
        hrs = pd.date_range(self.DAY - pd.Timedelta(days=3), periods=48, freq="h")
        val, weeks_back = carbon.live_intensity(ge, st, hrs, "Initial")
        self.assertFalse(val.isna().any())
        self.assertEqual(set(weeks_back), {2})  # settlement ends 10 days before the day -> two weeks back
        h = hrs[5]
        g = ge[(ge["Version"] == "Initial") & (ge["FuelAllocationMethod"] == "125%") & (ge["HourUTC"] == h)]
        g = g.set_index("PriceArea")["CO2PerkWh"]
        w = st[st["HourUTC"] == h - pd.Timedelta(weeks=2)].set_index("PriceArea")["GrossConsumptionMWh"]
        self.assertAlmostEqual(val[h], float((g * w).sum() / w.sum()), places=9)

    def test_no_weights_means_no_value(self):
        ge, _, _, _ = _live_inputs(self.DAY)
        val, weeks_back = carbon.live_intensity(ge, pd.DataFrame(), pd.date_range(self.DAY, periods=3, freq="h"),
                                                "Initial")
        self.assertTrue(val.isna().all())
        self.assertEqual(weeks_back, [-1, -1, -1])

    def test_live_plan_uses_initial_lags_only(self):
        E = fixture_frame()
        ge, st, fc, da = _live_inputs(self.DAY, final_offset=500.0)  # a wildly different Final must not matter
        ge_initial = ge[ge["Version"] == "Initial"]
        with mock.patch.object(carbon, "fit", wraps=carbon.fit) as fit:
            a = carbon.live_plan(self.DAY, ge, st, fc, da, E=E, cfg=carbon.FROZEN)
            b = carbon.live_plan(self.DAY, ge_initial, st, fc, da, E=E, cfg=carbon.FROZEN)
        self.assertEqual(a["co2_forecast_g_per_kwh"], b["co2_forecast_g_per_kwh"])
        self.assertEqual(len(a["co2_forecast_g_per_kwh"]), 24)
        self.assertEqual(a["lag_intensity_version"], "Initial")
        self.assertEqual(a["train_version"], "Final")
        before = fit.call_args.args[1]
        self.assertEqual(before, E.index.max() + pd.Timedelta(hours=1))  # trained on the (Final) dataset
        share = np.array(a["planned_shift_share_of_hour_load"])
        self.assertAlmostEqual(share.sum(), 0.0, places=3)
        self.assertGreaterEqual(share.min(), -0.10 - 1e-4)
        self.assertLessEqual(share.max(), 0.25 + 1e-4)
        prio = np.array(a["co2_forecast_g_per_kwh"])
        self.assertLess(prio[share > 1e-6].max(), prio[share < -1e-6].min() + 1e-6)  # only into cleaner hours

    def test_live_plan_refuses_incomplete_forecasts(self):
        ge, st, fc, da = _live_inputs(self.DAY)
        with self.assertRaises(SystemExit):
            carbon.live_plan(self.DAY, ge, st, fc.iloc[:-6], da, E=fixture_frame(), cfg=carbon.FROZEN)
        with self.assertRaises(SystemExit):
            carbon.live_plan(self.DAY, ge, st, fc, da.iloc[:-8], E=fixture_frame(), cfg=carbon.FROZEN)

    def test_score_initial_now_final_later(self):
        plan = {"co2_forecast_g_per_kwh": [100.0] * 24, "persistence_lag168_g_per_kwh": [90.0] * 24}
        ge, st, _, _ = _live_inputs(self.DAY)
        st_now = st  # settlement for the day itself is not published yet
        sc = carbon.live_score(plan, self.DAY, ge, st_now)
        self.assertEqual(set(sc), {"Initial"})
        self.assertIn("weeks earlier", sc["Initial"]["weights"])
        actual = np.array(sc["Initial"]["actual_g_per_kwh"])
        self.assertAlmostEqual(sc["Initial"]["mae_model_g_per_kwh"], float(np.mean(np.abs(100 - actual))), places=1)
        ge2, st2, _, _ = _live_inputs(self.DAY, final_offset=5.0)
        sc2 = carbon.live_score(plan, self.DAY, ge2, st2)
        self.assertEqual(set(sc2), {"Initial", "Final"})


class CarbonZKInputTests(unittest.TestCase):
    def test_intensity_is_rounded_and_clipped(self):
        self.assertEqual(carbon.intensity_g([12.49, 12.5, 13.5, -0.4, 0.0]), [12, 12, 14, 0, 0])

    def test_zk_week_matches_circuit_arithmetic(self):
        from hourproof import zk
        E = fixture_frame()
        wk = carbon.zk_week(E, pd.Timestamp("2025-08-12"))
        self.assertEqual(wk["threshold_bps"], zk.max_bps(wk["load_kwh"], wk["cert_kwh"]))
        self.assertEqual(wk["cap_kg"], zk.min_cap_kg(wk["load_kwh"], wk["cert_kwh"], wk["intensity_g_per_kwh"]))
        self.assertEqual(wk["cert_kwh"], [c * 1000 for c in wk["cert_mwh"]])
        with self.assertRaises(ValueError):
            carbon.zk_week(E, pd.Timestamp("2025-12-28"))  # runs past the end of the data


class CarbonPolicyTests(unittest.TestCase):
    def test_plan_conserves_energy_and_respects_limits(self):
        rng = np.random.default_rng(3)
        load_hat = rng.uniform(150, 220, 24)
        prio = rng.uniform(5, 250, 24)
        shift = carbon.plan_shift(load_hat, prio)
        self.assertAlmostEqual(shift.sum(), 0.0, places=6)
        self.assertTrue(np.all(-np.minimum(shift, 0) <= 0.10 * load_hat + 1e-9))   # flexible share
        self.assertTrue(np.all(np.maximum(shift, 0) <= 0.25 * load_hat + 1e-9))    # no hour above +25 %
        # load only ever moves to a strictly cleaner hour
        self.assertLess(prio[shift > 1e-9].max(), prio[shift < -1e-9].min() + 1e-9)

    def test_flat_priority_moves_nothing(self):
        self.assertEqual(np.abs(carbon.plan_shift(np.full(24, 200.0), np.full(24, 50.0))).sum(), 0.0)

    def test_execution_uses_actual_flexible_load(self):
        load = np.full(24, 100.0)
        shift = np.zeros(24)
        shift[0], shift[5] = -40.0, 40.0   # plan wants more than the flexible 10 % of ACTUAL load
        new = carbon.execute(load, shift)
        self.assertAlmostEqual(new.sum(), load.sum())
        self.assertAlmostEqual(new[0], 90.0)
        self.assertAlmostEqual(new[5], 110.0)

    def test_metrics_use_hourly_grid_average_for_unmatched(self):
        idx = pd.date_range("2025-07-01", periods=2, freq="h")
        D = pd.DataFrame({"co2_g_per_kwh": [100.0, 10.0], "base": [50.0, 200.0]}, index=idx)
        m = carbon.metrics(pd.Series([100.0, 100.0], index=idx), D)
        self.assertAlmostEqual(m["emissions_t"], (100 * 100 + 100 * 10) / 1000)
        self.assertAlmostEqual(m["residual_unmatched_t"], 50 * 100 / 1000)   # surplus never offsets another hour
        self.assertAlmostEqual(m["coverage"], 150 / 200)


class CarbonDataTests(unittest.TestCase):
    def test_price_splices_elspot_then_day_ahead_hourly_mean(self):
        sp = pd.DataFrame({"HourUTC": ["2025-09-30T21:00:00"] * 2 + ["2025-10-01T00:00:00"] * 2,
                           "PriceArea": ["DK1", "DK2"] * 2, "SpotPriceEUR": [10.0, 20.0, 999.0, 999.0]})
        q = pd.date_range("2025-09-30 22:00", periods=8, freq="15min")
        da = pd.DataFrame({"TimeUTC": [str(t) for t in q for _ in (0, 1)], "PriceArea": ["DK1", "DK2"] * 8,
                           "DayAheadPriceEUR": [float(i) for i in range(16)]})
        p = dataset.hourly_price(sp, da)
        self.assertEqual(p[pd.Timestamp("2025-09-30 21:00")], 15.0)                 # DK1/DK2 mean
        self.assertEqual(p[pd.Timestamp("2025-09-30 22:00")], np.mean(range(8)))    # 4 quarter-hours x 2 areas
        self.assertEqual(p[pd.Timestamp("2025-09-30 23:00")], np.mean(range(8, 16)))
        self.assertNotIn(999.0, p.to_numpy())   # Elspot is not used from the switch date on

    def test_intensity_is_consumption_weighted(self):
        ge = pd.DataFrame({"HourUTC": ["2025-01-01T00:00:00"] * 4, "PriceArea": ["DK1", "DK2", "DK1", "DK2"],
                           "Version": ["Final"] * 4, "FuelAllocationMethod": ["125%", "125%", "200%", "200%"],
                           "CO2PerkWh": [100.0, 40.0, 1.0, 1.0]})
        cons = pd.DataFrame({"DK1": [3.0], "DK2": [1.0]}, index=pd.Index(["2025-01-01T00:00:00"], name="HourUTC"))
        self.assertEqual(dataset.grid_intensity(ge, cons).iloc[0], (100 * 3 + 40 * 1) / 4)


class CarbonForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = fixture_frame()

    def test_features_only_use_intensity_known_at_decision_time(self):
        """Leakage guard: corrupting every intensity from D-1 17:30 UTC onward leaves day D's features unchanged."""
        day = pd.Timestamp("2025-09-10")
        idx = pd.date_range(day, periods=24, freq="h")
        f1 = carbon.co2_features(self.E, idx, True)
        bad = self.E.copy()
        bad.loc[bad.index >= day - pd.Timedelta(hours=6.5), "co2_g_per_kwh"] = 1e9
        pd.testing.assert_frame_equal(f1, carbon.co2_features(bad, idx, True))

    def test_walk_forward_trains_only_before_each_month(self):
        """Corrupting every intensity from M - 6.5 h on must not change month M's model, so the first day's
        predictions are identical (later days legitimately use lag >= 48 h values from inside the month)."""
        M = pd.Timestamp("2025-03-01")
        cfg = carbon.FROZEN | {"model": carbon.FROZEN["model"] | {"max_iter": 20}}
        p1 = carbon.walk_forward(self.E, M, M + pd.offsets.MonthBegin(1), True, cfg)
        bad = self.E.copy()
        bad.loc[bad.index >= M - pd.Timedelta(hours=6.5), "co2_g_per_kwh"] = 1e9
        p2 = carbon.walk_forward(bad, M, M + pd.offsets.MonthBegin(1), True, cfg)
        pd.testing.assert_series_equal(p1.iloc[:24], p2.iloc[:24])
        X = carbon.co2_features(self.E, p1.index, True)
        np.testing.assert_array_equal(carbon.fit(self.E, M - pd.Timedelta(hours=6.5), cfg).predict(X),
                                      carbon.fit(bad, M - pd.Timedelta(hours=6.5), cfg).predict(X))

    def test_bootstrap_is_reproducible(self):
        idx = pd.date_range("2025-07-01", periods=24 * 28, freq="h")
        D = pd.DataFrame({"co2_g_per_kwh": self.E["co2_g_per_kwh"].iloc[:len(idx)].to_numpy()}, index=idx)
        loads = {s: pd.Series(np.full(len(idx), 100.0 - i), index=idx) for i, s in enumerate(carbon.STRATEGIES)}
        a = carbon.block_bootstrap(D, loads, [("carbon_model", "shift_for_mwh")], resamples=200)
        b = carbon.block_bootstrap(D, loads, [("carbon_model", "shift_for_mwh")], resamples=200)
        self.assertEqual(a, b)
        self.assertEqual(a["blocks"], 4)


# The kill test's TEST numbers (Jul-Dec 2025), as frozen in the brief.
TABLE = {
    "mae": {"model": 20.28, "lag168": 38.36, "lag48": 41.41},
    "emissions_t": {"no_shift": 48840.2, "shift_for_mwh": 47889.1, "carbon_persist": 48546.5,
                    "carbon_model": 47631.7, "carbon_perfect": 46856.5},
    "coverage_pct": {"no_shift": 70.45, "shift_for_mwh": 71.47, "carbon_persist": 70.03,
                     "carbon_model": 71.36, "carbon_perfect": 71.37},
}


@unittest.skipUnless(CARBON_CSV.exists(), "real carbon dataset not imported (python -m hourproof data import-carbon hp_ai)")
class CarbonRegression(unittest.TestCase):
    """Reproduce the kill test on real data with the frozen choices: every number within 0.5 % of the table."""

    def test_reproduces_killtest_within_half_a_percent(self):
        E, meta = dataset.load_carbon()
        self.assertFalse(meta["synthetic"])
        r = carbon.backtest(E, write=False, cfg=carbon.FROZEN)
        got = {"mae": r["forecast"]["test_mae_g_per_kwh"],
               "emissions_t": {s: v["emissions_t"] for s, v in r["strategies"].items()},
               "coverage_pct": {s: 100 * v["coverage"] for s, v in r["strategies"].items()}}
        for group, ref in TABLE.items():
            for k, v in ref.items():
                with self.subTest(metric=f"{group}.{k}"):
                    self.assertLess(abs(got[group][k] / v - 1), 0.005, f"{group}.{k}: {got[group][k]} vs {v}")
        # the frozen choice still wins on validation (reported, not re-made)
        val = r["forecast"]["validation_mae_rerun"]
        self.assertLess(val["use_price_true"], val["use_price_false"])

    def test_zk_week_reproduces_killtest_k4(self):
        """The emissions proof's integer inputs for the kill test's week: coverage >= 44.76 %, residual <= 1,842.7 t."""
        E, _ = dataset.load_carbon()
        wk = carbon.zk_week(E, carbon.K4_WEEK)
        self.assertEqual(wk["threshold_bps"], carbon.K4_REFERENCE["threshold_bps"])
        self.assertEqual(round(wk["cap_kg"] / 1000, 1), carbon.K4_REFERENCE["residual_t"])
        self.assertEqual(len(wk["intensity_g_per_kwh"]), 168)
        self.assertTrue(all(0 <= g <= 2000 for g in wk["intensity_g_per_kwh"]))  # the oracle's bound


if __name__ == "__main__":
    unittest.main()
