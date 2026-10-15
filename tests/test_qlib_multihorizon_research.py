import unittest
import json
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

from scripts.run_qlib_multihorizon_blend_pre2026 import blend_scores


class QlibMultihorizonResearchTests(unittest.TestCase):
    @unittest.skipIf(pd is None, "optional pandas research dependency is unavailable")
    def test_equal_daily_ranks_are_scale_independent_and_reject_future(self):
        symbols = [f"SH{index:06d}" for index in range(100)]
        index = pd.MultiIndex.from_product(
            [[pd.Timestamp("2024-01-02")], symbols], names=["datetime", "instrument"]
        )
        fast = pd.Series(range(100), index=index)
        slow = pd.Series(range(99, -1, -1), index=index)
        combined, coverage = blend_scores(fast, slow * 1000)
        self.assertEqual(coverage["min_daily_shared_names"], 100)
        self.assertAlmostEqual(float(combined.score.max() - combined.score.min()), 0)
        future = slow.copy()
        future.index = pd.MultiIndex.from_product(
            [[pd.Timestamp("2026-01-05")], symbols], names=index.names
        )
        with self.assertRaises(ValueError):
            blend_scores(fast, future)

    def test_recorded_blend_has_full_shared_universe_and_no_lift(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / "experiments/qlib/multihorizon-blend-pre2026-results.json").read_text())
        self.assertEqual(result["coverage"]["min_daily_shared_names"], 500)
        self.assertEqual(result["target_status"], "FAIL")
        self.assertFalse(result["2026_market_data_accessed"])
        self.assertLess(result["blend_minus_fast_only"]["net_annualized_pct_points"], 0)
