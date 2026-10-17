import json
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from hourproof import agent
from hourproof.dataset import FC_AREA_COLUMNS
from tests.synthetic import synthetic_year, with_area_forecasts


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = synthetic_year()

    def test_load_features_only_use_data_known_at_decision_time(self):
        """Leakage guard: corrupting every load value from the decision time (D-1 17:30 UTC)
        onward must not change the features for day D."""
        day = pd.Timestamp("2025-08-14")
        idx = pd.date_range(day, periods=24, freq="h")
        f1 = agent.load_features(self.df, idx)
        corrupted = self.df.copy()
        corrupted.loc[corrupted.index >= agent.decision_time(day), "load_mwh"] = 1e9
        f2 = agent.load_features(corrupted, idx)
        pd.testing.assert_frame_equal(f1, f2)

    def test_supply_features_ignore_actual_production(self):
        day = pd.Timestamp("2025-09-02")
        idx = pd.date_range(day, periods=24, freq="h")
        f1 = agent.supply_features(self.df, idx)
        corrupted = self.df.assign(wind_mwh=-1.0, clean_mwh=-1.0)
        pd.testing.assert_frame_equal(f1, agent.supply_features(corrupted, idx))

    def test_decision_time_is_before_the_day(self):
        day = pd.Timestamp("2025-03-10")
        self.assertLess(agent.decision_time(day), day)
        self.assertEqual(agent.decision_time(day), pd.Timestamp("2025-03-09 17:30"))

    def test_plan_conserves_energy_and_budget(self):
        rng = np.random.default_rng(1)
        p_load = rng.uniform(50, 150, 24)
        p_cert = rng.uniform(0, 250, 24)
        avail = rng.uniform(0, 30, 24)
        shift, buy = agent.plan_day(p_load, p_cert, avail, 40.0, agent.AgentParams())
        self.assertAlmostEqual(shift.sum(), 0.0, places=6)
        self.assertLessEqual(buy.sum(), 40.0 + 1e-9)
        self.assertTrue(np.all(buy <= avail + 1e-9))
        self.assertTrue(np.all(-np.minimum(shift, 0) <= 0.10 * p_load + 1e-9))

    def test_execution_respects_actuals(self):
        load = np.full(24, 100.0)
        shift = np.zeros(24); shift[0] = -50; shift[12] = 50   # plan wants more than the flexible 10 %
        buy = np.full(24, 5.0)
        avail = np.full(24, 2.0)
        new_load, bought = agent.execute_day(load, shift, buy, avail, agent.AgentParams())
        self.assertAlmostEqual(new_load.sum(), load.sum())
        self.assertAlmostEqual(new_load[0], 90.0)   # only 10 % could move
        self.assertTrue(np.all(bought <= 2.0))

    def test_coverage(self):
        self.assertAlmostEqual(agent.coverage([100, 100], [100, 50]), 0.75)
        self.assertAlmostEqual(agent.coverage([100, 100], [500, 0]), 0.5)  # surplus never counts

    def test_backtest_compares_at_equal_mwh(self):
        r = agent.backtest(self.df, write=False)
        c = r["coverage"]
        self.assertLessEqual(c["naive_fixed_portfolio"], c["bigger_portfolio_same_mwh"] + 1e-9)
        self.assertLessEqual(c["agent_shift_and_topup"], c["perfect_foresight_bound"] + 0.02)
        self.assertGreater(r["test_days"], 150)
        self.assertGreaterEqual(r["extra_certificate_mwh"], 0)

    def test_backtest_keeps_the_v1_output_keys(self):
        r = agent.backtest(self.df, test_from="2025-11-01", write=False)
        for k in ("agent", "params", "portfolio_share_k", "test_period", "test_days", "extra_certificate_mwh",
                  "extra_share_of_test_load", "coverage", "forecast_skill", "gain_vs_same_mwh_pp", "gain_vs_naive_pp",
                  "note"):
            self.assertIn(k, r)
        self.assertEqual(set(r["coverage"]), {"naive_fixed_portfolio", "bigger_portfolio_same_mwh", "agent_shift_only",
                                              "agent_shift_and_topup", "perfect_foresight_bound"})
        for k in ("wind_mae_raw_forecast_mwh", "wind_mae_model_mwh", "load_mae_model_mwh", "load_mae_lag168_mwh"):
            self.assertIn(k, r["forecast_skill"])


