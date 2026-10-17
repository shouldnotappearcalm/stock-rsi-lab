import copy
import unittest

from scripts.run_qlib_low_risk_goal_diagnostic_2026 import eligible_for_goal_diagnostic, validate_diagnostic_states


class LowRiskGoalDiagnosticTests(unittest.TestCase):
    def test_goal_eligibility_does_not_relabel_failed_research_gate(self):
        summary = {"status":"PRE2026_DEVELOPMENT_ONLY", "end":"2025-12-31", "candidate_budget":1,
                   "2026_market_values_queried":False, "development_gate_status":"REJECTED",
                   "results":{"low_vol36":{"2024_return_pct":21.,"2025_return_pct":8.,
                                              "average_exposure_pct":95.,
                                              "unverified_held_marks":0,
                                              "all_monthly_decisions_match_prior_close_inventory_and_equity":True}}}
        original = copy.deepcopy(summary)
        self.assertTrue(eligible_for_goal_diagnostic(summary))
        self.assertEqual(summary,original)
        summary["results"]["low_vol36"]["2025_return_pct"] = -1.
        self.assertFalse(eligible_for_goal_diagnostic(summary))
        summary["2026_market_values_queried"] = True
        with self.assertRaisesRegex(ValueError,"pre-2026"):
            eligible_for_goal_diagnostic(summary)

    def test_diagnostic_state_capture_is_bounded_and_cannot_mix_securities(self):
        fields = ["date","code","close","tradestatus","isST"]
        row = ["2026-01-05","sh.600001","10.0000","0","0"]
        self.assertEqual(validate_diagnostic_states("SH600001",fields,[row])[0]["date"],row[0])
        for bad in (["2026-10-14",*row[1:]], [row[0],"sh.600002",*row[2:]]):
            with self.assertRaises(ValueError):
                validate_diagnostic_states("SH600001",fields,[bad])
