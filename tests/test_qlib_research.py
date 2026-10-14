import json
import unittest
from pathlib import Path

from scripts.run_qlib_topk_search import rank_candidates
from scripts.run_qlib_enhanced_search import (
    CANDIDATES as ENHANCED_CANDIDATES,
    rank_candidates as rank_enhanced_candidates,
    validate_development_dates,
)


class QlibResearchTests(unittest.TestCase):
    def test_rank_prefers_worst_year_before_peak_or_low_cost(self):
        unstable = {
            "topk": 30, "n_drop": 3, "net_annualized_pct": 35.0, "cost_pct_initial": 1.0,
            "2024_return_pct": 2.0, "2025_return_pct": 70.0,
        }
        stable = {
            "topk": 100, "n_drop": 2, "net_annualized_pct": 27.0, "cost_pct_initial": 3.0,
            "2024_return_pct": 11.0, "2025_return_pct": 40.0,
        }
        self.assertEqual(rank_candidates([unstable, stable])[0], stable)

    def test_rank_rejects_nonfinite_or_incomplete_results(self):
        with self.assertRaises(ValueError):
            rank_candidates([{"topk": 10}])
        row = {
            "topk": 10, "n_drop": 1, "net_annualized_pct": float("inf"),
            "cost_pct_initial": 1.0, "2024_return_pct": 1.0, "2025_return_pct": 1.0,
        }
        with self.assertRaises(ValueError):
            rank_candidates([row])

    def test_enhanced_search_budget_and_gate_are_fixed(self):
        self.assertEqual(len(ENHANCED_CANDIDATES), 6)
        below_target = {
            "net_annualized_pct": 19.9, "average_exposure_pct": 99.0,
            "max_drawdown_pct": -5.0, "turnover_x_initial": 1.0,
            "2024_return_pct": 30.0, "2025_return_pct": 30.0,
        }
        unstable = {
            "net_annualized_pct": 40.0, "average_exposure_pct": 99.0,
            "max_drawdown_pct": -15.0, "turnover_x_initial": 10.0,
            "2024_return_pct": 5.0, "2025_return_pct": 80.0,
        }
        stable = {
            "net_annualized_pct": 25.0, "average_exposure_pct": 98.0,
            "max_drawdown_pct": -20.0, "turnover_x_initial": 20.0,
            "2024_return_pct": 20.0, "2025_return_pct": 30.0,
        }
        self.assertEqual(rank_enhanced_candidates([below_target, unstable, stable])[0], stable)
        self.assertNotIn(below_target, rank_enhanced_candidates([below_target, stable]))

    def test_enhanced_search_cannot_cross_2026_boundary(self):
        validate_development_dates("2024-01-02", "2025-12-30", "2025-12-30")
        for args in (
            ("2024-01-02", "2026-01-05", "2026-01-05"),
            ("2024-01-02", "2025-12-30", "2026-01-01"),
            ("2025-01-02", "2024-12-30", "2025-12-30"),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_development_dates(*args)

    def test_recorded_enhanced_result_exhausts_budget_without_2026(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / "experiments/qlib/enhanced-indexing-pre2026-results.json").read_text())
        self.assertFalse(result["data_contract"]["2026_accessed"])
        self.assertLess(result["data_contract"]["prediction_max_date"], "2026-01-01")
        self.assertEqual(len(result["search"]["candidates"]), result["search"]["candidate_budget"])
        self.assertEqual(sum(row["status"] == "FAILED_CONSTRAINTS"
                             for row in result["search"]["candidates"]), 1)
        winner = result["retained_development_candidate"]
        self.assertEqual(winner["optimizer_audit"]["constraint_relaxations"], 0)
        self.assertLessEqual(winner["optimizer_audit"]["max_constraint_violation"], 1e-4)
        self.assertGreaterEqual(winner["net_annualized_pct"], 20)
        self.assertGreaterEqual(winner["average_exposure_pct"], 95)
        self.assertGreaterEqual(min(winner["2024_return_pct"], winner["2025_return_pct"]), 20)


if __name__ == "__main__":
    unittest.main()
