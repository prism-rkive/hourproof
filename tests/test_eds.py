import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from hourproof import eds


class FakeResp:
    def __init__(self, status, recs=None, headers=None):
        self.status_code, self._recs, self.headers = status, recs or [], headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return {"records": self._recs}


class EDSTests(unittest.TestCase):
    def test_backoff_on_429_then_cache(self):
        recs = [{"HourUTC": "2025-01-01T00:00:00", "x": 1}]
        calls = []

        def get(url, params, timeout):
            calls.append(params["start"])
            return FakeResp(429, headers={"Retry-After": "0"}) if len(calls) == 1 else FakeResp(200, recs)

        with tempfile.TemporaryDirectory() as d, mock.patch.object(eds, "CACHE", Path(d)), \
                mock.patch.object(eds, "_session", mock.Mock(get=get)), mock.patch.object(eds, "PAUSE_S", 0), \
                mock.patch.object(eds.time, "sleep", lambda s: None):
            df = eds.fetch("X", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02"))
            self.assertEqual(len(df), 1)
            self.assertEqual(len(calls), 2)
            eds.fetch("X", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02"))
            self.assertEqual(len(calls), 2, "second fetch must come from the cache")

    def test_403_is_fatal_without_retry(self):
        calls = []

        def get(url, params, timeout):
            calls.append(1)
            return FakeResp(403)

        with tempfile.TemporaryDirectory() as d, mock.patch.object(eds, "CACHE", Path(d)), \
                mock.patch.object(eds, "_session", mock.Mock(get=get)), mock.patch.object(eds, "PAUSE_S", 0), \
                mock.patch.object(eds.time, "sleep", lambda s: None):
            with self.assertRaises(eds.EDSBlocked) as cm:
                eds.fetch("Z", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02"))
            self.assertEqual(len(calls), 1, "a 403 must not be retried")
            self.assertIn("energidataservice.dk/support-service", str(cm.exception))
            self.assertEqual(list(Path(d).iterdir()), [], "nothing is cached for a blocked request")

    def test_ignored_parameters_are_detected(self):
        recs = [{"HourUTC": "2026-10-14T10:00:00"}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(eds, "CACHE", Path(d)), \
                mock.patch.object(eds, "_session", mock.Mock(get=lambda *a, **k: FakeResp(200, recs))), \
                mock.patch.object(eds, "PAUSE_S", 0):
            with self.assertRaises(eds.EDSError):
                eds.fetch("Y", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02"))


if __name__ == "__main__":
    unittest.main()
