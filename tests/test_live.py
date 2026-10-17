import json
import unittest
from unittest import mock

import pandas as pd

from hourproof import live
from tests.test_carbon import _live_inputs


class LiveCarbonScoreTests(unittest.TestCase):
    """Offline: Energi Data Service is replaced by TEST-ONLY records shaped like its responses."""
    DAY = pd.Timestamp("2025-12-20")

    def _entry(self):
        plan = {"agent": "x", "carbon": {"co2_forecast_g_per_kwh": [100.0] * 24,
                                         "persistence_lag168_g_per_kwh": [90.0] * 24}}
        return {"day": f"{self.DAY:%Y-%m-%d}", "plan": json.dumps(plan)}

    def test_initial_first_then_final_without_rescoring(self):
        d = self._entry()
        ge, st, _, _ = _live_inputs(self.DAY)
        with mock.patch.object(live, "_grid_emission", return_value=(ge, st)):
            live._score_carbon(d, self.DAY)
        self.assertEqual(set(d["co2_score"]), {"Initial"})
        first = dict(d["co2_score"]["Initial"])
        ge2, st2, _, _ = _live_inputs(self.DAY, final_offset=50.0)
        with mock.patch.object(live, "_grid_emission", return_value=(ge2, st2)):
            live._score_carbon(d, self.DAY)
        self.assertEqual(set(d["co2_score"]), {"Initial", "Final"})
        self.assertEqual(d["co2_score"]["Initial"], first)  # the Initial score is never overwritten
        with mock.patch.object(live, "_grid_emission") as g:
            live._score_carbon(d, self.DAY)
            g.assert_not_called()  # complete: no more requests

    def test_plans_without_carbon_part_are_skipped(self):
        d = {"day": "2025-12-20", "plan": json.dumps({"agent": "x"})}
        with mock.patch.object(live, "_grid_emission") as g:
            live._score_carbon(d, self.DAY)
            g.assert_not_called()
        self.assertNotIn("co2_score", d)


if __name__ == "__main__":
    unittest.main()
