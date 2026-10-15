import unittest

from scripts.prepare_qlib_master_market_pre2026 import index_fields, normalize_training_only


class QlibMasterMarketResearchTests(unittest.TestCase):
    def test_market_features_use_only_current_and_past_prices(self):
        fields = index_fields()
        self.assertEqual(len(fields), 21)
        self.assertTrue(all("Ref($close,1)" in field or "Ref(" not in field for field in fields))
        self.assertTrue(all("$amount" in field or "$close" in field for field in fields))

    def test_normalizer_is_fit_only_on_training_dates(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        dates = pd.to_datetime(["2016-01-04", "2016-01-05", "2016-01-06", "2024-01-02"])
        raw = pd.DataFrame([[1.0] * 63, [2.0] * 63, [3.0] * 63, [4.0] * 63],
                           index=pd.Index(dates, name="datetime"), columns=[str(i) for i in range(63)])
        _, first = normalize_training_only(raw, fit_end="2016-01-06")
        raw.iloc[-1] = 1_000_000.0
        normalized, second = normalize_training_only(raw, fit_end="2016-01-06")
        self.assertEqual(first, second)
        self.assertEqual(normalized.iloc[-1, 0], 3.0)
        future = raw.copy()
        future.loc[pd.Timestamp("2026-01-05")] = [0.0] * 63
        with self.assertRaisesRegex(ValueError, "post-2025"):
            normalize_training_only(future, fit_end="2016-01-06")
