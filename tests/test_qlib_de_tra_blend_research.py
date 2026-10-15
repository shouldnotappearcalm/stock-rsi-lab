import unittest

from scripts.run_qlib_de_tra_blend_pre2026 import equal_rank_blend


class QlibDeTraBlendResearchTests(unittest.TestCase):
    def test_rank_blend_rejects_future_and_is_scale_invariant(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        dates = pd.bdate_range("2024-01-02", periods=482)
        index = pd.MultiIndex.from_product(
            [dates, [f"SH60{i:04d}" for i in range(100)]], names=["datetime", "instrument"]
        )
        fast = pd.DataFrame({"score": list(range(100)) * len(dates)}, index=index)
        tra = pd.DataFrame({"score": list(reversed(range(100))) * len(dates)}, index=index)
        base, coverage = equal_rank_blend(fast, tra)
        scaled, _ = equal_rank_blend(fast * 1000, tra * 0.01)
        pd.testing.assert_frame_equal(base, scaled)
        self.assertEqual(coverage["min_daily_shared_names"], 100)
        future = tra.copy()
        future.loc[(pd.Timestamp("2026-01-05"), "SH600000"), "score"] = 1.0
        with self.assertRaisesRegex(ValueError, "post-2025"):
            equal_rank_blend(fast, future)
