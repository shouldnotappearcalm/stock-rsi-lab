import unittest

from scripts.run_qlib_roll1_campaign_pre2026 import rank_development


class RollingCampaignTests(unittest.TestCase):
    def test_selection_uses_worst_year_and_rejects_losing_year(self):
        def row(first, second, exposure=95):
            return {"2024_return_pct": first, "2025_return_pct": second,
                    "average_exposure_pct": exposure, "net_annualized_pct": 20,
                    "cost_pct_initial": 2}
        results = {"unbalanced": row(5, 60), "balanced": row(15, 20),
                   "loss": row(-1, 100), "cash": row(30, 30, 50)}
        self.assertEqual(rank_development(results), ["balanced", "unbalanced"])
        results["invalid"] = row(float("nan"), 20)
        with self.assertRaisesRegex(ValueError, "finite"):
            rank_development(results)
