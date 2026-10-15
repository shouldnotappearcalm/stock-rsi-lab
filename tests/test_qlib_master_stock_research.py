import unittest

from scripts.prepare_qlib_master_stock_pre2026 import END, LABEL, SEGMENTS, assert_registered_windows


class QlibMasterStockResearchTests(unittest.TestCase):
    def test_registered_five_session_labels_mature_inside_each_split(self):
        import pandas as pd

        def calendar(start, end):
            return pd.bdate_range(start, end)

        # This synthetic business-day calendar has the same dates for the
        # registered split tails; the live preparation checks Qlib's calendar.
        assert_registered_windows(calendar)
        self.assertEqual(END, "2025-12-23")
        self.assertEqual(LABEL, "Ref($close,-5)/Ref($close,-1)-1")
        self.assertTrue(all(maturity[:4] == end[:4] for _, end, maturity in SEGMENTS.values()))

    def test_rejects_calendar_without_matured_label(self):
        with self.assertRaisesRegex(ValueError, "maturity mismatch"):
            assert_registered_windows(lambda start, end: [start, end])
