import unittest
import json
from pathlib import Path

from scripts.run_qlib_rolling20_pre2026 import LABEL_LOOKAHEAD, STEP, windows


class QlibRollingResearchTests(unittest.TestCase):
    def test_windows_purge_labels_and_cover_each_development_session_once(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        dates = pd.bdate_range("2016-01-04", "2025-12-31")
        receipts = list(windows(dates))
        self.assertEqual(LABEL_LOOKAHEAD, 21)
        self.assertEqual(STEP, 20)
        self.assertGreater(len(receipts), 20)
        self.assertEqual(receipts[0]["test"][0], "2024-01-02")
        self.assertEqual(receipts[-1]["test"][1], "2025-11-28")
        for receipt in receipts:
            self.assertLess(receipt["train"][1], receipt["valid"][0])
            self.assertLess(receipt["valid_label_matures"], receipt["test"][0])
            self.assertLess(receipt["test_label_matures"], "2026-01-01")
        for earlier, later in zip(receipts, receipts[1:]):
            self.assertEqual(
                dates[dates.get_loc(earlier["test"][1]) + 1].strftime("%Y-%m-%d"),
                later["test"][0],
            )

    def test_recorded_run_consumed_all_windows_and_failed_target(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / "experiments/qlib/rolling20-pre2026-results.json").read_text())
        self.assertEqual(result["fit_count"], len(result["windows"]))
        self.assertEqual(result["fit_count"], 24)
        self.assertFalse(result["2026_market_data_accessed"])
        self.assertEqual(result["target_status"], "FAIL")
        self.assertLess(result["comparison_to_fixed_horizon20"]["net_annualized_pct_points"], 0)
