import unittest

from scripts.run_qlib_topk_search import rank_candidates


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


if __name__ == "__main__":
    unittest.main()
