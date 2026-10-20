import hashlib
import json
from datetime import date
from decimal import Decimal as D
import unittest
from stock_rsi.calendar import TradingCalendar
try:
    from scripts.run_budgeted_capital_income_stress_development import prefix_checked_factory
except ImportError:
    prefix_checked_factory = None


class CapitalStressRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(prefix_checked_factory)
        self.cal = TradingCalendar(['2025-06-26', '2025-06-27'])
        self.literal = {'last_account_clock':['2025-06-26',1],'cash':'10000','positions':{},'orders':[],
                        'fills':[],'owned_shares':{},'corporate_ledger':[],'cash_claims':[],'stock_claims':[]}

    def test_prefix_has_to_match_original_failure_bytes_before_any_new_processing(self):
        expected = (json.dumps(self.literal,indent=2)+'\n').encode(); evidence=[]
        factory=prefix_checked_factory(40,{},date(2025,6,27),hashlib.sha256(expected).hexdigest(),evidence)
        a=factory(self.cal,'10000',(),tax_reserve_rate='.2');a.end_day(date(2025,6,26));a.start_day(date(2025,6,27))
        self.assertEqual(len(evidence),1);self.assertTrue(evidence[0]['original_failure_bytes_reproduced'])
        self.assertEqual(a._last_clock,(date(2025,6,27),0))

    def test_mismatched_prefix_fails_before_clock_cash_or_distribution_mutation(self):
        evidence=[];factory=prefix_checked_factory(20,{},date(2025,6,27),'0'*64,evidence)
        a=factory(self.cal,'10000',(),tax_reserve_rate='.2');a.end_day(date(2025,6,26))
        with self.assertRaisesRegex(ValueError,'prefix'):a.start_day(date(2025,6,27))
        self.assertEqual(a.broker.cash,D('10000'));self.assertEqual(a._last_clock,(date(2025,6,26),1))
        self.assertEqual(a.capital_stress_ledger,[]);self.assertEqual(evidence,[])
