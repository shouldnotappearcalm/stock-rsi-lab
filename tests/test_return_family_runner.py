import unittest

try:
    from scripts.run_qlib_return_families_pre2026 import summarize_report
except ImportError:
    summarize_report=None


class ReturnFamilyRunnerTests(unittest.TestCase):
    def test_year_returns_use_the_actual_initial_capital_and_reconcile_net_account(self):
        self.assertIsNotNone(summarize_report,'return-family runner missing')
        try:import pandas as pd
        except ImportError:self.skipTest('optional research pandas is unavailable')
        report=pd.DataFrame({'return':[.11,.22],'cost':[.01,.02],'account':[1100000.,1320000.],
                             'value':[1045000.,1254000.],'total_cost':[10000.,30000.],
                             'total_turnover':[1000000.,2000000.]},
                            index=pd.to_datetime(['2024-12-31','2025-12-31']))
        result=summarize_report(report,1000000)
        self.assertAlmostEqual(result['2024_return_pct'],10)
        self.assertAlmostEqual(result['2025_return_pct'],20)
        self.assertAlmostEqual(result['net_compound_return_pct'],32)
        self.assertAlmostEqual(result['average_exposure_pct'],95)
        report.loc['2025-12-31','account']=1330000.
        with self.assertRaises(ValueError):summarize_report(report,1000000)
