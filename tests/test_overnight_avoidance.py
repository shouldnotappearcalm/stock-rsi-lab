import unittest
from datetime import date
from unittest.mock import patch

from stock_rsi.overnight_trend import PastOnlyPrices, formation_window, overnight_trend, weakest_decile


class OvernightAvoidanceTests(unittest.TestCase):
    def test_month_window_and_future_mutation_do_not_change_factor(self):
        self.assertEqual(formation_window("2024-01"), (date(2023, 1, 1), date(2023, 11, 30)))

        class Snapshot:
            calendar = (date(2022, 12, 28),) + tuple(date(2023, month, 28) for month in range(1, 13))
            future_scale = 1.0

            def value(self, symbol, field, day):
                day = date.fromisoformat(day)
                index = self.calendar.index(day)
                value = 100 * 1.01 ** index if field == "adjclose" else 100
                return value * (self.future_scale if day >= date(2023, 12, 1) else 1)

        snapshot = Snapshot()
        view = PastOnlyPrices(snapshot, date(2023, 11, 30))
        first = overnight_trend(view, "SH600001", "2024-01")
        snapshot.future_scale = 1000
        second = overnight_trend(PastOnlyPrices(snapshot, date(2023, 11, 30)), "SH600001", "2024-01")
        self.assertAlmostEqual(first, (1.01 ** 11 - 1) / 11)
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "future"):
            view.value("SH600001", "open", "2023-12-28")

    def test_bottom_decile_has_stable_tie_break(self):
        scores = {f"SH60{i:04d}": 0.0 for i in range(100)}
        self.assertEqual(weakest_decile(scores), tuple(sorted(scores)[:10]))

    def test_monthly_filter_demotes_only_fixed_weak_names(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        from scripts.run_qlib_ovnt_avoidance_pre2026 import apply_monthly_avoidance

        class Snapshot:
            calendar = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))

        symbols = [f"SH60{i:04d}" for i in range(100)]
        index = pd.MultiIndex.from_product(
            [pd.to_datetime(["2024-01-02", "2024-01-03"]), symbols],
            names=["datetime", "instrument"],
        )
        prediction = pd.DataFrame({"score": [0.5] * len(index)}, index=index)

        def factor(view, symbol, month):
            view.latest_read = view.as_of
            return float(symbol[-4:])

        with patch("scripts.run_qlib_ovnt_avoidance_pre2026.overnight_trend", factor):
            result, receipts = apply_monthly_avoidance(prediction, Snapshot())
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["formation_end"], "2023-11-30")
        for day in pd.to_datetime(["2024-01-02", "2024-01-03"]):
            self.assertEqual(int((result.loc[day, "score"] < 0.5).sum()), 10)
        future = prediction.copy()
        future.index = pd.MultiIndex.from_product(
            [pd.to_datetime(["2026-01-05", "2026-01-06"]), symbols], names=index.names
        )
        with self.assertRaisesRegex(ValueError, "2026"):
            apply_monthly_avoidance(future, Snapshot())
