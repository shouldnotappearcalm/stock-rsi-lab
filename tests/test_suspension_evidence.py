import unittest
from datetime import date

from stock_rsi.suspension_evidence import verify_suspension_mark
from scripts.capture_baostock_gap_states_pre2026 import validate_rows


class SuspensionEvidenceTests(unittest.TestCase):
    def test_missing_price_alone_never_implies_suspension_or_a_valid_mark(self):
        class Snapshot:
            calendar = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
            def value(self, symbol, field, day):
                if day > "2024-01-03":
                    raise AssertionError("future quote in suspension valuation")
                return .5 if field == "factor" else (10. if day == "2024-01-02" else None)
        rows = {"2024-01-02":{"close":"20.0000","tradestatus":"1"},
                "2024-01-03":{"close":"20.0000","tradestatus":"0"}}
        result = verify_suspension_mark(Snapshot(), "SH600001", "2024-01-03", 10., rows)
        self.assertTrue(result["verified"])
        self.assertEqual(result["last_visible_close_date"], "2024-01-02")
        self.assertFalse(verify_suspension_mark(Snapshot(), "SH600001", "2024-01-03", 10., {})["verified"])
        self.assertFalse(verify_suspension_mark(Snapshot(), "SH600001", "2024-01-03", 11., rows)["verified"])
        rows["2024-01-03"]["tradestatus"] = "1"
        self.assertFalse(verify_suspension_mark(Snapshot(), "SH600001", "2024-01-03", 10., rows)["verified"])

    def test_capture_rejects_wrong_security_future_rows_and_duplicate_dates(self):
        fields = ["date","code","close","tradestatus","isST"]
        row = ["2024-04-30","sh.601456","10.4600","0","0"]
        self.assertEqual(len(validate_rows("SH601456", fields, [row])), 1)
        for bad in (["2026-01-05",*row[1:]], [row[0],"sz.000559",*row[2:]]):
            with self.assertRaises(ValueError):
                validate_rows("SH601456", fields, [bad])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_rows("SH601456", fields, [row,row])
