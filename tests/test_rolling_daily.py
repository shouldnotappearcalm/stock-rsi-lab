import unittest
from datetime import date

from stock_rsi.rolling_daily import MatureDailyLabels, rolling_windows


class RollingDailyTests(unittest.TestCase):
    def test_windows_purge_unmatured_labels_and_are_nonoverlapping(self):
        dates = tuple(date(2024, 1, day) for day in (2, 3, 4, 5, 8, 9, 10, 11, 12))
        rows = list(rolling_windows(dates, "2024-01-10", "2024-01-12", history=3, step=2))
        self.assertEqual(rows[0]["train_end"], "2024-01-05")
        self.assertEqual(rows[0]["latest_label_maturity"], "2024-01-09")
        self.assertEqual(rows[0]["fit_asof"], "2024-01-09")
        self.assertEqual(rows[0]["prediction_end"], "2024-01-11")
        self.assertEqual(rows[1]["prediction_start"], "2024-01-12")

    def test_label_cache_cannot_bypass_maturity(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")

        class Snapshot:
            calls = []

            def value(self, code, field, day):
                self.calls.append(day)
                return 100.0 if day == "2024-01-05" else (110.0 if code == "A" else 90.0)

        dates = tuple(date(2024, 1, day) for day in (2, 3, 4, 5, 8))
        snapshot = Snapshot()
        labels = MatureDailyLabels(snapshot, dates)
        index = pd.MultiIndex.from_product([[pd.Timestamp("2024-01-04")], ["A", "B"]],
                                          names=["datetime", "instrument"])
        with self.assertRaisesRegex(ValueError, "not matured"):
            labels.targets(index, "2024-01-05")
        self.assertEqual(snapshot.calls, [])
        target = labels.targets(index, "2024-01-08")
        self.assertGreater(target.iloc[0], target.iloc[1])
        with self.assertRaisesRegex(ValueError, "not matured"):
            labels.targets(index, "2024-01-05")
