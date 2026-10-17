import unittest

from scripts.capture_baostock_adjustments_pre2026 import (
    REQUIRED_FIELDS, baostock_code, validate_rows,
)


class BaoStockAdjustmentCaptureTests(unittest.TestCase):
    def test_symbol_and_pre2026_date_boundary(self):
        self.assertEqual(baostock_code("SH600166"), "sh.600166")
        valid = ["sh.600166", "2024-06-26", "1", "1", "1"]
        self.assertEqual(validate_rows("SH600166", REQUIRED_FIELDS, [valid])[0]["dividOperateDate"],
                         "2024-06-26")
        with self.assertRaisesRegex(ValueError, "pre-2026"):
            validate_rows("SH600166", REQUIRED_FIELDS,
                          [["sh.600166", "2026-01-05", "1", "1", "1"]])
        with self.assertRaisesRegex(ValueError, "wrong security"):
            validate_rows("SH600166", REQUIRED_FIELDS,
                          [["sz.000783", "2024-06-26", "1", "1", "1"]])

    def test_duplicate_adjustment_rows_are_rejected(self):
        row = ["sz.000783", "2024-06-26", "1", "1", "1"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_rows("SZ000783", REQUIRED_FIELDS, [row, row])


if __name__ == "__main__":
    unittest.main()