class AgentV2Tests(unittest.TestCase):
    """v2: rolling budget, residual load model + selector, area/type wind, quantiles, LP, selection."""

    @classmethod
    def setUpClass(cls):
        cls.df = with_area_forecasts(synthetic_year())

    # ---------------------------------------------------------------- leakage guards for every new feature
    def test_residual_load_features_only_use_values_at_least_48h_old(self):
        day = pd.Timestamp("2025-08-14")
        for h in (0, 7, 17, 23):
            t = day + pd.Timedelta(hours=h)
            idx = pd.DatetimeIndex([t])
            f1 = agent.residual_load_features(self.df, idx)
            corrupted = self.df.copy()
            corrupted.loc[corrupted.index > t - pd.Timedelta(hours=agent.MIN_LAG_H), "load_mwh"] = 1e9
            pd.testing.assert_frame_equal(f1, agent.residual_load_features(corrupted, idx))

    def test_residual_load_features_only_use_data_known_at_decision_time(self):
        day = pd.Timestamp("2025-08-14")
        idx = pd.date_range(day, periods=24, freq="h")
        corrupted = self.df.copy()
        corrupted.loc[corrupted.index >= agent.decision_time(day), "load_mwh"] = 1e9
        pd.testing.assert_frame_equal(agent.residual_load_features(self.df, idx),
                                      agent.residual_load_features(corrupted, idx))

    def test_holiday_flags_are_calendar_only(self):
        idx = pd.date_range("2025-12-23", periods=24 * 9, freq="h")
        f = agent.residual_load_features(self.df.assign(load_mwh=np.nan), idx)  # no load needed at all
        on = lambda s, col: bool(f.loc[f.index.normalize() == pd.Timestamp(s), col].all())  # noqa: E731
        self.assertTrue(on("2025-12-23", "pre_holiday"))
        self.assertFalse(on("2025-12-23", "holiday"))
        self.assertTrue(on("2025-12-27", "post_holiday"))
        self.assertTrue(on("2025-12-31", "holiday_last_week"))  # 24 Dec was a holiday
        self.assertTrue(on("2025-12-30", "pre_holiday"))  # 31 Dec is in the holiday list
        self.assertFalse(on("2025-12-28", "pre_holiday"))

    def test_area_supply_features_ignore_actuals_and_other_days_forecasts(self):
        day = pd.Timestamp("2025-09-02")
        idx = pd.date_range(day, periods=24, freq="h")
        f1 = agent._supply_X(self.df, idx, "area_type")
        self.assertTrue(all(c in f1.columns for c in FC_AREA_COLUMNS))
        corrupted = self.df.assign(wind_mwh=-1.0, clean_mwh=-1.0, load_mwh=-1.0)
        outside = (corrupted.index < day) | (corrupted.index > idx[-1])
        corrupted.loc[outside, ["wind_fc_da_mwh", *FC_AREA_COLUMNS]] = 1e9
        pd.testing.assert_frame_equal(f1, agent._supply_X(corrupted, idx, "area_type"))

    def test_wind_models_are_as_of(self):
        """Point and quantile wind forecasts for day D, with either feature set, do not change when actual
        wind/clean from the decision onward, or forecasts for later days, are corrupted."""
        day = pd.Timestamp("2025-06-03")
        corrupted = self.df.copy()
        corrupted.loc[corrupted.index >= agent.decision_time(day), ["wind_mwh", "clean_mwh"]] = 1e9
        corrupted.loc[corrupted.index > day + pd.Timedelta(hours=23), ["wind_fc_da_mwh", *FC_AREA_COLUMNS]] = 1e9
        for feats, q in (("total", None), ("area_type", None), ("area_type", 0.1), ("total", 0.9)):
            a = agent.Forecasts(self.df, [day]).wind(feats, q)[day]
            b = agent.Forecasts(corrupted, [day]).wind(feats, q)[day]
            np.testing.assert_array_equal(a, b, err_msg=f"{feats} q={q}")

    def test_raw_forecast_wind_is_the_published_forecast_only(self):
        day = pd.Timestamp("2025-09-02")
        f = agent.Forecasts(self.df.assign(wind_mwh=-1.0, clean_mwh=-1.0), [day])
        s = f.wind_scenarios("raw_forecast", ())[day]
        self.assertEqual(s.shape, (1, 24))
        np.testing.assert_array_equal(s[0], self.df["wind_fc_da_mwh"].loc[day: day + pd.Timedelta(hours=23)].to_numpy())
        np.testing.assert_array_equal(f.wind_point("raw_forecast", ())[day], s[0])

    def test_v2_load_forecasts_and_selector_are_as_of(self):
        day = pd.Timestamp("2025-06-01")
        T = agent.decision_time(day)
        corrupted = self.df.copy()
        corrupted.loc[corrupted.index >= T, "load_mwh"] = 1e9
        for kind in ("lag168", "residual", "selector"):
            a, b = agent.Forecasts(self.df, [day]), agent.Forecasts(corrupted, [day])
            np.testing.assert_array_equal(a.load(kind)[day], b.load(kind)[day], err_msg=kind)
        # the selector's choice uses only hours >= 48 h old at the month's first decision
        corrupted.loc[corrupted.index >= T - pd.Timedelta(hours=agent.MIN_LAG_H), "load_mwh"] = 1e9
        a, b = agent.Forecasts(self.df, [day]), agent.Forecasts(corrupted, [day])
        a.load("selector")
        b.load("selector")
        self.assertEqual(a.selector_choices, b.selector_choices)

    def test_selector_picks_last_week_when_the_model_is_worse(self):
        class Bad:
            def fit(self, X, y):
                return self

            def predict(self, X):
                return np.full(len(X), 50.0)  # a residual model that is far off

        day = pd.Timestamp("2025-06-02")
        with mock.patch.object(agent, "_model", lambda quantile=None: Bad()):
            f = agent.Forecasts(self.df, [day])
            p = f.load("selector")[day]
        ch = f.selector_choices["2025-06-01"]
        self.assertEqual(ch["choice"], "lag168")
        self.assertGreater(ch["mae_residual"], ch["mae_lag168"])
        np.testing.assert_array_equal(p, f._lag168(pd.date_range(day, periods=24, freq="h"), agent.decision_time(day)))

    # ---------------------------------------------------------------- planner
    def test_lp_plan_conserves_energy_and_respects_caps(self):
        rng = np.random.default_rng(2)
        params = agent.AgentParams()
        for _ in range(25):
            p_load = rng.uniform(50, 150, 24)
            scen = np.sort(rng.uniform(0, 250, (int(rng.integers(1, 6)), 24)), axis=0)
            avail = rng.uniform(0, 30, 24)
            cap = float(rng.uniform(0, 80))
            shift, buy = agent.plan_day_lp(p_load, scen, avail, cap, params)
            self.assertAlmostEqual(shift.sum(), 0.0, places=6)
            self.assertLessEqual(buy.sum(), cap + 1e-9)
            self.assertTrue(np.all(buy >= 0) and np.all(buy <= avail + 1e-9))
            self.assertTrue(np.all(-np.minimum(shift, 0) <= params.flex_share * p_load + 1e-6))
            self.assertTrue(np.all(np.maximum(shift, 0) <= params.flex_cap * p_load + 1e-6))

    def test_lp_is_at_least_as_good_as_greedy_on_its_own_objective(self):
        rng = np.random.default_rng(3)
        params = agent.AgentParams()
        for _ in range(25):
            p_load, cert, avail = rng.uniform(50, 150, 24), rng.uniform(0, 250, 24), rng.uniform(0, 30, 24)
            cap = float(rng.uniform(0, 80))
            matched = lambda s, b: np.minimum(p_load + s, cert + b).sum()  # noqa: E731
            g = matched(*agent.plan_day(p_load, cert, avail, cap, params))
            lp = matched(*agent.plan_day_lp(p_load, cert[None, :], avail, cap, params))
            self.assertGreaterEqual(lp, g - 0.01)

    # ---------------------------------------------------------------- budget
    def test_rolling_budget_never_exceeds_cumulative_budget(self):
        rng = np.random.default_rng(4)
        for alpha in agent.ALPHAS:
            b = agent.RollingBudget(10.0, alpha)
            for _ in range(80):
                cap = b.open_day()
                self.assertLessEqual(cap, min(alpha, agent.BALANCE_CAP_DAYS) * 10.0 + 1e-9)
                planned = float(rng.uniform(0, cap))
                rec = b.close_day(planned, planned * float(rng.uniform(0, 1)))
                self.assertLessEqual(rec["cumulative_realised"], rec["cumulative_budget"] + 1e-9)
                self.assertGreaterEqual(b.balance, -1e-9)

    def test_alpha_one_is_the_v1_daily_budget(self):
        b = agent.RollingBudget(10.0, 1.0)
        for spent in (0, 10, 3, 0, 0, 10):
            self.assertAlmostEqual(b.open_day(), 10.0)
            b.close_day(spent, spent / 2)

    def test_spend_cap_does_not_depend_on_days_that_have_not_ended(self):
        a, b = agent.RollingBudget(10.0, 3.0), agent.RollingBudget(10.0, 3.0)
        for x in (a, b):
            x.open_day()
        a.close_day(10, 10)
        b.close_day(10, 0)  # same plan, nothing could be bought: refunded only after the day is over
        self.assertEqual(a.open_day(), b.open_day())  # decision for the next day: day 0 still running
        a.close_day(0, 0)
        b.close_day(0, 0)
        self.assertGreater(b.open_day(), a.open_day())  # two days later the refund is usable

    def test_plans_do_not_depend_on_the_outcome_of_the_previous_day(self):
        days = list(pd.date_range("2025-09-01", periods=6, freq="D"))
        changed = self.df.copy()
        d_prev = days[3]
        changed.loc[d_prev: d_prev + pd.Timedelta(hours=23), "clean_mwh"] = 0.0  # nothing available that day
        cfg = agent.AgentConfig(alpha=3.0, load_model="lag168")
        k, bd = agent.portfolio_share(self.df), 8.0
        p1 = agent._simulate(self.df, days, agent.Forecasts(self.df, days), cfg, agent.AgentParams(), k, bd)["plans"]
        p2 = agent._simulate(changed, days, agent.Forecasts(changed, days), cfg, agent.AgentParams(), k, bd)["plans"]
        for i in range(5):  # up to and including the day after the changed day
            np.testing.assert_array_equal(p1[i][2], p2[i][2], err_msg=f"day {i}")

    def test_v2_backtest_compares_at_equal_mwh_and_never_overspends(self):
        cfg = agent.AgentConfig(policy="lp", alpha=3.0, load_model="selector", wind_features="area_type",
                                wind_quantiles=(0.1, 0.5, 0.9))
        r = agent.backtest(self.df, test_from="2025-10-01", write=False, config=cfg)
        c = r["coverage"]
        self.assertEqual(r["version"], "v2")
        self.assertLessEqual(c["naive_fixed_portfolio"], c["bigger_portfolio_same_mwh"] + 1e-9)
        self.assertLessEqual(c["agent_shift_and_topup"], c["perfect_foresight_bound"] + 0.02)
        self.assertLessEqual(r["budget"]["max_cumulative_overspend_mwh"], 1e-9)
        self.assertLessEqual(r["extra_certificate_mwh"], r["budget"]["budget_total_mwh"] + 1e-6)
        self.assertEqual(set(r["wind_pinball"]), {"0.1", "0.5", "0.9"})

    # ---------------------------------------------------------------- selection
    def test_select_config_never_reads_the_test_period(self):
        cands = [agent.AgentConfig(), agent.AgentConfig(alpha=3.0, load_model="lag168"),
                 agent.AgentConfig(policy="lp", alpha=5.0, load_model="lag168", wind_quantiles=(0.1, 0.5, 0.9))]
        garbage = self.df.copy()
        garbage.loc[garbage.index >= pd.Timestamp("2025-07-01"), :] = 1e9
        r1, r2 = {}, {}
        a = agent.select_config(self.df, cands, "2025-06-01", "2025-07-01", report=r1)
        b = agent.select_config(garbage, cands, "2025-06-01", "2025-07-01", report=r2)
        self.assertEqual(a, b)
        self.assertEqual(json.dumps(r1["candidates"], default=str), json.dumps(r2["candidates"], default=str))

    def test_periods(self):
        p = agent.periods(self.df)
        self.assertEqual(p["validation"], ("2025-04-01", "2025-07-01"))
        self.assertEqual(p["test"][0], "2025-07-01")


if __name__ == "__main__":
    unittest.main()
