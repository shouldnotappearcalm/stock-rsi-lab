import unittest

from scripts.run_qlib_horizon20_pre2026 import HORIZON, LABEL, validate_dates


class QlibHorizonResearchTests(unittest.TestCase):
    def test_long_horizon_protocol_has_its_own_pre2026_cutoffs(self):
        validate_dates()
        self.assertEqual(HORIZON, 21)
        self.assertIn("Ref($close, -21)", LABEL)
        with self.assertRaises(ValueError):
            validate_dates(test_end="2026-01-02")
        with self.assertRaises(ValueError):
            validate_dates(valid_end="2024-01-02")
