from pathlib import Path
from unittest import TestCase
from scripts.run_cash_accrual_horizon_targets import same_policy
from stock_rsi import cash_accrual_horizon as h
from tests.test_annual_cash_accruals import DOC

class CashAccrualHorizonTests(TestCase):
    def test_only_window_clock_year_and_diagnostics_changed_in_ast(self):
        p=Path(__file__).resolve().parents[1]/'src/stock_rsi';old=(p/'cash_accrual_monthly.py').read_text();new=(p/'cash_accrual_horizon.py').read_text();same_policy(old,new)
        for before,after in [('100,','99,'),('len(scores)>=100','len(scores)>=99'),('.95/len(selected)','.90/len(selected)')]:
            changed=new.replace(before,after)
            if changed!=new:
                with self.assertRaises(ValueError):same_policy(old,changed)
    def test_2026publication_end_gate_and_no_older_fallback_for_later_source(self):
        old=DOC;new={**DOC,'effective_fiscal_year':2025,'day':'2026-01-08','capture_key':'new'}
        for clock,expected in [('2026-01-08T15:05:00+08:00',old),('2026-01-09T15:05:00+08:00',new)]:
            self.assertEqual(h.visible_latest([old,new],[DOC['instrument']],clock)[DOC['instrument']][0],expected)
        def poison(k):raise AssertionError('future financial loader')
        self.assertIsNone(h.observation(new,poison,{},'2026-01-08T15:05:00+08:00'))
    def test_unknown_fiscal_identity_stops_instead_of_guessing_or_falling_back(self):
        new={**DOC,'effective_fiscal_year':None,'day':'2026-01-08','capture_key':'unknown'}
        with self.assertRaises(ValueError):h.visible_latest([DOC,new],[DOC['instrument']],'2026-01-09T15:05:00+08:00')
