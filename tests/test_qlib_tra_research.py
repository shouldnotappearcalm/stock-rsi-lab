import unittest

from scripts.run_qlib_tra_pre2026 import FEATURES, validate_window


class QlibTraResearchTests(unittest.TestCase):
    def test_purged_development_windows_and_fixed_feature_count(self):
        validate_window()
        self.assertEqual(len(FEATURES), 20)
        with self.assertRaises(ValueError):
            validate_window(test_end="2026-01-05")
        with self.assertRaises(ValueError):
            validate_window(train_end="2022-01-04")
