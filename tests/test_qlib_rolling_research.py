import unittest

import pandas as pd

from scripts.run_qlib_rolling20_pre2026 import LABEL_LOOKAHEAD, STEP, windows


class QlibRollingResearchTests(unittest.TestCase):
    def test_windows_purge_labels_and_cover_each_development_session_once(self):
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
