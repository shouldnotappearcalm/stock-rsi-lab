import unittest

from scripts.run_qlib_tra_pre2026 import FEATURES, first_pass_score, validate_window


class QlibTraResearchTests(unittest.TestCase):
    def test_purged_development_windows_and_fixed_feature_count(self):
        validate_window()
        self.assertEqual(len(FEATURES), 20)
        with self.assertRaises(ValueError):
            validate_window(test_end="2026-01-05")
        with self.assertRaises(ValueError):
            validate_window(train_end="2022-01-04")

    def test_first_pass_extracts_score_without_reusing_label_memory(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        index = pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2024-01-02"), "SH600000")], names=["datetime", "instrument"]
        )
        first = pd.DataFrame({"score": [0.1], "label": [0.9], "score_0": [0.2]}, index=index)
        self.assertEqual(first_pass_score(first).columns.tolist(), ["score"])
        self.assertEqual(first_pass_score(first).iloc[0, 0], 0.1)
        future = first.copy()
        future.index = pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2026-01-05"), "SH600000")], names=index.names
        )
        with self.assertRaises(ValueError):
            first_pass_score(future)
