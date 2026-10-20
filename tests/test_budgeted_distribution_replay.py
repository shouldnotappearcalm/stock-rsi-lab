import copy
from datetime import date
from decimal import Decimal as D
import unittest
from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistribution
try:
    from scripts.replay_budgeted_stock_distribution_targets import simulate_budgeted_fixed_targets
except ImportError:
    simulate_budgeted_fixed_targets=None


class BudgetedDistributionReplayTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(simulate_budgeted_fixed_targets)
        self.calendar=TradingCalendar(['2023-12-29','2024-01-02','2024-01-03'])
        self.bars={c:{str(d):{'date':str(d),'tradestatus':'1','isST':'0','open':p,'close':p,'preclose':p,'volume':'1000000'}
            for d in self.calendar.days} for c,p in (('SH600001','16'),('SH600002','11'))}
        self.targets={'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':'.45','SH600002':'.5'}}}

    def run_case(self,bars=None,events=()):
        return simulate_budgeted_fixed_targets(self.calendar,bars or self.bars,events,self.targets,'10000',lifecycles={})

    def test_budgeted_increment_is_really_filled_in_the_unchanged_cash_account(self):
        r=self.run_case()
        self.assertEqual([(f['security_id'],f['quantity']) for f in r['fills']],[('SH600001',300),('SH600002',400)])
        self.assertEqual(r['days'][-1]['equity'],D('9990.00'))
        self.assertEqual(r['days'][-1]['market_value'],D('9200'))
        self.assertEqual(r['intents'][0]['allocation_receipt']['final_planned_notional'],9200)

    def test_future_execution_data_cannot_change_the_prior_close_intent(self):
        first=self.run_case();changed=copy.deepcopy(self.bars)
        changed['SH600001']['2024-01-02'].update(open='16.50',close='16.50')
        second=self.run_case(changed)
        self.assertEqual(first['intents'][0],second['intents'][0])
        self.assertNotEqual(first['fills'][0]['price'],second['fills'][0]['price'])

    def test_unverified_capital_tax_on_real_registered_inventory_still_rejects(self):
        e=StockDistribution('unverified','SH600001',date(2023,12,28),date(2024,1,2),date(2024,1,3),None,date(2024,1,3),D(0),D('.4'),False)
        with self.assertRaisesRegex(ValueError,'capital transfer tax treatment is unverified'):
            self.run_case(events=[e])


if __name__=='__main__':unittest.main()
