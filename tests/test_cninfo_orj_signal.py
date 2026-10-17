import unittest
from datetime import date

from scripts.run_cninfo_orj_signal_pre2026 import (
    development_lead_status, next_sessions, summarize_horizon,
)


class CninfoOrjSignalTests(unittest.TestCase):
    def test_announcement_signal_and_entry_are_separate_sessions(self):
        calendar = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
        self.assertEqual(next_sessions(calendar, "2024-01-02"),
                         ("2024-01-03", "2024-01-04", 2))
        self.assertIsNone(next_sessions((date(2025, 12, 31), date(2026, 1, 5)),
                                        "2025-12-31"))

    def test_fixed_forward_excess_keeps_positive_and_nonpositive_separate(self):
        class Snapshot:
            calendar = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4),
                        date(2024, 1, 5))

            def value(self, code, field, day):
                prices = {"SH600001": {"2024-01-03": 100, "2024-01-04": 110},
                          "SZ000001": {"2024-01-03": 100, "2024-01-04": 90},
                          "SH000905": {"2024-01-03": 100, "2024-01-04": 100}}
                return prices[code][day]

        events = [
            {"code": "SH600001", "entry_day": "2024-01-03", "entry_index": 1,
             "signal_day": "2024-01-02", "overnight_response": 0.01},
            {"code": "SZ000001", "entry_day": "2024-01-03", "entry_index": 1,
             "signal_day": "2024-01-02", "overnight_response": -0.01},
        ]
        result = summarize_horizon(events, Snapshot(), 1)
        self.assertEqual(result["positive"]["events"], 1)
        self.assertAlmostEqual(result["positive"]["mean_cost_adjusted_excess_pct"], 9.8)
        self.assertAlmostEqual(result["nonpositive"]["mean_cost_adjusted_excess_pct"], -10.2)
        self.assertAlmostEqual(result["positive_minus_nonpositive_excess_points"], 20.0)

    def test_lead_gate_requires_coverage_and_both_horizons(self):
        good = {"positive": {"events": 120, "distinct_signal_days": 50,
                             "date_balanced_cost_adjusted_excess_pct": 1.0},
                "positive_minus_nonpositive_excess_points": 1.0}
        self.assertEqual(development_lead_status({"60": good, "20": good}),
                         "DEVELOPMENT_LEAD_ONLY_NO_PORTFOLIO_CLAIM")
        weak = {**good, "positive_minus_nonpositive_excess_points": -1.0}
        self.assertEqual(development_lead_status({"60": weak, "20": good}),
                         "REJECTED_DEVELOPMENT_SIGNAL")


if __name__ == "__main__":
    unittest.main()
