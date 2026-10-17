import unittest
from datetime import date

from stock_rsi.roll1_continuation import continuation_windows, normalize_frozen_features
from stock_rsi.rolling_daily import rolling_windows


class RollingContinuationTests(unittest.TestCase):
    def test_continuation_reuses_unfinished_block_without_new_year_reset(self):
        days = tuple(date.fromisoformat(day) for day in (
            "2025-12-22", "2025-12-23", "2025-12-24", "2025-12-25", "2025-12-26",
            "2025-12-29", "2025-12-30", "2025-12-31", "2026-01-05", "2026-01-06"))
        prior = list(rolling_windows(days[:8], "2025-12-29", "2025-12-31", history=3, step=4))
        extended = continuation_windows(days, prior, history=3, step=4)
        self.assertEqual(extended[0]["number"], 1)
        self.assertTrue(extended[0]["reuse_existing"])
        self.assertEqual(extended[0]["prediction_start"], "2026-01-05")
        self.assertEqual(extended[0]["fit_asof"], "2025-12-26")
        self.assertEqual(extended[1]["prediction_start"], "2026-01-06")
        self.assertFalse(extended[1]["reuse_existing"])
        prior[0]["fit_asof"] = "2025-12-25"
        with self.assertRaisesRegex(ValueError, "cadence"):
            continuation_windows(days, prior, history=3, step=4)

    def test_normalization_uses_saved_state_and_preserves_input(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        raw = pd.DataFrame({"a": [12., 999.], "b": [float("nan"), 4.]}, dtype="float32")
        state = {"columns": ["a", "b"], "center": [10., 2.], "scale": [2., 1.],
                 "clip": [-3, 3], "fillna": 0, "fit_end": "2021-12-29"}
        result = normalize_frozen_features(raw, state)
        self.assertEqual(result.to_numpy().tolist(), [[1., 0.], [3., 2.]])
        self.assertEqual(raw.iloc[0, 0], 12.)
        state["fit_end"] = "2026-01-01"
        with self.assertRaisesRegex(ValueError, "normalizer"):
            normalize_frozen_features(raw, state)
