import copy
import unittest
from datetime import date
from decimal import Decimal as D
from scripts.run_low_risk_raw_share_validation import simulate_fixed_targets as legacy_replay
from stock_rsi.calendar import TradingCalendar
from stock_rsi.raw_share_account import Distribution
from stock_rsi.stock_distribution_account import StockDistribution,StockDistributionAccount
try:
    from scripts.replay_stock_distribution_targets import simulate_fixed_targets
except ImportError:
    simulate_fixed_targets=None


class LifecycleTargetReplayTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(simulate_fixed_targets)
        self.calendar=TradingCalendar(['2024-04-30','2024-05-06','2024-05-07','2024-05-08','2024-05-09'])
        self.bars={'A':{day:{'date':day,'tradestatus':'1','isST':'0','open':'14.10','close':'14.10',
            'preclose':'14.10','volume':'1000000'} for day in map(str,self.calendar.days)}}
        self.targets={'2024-05-06':{'as_of':'2024-04-30','weights':{'A':'.95'}}}

    def event(self,stock=False):
        args=('e','A',date(2024,4,29),date(2024,5,7),date(2024,5,8),date(2024,5,8),
            date(2024,5,9),D('.1'),D(0) if stock else D('.4'),not stock)
        return StockDistribution(*args,stock_per_share=D('.4'),stock_taxable_income_per_share=D('.4'),
            stock_tax_basis_verified=True) if stock else Distribution(*args)

    def replay(self,events=(),**kwargs):
        return simulate_fixed_targets(self.calendar,self.bars,events,self.targets,'20000',lifecycles=kwargs.pop('lifecycles',{}),**kwargs)

    def test_complete_cash_and_capital_daily_financial_prefix_matches_legacy(self):
        events=[self.event()]
        for day in ('2024-05-08','2024-05-09'):
            self.bars['A'][day].update(preclose='10',open='10',close='10')
        old=legacy_replay(self.calendar,self.bars,events,self.targets,'20000');new=self.replay(events)
        for key in ('days','ownership','max_daily_volume_fraction','whole_day_volume_violations'):
            self.assertEqual(old[key],new[key])
        self.assertEqual([(f['action'],f['quantity'],f['price'],f['cost']) for f in old['fills']],
            [(f['action'],f['quantity'],f['price'],f['cost']) for f in new['fills']])

    def test_stock_dividend_conserves_owned_shares_and_pending_value_until_listing(self):
        for day in ('2024-05-08','2024-05-09'):
            self.bars['A'][day].update(preclose='10',open='10',close='10')
        case=self.replay([self.event(True)])
        self.assertEqual(case['ownership']['2024-05-07']['A'],1300)
        self.assertEqual(case['ownership']['2024-05-08']['A'],1300)
        self.assertEqual(case['ownership']['2024-05-09']['A'],1820)
        self.assertEqual(case['days'][3]['pending_stock_value'],D('5200'))
        self.assertEqual(case['days'][4]['pending_stock_value'],D(0))
        self.assertEqual(case['corporate_ledger'][-1]['kind'],'STOCK_DIVIDEND_SHARES_LISTED')

    def test_listing_prefix_is_skipped_only_without_any_price_or_order_dependency(self):
        proof={'B':{'kind':'LISTING_BEGIN','effective_date':'2024-05-07','verified_primary_boundary':True,
            'primary_document_sha256':'a'*64}}
        self.bars['B']={d:{**row} for d,row in self.bars['A'].items() if d>='2024-05-07'}
        case=self.replay(lifecycles=proof)
        self.assertEqual(len(case['lifecycle_source_audit']),2)
        self.assertTrue(all('primary_document_sha256' not in str(i) for i in case['intents']))
        self.targets['2024-05-06']['weights']={'B':'.95'}
        with self.assertRaises(ValueError):self.replay(lifecycles=proof)

    def test_delisting_rejects_actual_inventory_even_when_vendor_bar_is_present(self):
        proof={'A':{'kind':'DELISTING_END','effective_date':'2024-05-08','verified_primary_boundary':True,
            'primary_document_sha256':'a'*64}}
        with self.assertRaisesRegex(ValueError,'lifecycle interval still requires'):
            self.replay(lifecycles=proof)

    def test_pending_unlisted_shares_and_pending_orders_cannot_hide_in_lifecycle_absence(self):
        proof={'B':{'kind':'LISTING_BEGIN','effective_date':'2024-05-07','verified_primary_boundary':True,
            'primary_document_sha256':'a'*64}}
        self.bars['B']={d:{**row} for d,row in self.bars['A'].items() if d>='2024-05-07'}
        def factory(cal,cash,events,**kwargs):
            a=StockDistributionAccount(cal,cash,events,**kwargs)
            a.stock_claims.append({'event_id':'pending','instrument':'B','quantity':100,'listed':date(2024,5,8),
                'recorded':date(2024,4,29),'credited':False,'share_kind':'STOCK_DIVIDEND'})
            return a
        with self.assertRaisesRegex(ValueError,'lifecycle interval still requires'):
            self.replay(lifecycles=proof,account_factory=factory)
        def order_factory(cal,cash,events,**kwargs):
            a=StockDistributionAccount(cal,cash,events,**kwargs)
            a.broker.orders.append({'security_id':'B','status':'PENDING'})
            return a
        with self.assertRaisesRegex(ValueError,'lifecycle interval still requires'):
            self.replay(lifecycles=proof,account_factory=order_factory)

    def test_unknown_held_mark_status_is_rejected_instead_of_reusing_old_price(self):
        self.bars['A']['2024-05-07']['tradestatus']='unknown'
        with self.assertRaisesRegex(ValueError,'market status'):
            self.replay()

    def test_intraday_factory_uses_child_execution_and_preserves_stock_account_conservation(self):
        from functools import partial
        from stock_rsi.intraday_broker import IntradayBroker
        from stock_rsi.intraday_tape import aggregate_minutes
        from scripts.tdx_history_checks import minute_labels
        used=[];holders=[]
        def tape(code,day):
            used.append((code,str(day)))
            points=[{'time':str(day)+'T'+label+':00+08:00','volume':10000,'price_milli':14100}
                    for label in minute_labels()]
            return aggregate_minutes(code,day,points)
        def factory(cal,cash,events,**kwargs):
            a=StockDistributionAccount(cal,cash,events,
                broker_factory=partial(IntradayBroker,participation_bps=500,extra_cost_bps=40,tape_provider=tape),**kwargs)
            holders.append(a.broker);return a
        case=self.replay(account_factory=factory)
        self.assertEqual(used,[('A','2024-05-06')])
        self.assertTrue(holders[0].child_orders)
        self.assertTrue(all(f['execution_at']>'2024-05-06T01:35:00+00:00' for f in case['fills']))
        self.assertEqual(case['ownership']['2024-05-06']['A'],1300)
