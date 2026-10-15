import unittest

from scripts.prepare_qlib_master_stock_pre2026 import (
    END, LABEL, SEGMENTS, assert_registered_windows, canonical_stock_index,
)


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

    def test_qlib_datetime_first_index_is_canonicalized_without_losing_rows(self):
        import pandas as pd

        index = pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2024-01-02"), "SH600000"),
             (pd.Timestamp("2024-01-03"), "SH600000")],
            names=["datetime", "instrument"],
        )
        panel = pd.DataFrame({"x": [1, 2]}, index=index)
        result = canonical_stock_index(panel)
        self.assertEqual(result.index.names, ["instrument", "datetime"])
        self.assertEqual(result["x"].tolist(), [1, 2])
