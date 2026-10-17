import tempfile
import unittest

from scripts.run_qlib_low_risk_pre2026 import build_targets, development_gate, main, members_on, parse_memberships


class LowRiskCampaignTests(unittest.TestCase):
    def test_historical_membership_does_not_use_latest_roster(self):
        rows = parse_memberships("SH600001\t2020-01-01\t2024-06-30\nSH600002\t2024-07-01\t2026-12-31\nSZ300001\t2020-01-01\t2026-12-31\n")
        self.assertEqual(members_on(rows, "2024-01-31"), ["SH600001"])
        self.assertEqual(members_on(rows, "2024-07-31"), ["SH600002"])

    def test_gate_requires_both_years_profit_and_a_risk_effect_against_control(self):
        def row(first, second, volatility, exposure=95):
            return {"2024_return_pct":first, "2025_return_pct":second,
                    "net_daily_volatility_annualized_pct":volatility, "average_exposure_pct":exposure}
        control = row(5,30,20)
        self.assertTrue(development_gate(row(10,20,15), control, missing_marks=0))
        self.assertFalse(development_gate(row(20,-1,15), control, missing_marks=0))
        self.assertFalse(development_gate(row(10,20,21), control, missing_marks=0))
        self.assertFalse(development_gate(row(10,20,15), control, missing_marks=1))
        self.assertFalse(development_gate(row(10,20,15,80), control, missing_marks=0))

    def test_development_2026_cap_and_append_only_output_precede_execution(self):
        with self.assertRaisesRegex(ValueError, "permitted"):
            build_targets(None, {}, end="2026-01-05")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "already exists"):
                main(["--provider-uri","unused","--output-dir",directory])
