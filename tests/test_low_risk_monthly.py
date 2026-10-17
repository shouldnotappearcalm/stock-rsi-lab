import math
import unittest
from datetime import date

from stock_rsi.low_risk_monthly import complete_month_ends, lowest_decile, monthly_volatility
from stock_rsi.prior_close_orders import AsOfPrices, plan_prior_close_orders


class LowRiskMonthlyTests(unittest.TestCase):
    def test_month_end_uses_explicit_sessions_and_rejects_partial_month(self):
        sessions = tuple(date.fromisoformat(day) for day in (
            "2023-10-30", "2023-10-31", "2023-11-29", "2023-11-30",
            "2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"))
        self.assertEqual(complete_month_ends(sessions, date(2023, 12, 29), count=3),
                         (date(2023, 10, 31), date(2023, 11, 30), date(2023, 12, 29)))
        with self.assertRaisesRegex(ValueError, "complete month"):
            complete_month_ends(sessions, date(2024, 1, 2), count=3)

    def test_volatility_requires_all_months_and_never_reads_after_formation(self):
        days = tuple(date.fromisoformat(day) for day in ("2023-10-31", "2023-11-30", "2023-12-29"))
        class Prices:
            def value(self, symbol, field, day):
                return {"2023-10-31":100., "2023-11-30":110., "2023-12-29":99.}.get(day)
        view = AsOfPrices(Prices(), days[-1])
        self.assertAlmostEqual(monthly_volatility(view, "A", days), math.sqrt(0.02 * 12))
        self.assertEqual(view.latest_read, days[-1])
        self.assertIsNone(monthly_volatility(view, "A", (date(2023, 9, 28),) + days))
        with self.assertRaisesRegex(ValueError, "future"):
            view.value("A", "close", "2024-01-02")
        self.assertEqual(lowest_decile({f"S{i:02d}":1. for i in range(20)}), ("S00", "S01"))

    def test_order_quantities_use_prior_closes_and_sell_before_buy(self):
        class Prices:
            next_open = 20.
            def value(self, symbol, field, day):
                if day != "2023-12-29":
                    raise AssertionError("future decision-facing price read")
                return 10. if field == "close" else 1.
        source = Prices()
        view = AsOfPrices(source, date(2023, 12, 29))
        first = plan_prior_close_orders(100000., {"A":1000.}, {"B":0.95}, view)
        self.assertEqual([(row["side"], row["instrument"], row["normalized_units"]) for row in first],
                         [("SELL", "A", 1000.), ("BUY", "B", 9500.)])
        source.next_open = 1000.
        self.assertEqual(first, plan_prior_close_orders(100000., {"A":1000.}, {"B":0.95}, view))
        with self.assertRaisesRegex(ValueError, "weights"):
            plan_prior_close_orders(100000., {}, {"B":1.1}, view)

    def test_missing_visible_quote_cannot_size_an_order(self):
        class Prices:
            def value(self, symbol, field, day):
                return None
        with self.assertRaisesRegex(ValueError, "visible"):
            plan_prior_close_orders(100000., {}, {"B":0.95}, AsOfPrices(Prices(), date(2023, 12, 29)))
