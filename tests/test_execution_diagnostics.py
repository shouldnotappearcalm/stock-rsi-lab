from datetime import date
import unittest
try:
    from stock_rsi.execution_diagnostics import buy_window_evidence
except ImportError:buy_window_evidence=None
from stock_rsi.intraday_tape import aggregate_minutes
from scripts.tdx_history_checks import minute_labels

class ExecutionDiagnosticTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(buy_window_evidence)
    def series(self):
        day='2024-10-08'
        points=[{'time':day+'T'+label+':00+08:00','price_milli':11000,'volume':101} for label in minute_labels()]
        return aggregate_minutes('SH600001',date.fromisoformat(day),points)
    def test_an_open_locked_day_can_have_later_guarded_windows_without_proving_a_fill(self):
        rows=self.series();rows[2]['buy_price']='10.90';rows[2]['sell_price']='10.90'
        out=buy_window_evidence(rows,{'preclose':'10','tradestatus':'1','isST':'0'},100)
        self.assertEqual(out['protective_buy_limit_CNY'],'10.95')
        self.assertEqual(out['candidate_windows'],1)
        self.assertEqual(out['windows'][0]['start'],rows[2]['start'])
        self.assertIs(out['actual_fill_verified'],False)
    def test_needs_previous_and_current_capacity_and_strict_price(self):
        rows=self.series();rows[2]['buy_price']='10.95'
        self.assertEqual(buy_window_evidence(rows,{'preclose':'10','tradestatus':'1','isST':'0'},500)['candidate_windows'],0)
        rows[2]['buy_price']='10.90';rows[1]['volume_lower_shares']=0
        self.assertEqual(buy_window_evidence(rows,{'preclose':'10','tradestatus':'1','isST':'0'},500)['candidate_windows'],0)
        rows[1]['volume_lower_shares']=50000;rows[2]['volume_lower_shares']=0
        self.assertEqual(buy_window_evidence(rows,{'preclose':'10','tradestatus':'1','isST':'0'},500)['candidate_windows'],0)
    def test_first_unobservable_and_after_expiry_windows_are_not_counted(self):
        rows=self.series()
        for i in (0,47):rows[i]['buy_price']='10.90'
        self.assertEqual(buy_window_evidence(rows,{'preclose':'10','tradestatus':'1','isST':'0'},500)['candidate_windows'],0)
    def test_halt_or_unknown_special_status_does_not_create_an_opportunity(self):
        rows=self.series();rows[2]['buy_price']='10.90'
        for state in ({'preclose':'10','tradestatus':'0','isST':'0'},{'preclose':'10','tradestatus':'1','isST':'1'}):
            self.assertEqual(buy_window_evidence(rows,state,500)['candidate_windows'],0)
        with self.assertRaises(ValueError):buy_window_evidence(rows,{'preclose':'10','tradestatus':'1','isST':'0'},200)
        with self.assertRaises(ValueError):buy_window_evidence(rows[:-1],{'preclose':'10','tradestatus':'1','isST':'0'},500)
