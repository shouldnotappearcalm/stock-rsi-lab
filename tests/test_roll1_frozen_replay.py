import unittest

from scripts.run_qlib_roll1_frozen_2026 import calendar_year_metrics, verify_development_selection


class RollingFrozenReplayTests(unittest.TestCase):
    def test_selection_rejects_control_or_changed_winner_before_loading_2026(self):
        def row(first):
            return {"2024_return_pct": first, "2025_return_pct": 20,
                    "average_exposure_pct": 95, "net_annualized_pct": 15, "cost_pct_initial": 2}
        summary = {"status": "PRE2026_DEVELOPMENT_ONLY", "account_end": "2025-12-31",
                   "development_status": "NEW_LEAD_ONLY", "candidate_budget": 3,
                   "2026_market_values_queried": False, "selected": "rolling_ridge",
                   "ranked_eligible": ["rolling_ridge", "de_control"],
                   "results": {"rolling_ridge": row(12), "de_control": row(10)}}
        self.assertEqual(verify_development_selection(summary), "rolling_ridge")
        summary["selected"] = "de_control"
        with self.assertRaisesRegex(ValueError, "selected"):
            verify_development_selection(summary)
        summary["selected"] = "rolling_ridge"
        summary["2026_market_values_queried"] = True
        with self.assertRaisesRegex(ValueError, "pre-2026"):
            verify_development_selection(summary)

    def test_calendar_metrics_use_previous_year_equity_and_cost_baseline(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        report = pd.DataFrame({"account": [200., 220., 198.], "value": [190., 209., 188.1],
                               "return": [0., .11, -.09], "cost": [0., .01, .01],
                               "bench": [0., .05, -.05], "total_cost": [10., 12., 14.2],
                               "total_turnover": [100., 120., 142.]},
                              index=pd.to_datetime(["2025-12-31", "2026-01-05", "2026-01-06"]))
        result = calendar_year_metrics(report, "2026")
        self.assertAlmostEqual(result["net_compound_return_pct"], -1.)
        self.assertAlmostEqual(result["cost_pct_starting_equity"], 2.1)
        self.assertAlmostEqual(result["average_exposure_pct"], 95.)
        self.assertAlmostEqual(result["max_drawdown_pct"], -10.)
        report.iloc[-1, report.columns.get_loc("account")] += 1
        with self.assertRaisesRegex(ValueError, "equity"):
            calendar_year_metrics(report, "2026")
