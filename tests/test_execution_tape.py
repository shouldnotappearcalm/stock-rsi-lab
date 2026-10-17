import unittest

from scripts.capture_low_risk_execution_tape import FIELDS, SLOTS, validate_minutes
from scripts.audit_low_risk_execution_tape import audit_case, regular_main_board_limits, fixed_fill_cost_sensitivity, validate_request_coverage
from scripts.capture_low_risk_execution_tape import EXPECTED_SUMMARY
from decimal import Decimal


class ExecutionTapeTests(unittest.TestCase):
    def row(self, at):
        return ["2024-01-02", "20240102" + at, "sh.600008", "2.69", "2.70", "2.67", "2.68",
                "10000", "26800", "3"]

    def test_complete_exchange_slots_and_partial_capture_are_distinguished(self):
        self.assertEqual(len(SLOTS), 48)
        self.assertEqual(SLOTS[0], "093500000")
        self.assertEqual(SLOTS[-1], "150000000")
        rows, full = validate_minutes("SH600008", "2024-01-02", FIELDS, [self.row(at) for at in SLOTS])
        self.assertTrue(full)
        self.assertEqual(len(rows), 48)
        self.assertFalse(validate_minutes("SH600008", "2024-01-02", FIELDS, [self.row(SLOTS[0])])[1])
        self.assertFalse(validate_minutes("SH600008", "2024-01-02", FIELDS, [])[1])

    def test_future_lunch_adjusted_wrong_security_and_duplicate_rows_fail(self):
        original = self.row(SLOTS[0])
        for index, value in ((0, "2024-01-03"), (1, "20240102120000000"),
                             (2, "sh.600009"), (9, "2"), (7, "1.5")):
            changed = original.copy(); changed[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_minutes("SH600008", "2024-01-02", FIELDS, [changed])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_minutes("SH600008", "2024-01-02", FIELDS, [original, original])

    def test_half_tick_limits_and_oversized_orders_are_not_silently_split(self):
        self.assertEqual(regular_main_board_limits("10.05"), (Decimal("9.05"), Decimal("11.06")))
        self.assertEqual(regular_main_board_limits(".01"), (Decimal(".01"), Decimal(".02")))
        case = audit_case([{"quantity":1000001, "order_id":"oversized"}], [], {}, {})
        self.assertEqual(case["status"], "INVALID_ORIGINAL_SINGLE_ORDER_TRACE")
        self.assertEqual(case["orders_over_one_million_shares"], 1)

    def test_first_label_volume_is_not_promoted_to_verified_auction_capacity(self):
        row = {"preclose":"10", "open":"10", "close":"10", "volume":"4800", "isST":"0"}
        tape = [{"open":"10", "close":"10", "volume":"100"} for _ in range(48)]
        fill = {"security_id":"SH600008", "quantity":200, "price":"10", "execution_at":"2024-01-02T01:30:00+00:00", "order_id":"a"}
        case = audit_case([{"quantity":200}], [fill], {"SH600008":{"2024-01-02":row}}, {("SH600008","2024-01-02"):tape})
        self.assertEqual(case["first_label_capacity"]["over_100pct"], 1)
        self.assertFalse(case["auction_volume_inclusion_verified"])
        self.assertFalse(case["opening_fill_verified"])
        self.assertEqual(case["status"], "NECESSARY_SCREENS_PASSED_AUCTION_UNVERIFIED")

    def test_fixed_fill_cost_diagnostic_reports_negative_shadow_cash_and_no_resimulation(self):
        rows=[{"day":day,"equity":"1000","cash":"0"} for day in ("2024-12-31","2025-12-31","2026-10-16")]
        fills=[{"price":"10","quantity":100,"execution_at":"2024-12-31T01:30:00+00:00"}]
        result=fixed_fill_cost_sensitivity(rows,fills,"1000")
        self.assertEqual(result["20"]["additional_charge_CNY"],"2.00")
        self.assertEqual(result["20"]["2024_pct"],-.2)
        self.assertEqual(result["20"]["negative_shadow_cash_days"],3)
        self.assertFalse(result["20"]["same_target_policy_resimulated"])

    def test_missing_unfilled_order_session_cannot_be_omitted_from_admission(self):
        expected = {("SH600008","2024-01-02"), ("SH600009","2024-01-02")}
        plan = {"summary_sha256":EXPECTED_SUMMARY,"requests":[list(key) for key in sorted(expected)]}
        manifest = {"requests":2,"per_session_sha256":{"a":"hash","b":"hash"}}
        tapes = {key:[] for key in expected}
        validate_request_coverage(expected,plan,manifest,tapes)
        del tapes[("SH600009","2024-01-02")]
        with self.assertRaisesRegex(ValueError,"exact frozen"):
            validate_request_coverage(expected,plan,manifest,tapes)
        order={"quantity":100,"security_id":"SH600009","order_id":"unfilled",
               "eligible_at":"2024-01-02T01:30:00+00:00"}
        case=audit_case([order],[],{},tapes)
        self.assertEqual(case["status"],"INCOMPLETE_EXECUTION_SOURCE_CHECK")
        self.assertEqual(case["incomplete_order_session_tape"],["unfilled"])
