"""Synthetic account/guard integration. No real source files or SDK imports."""
import copy
import importlib
import unittest
from datetime import date
from decimal import Decimal as D

from scripts.replay_budgeted_stock_distribution_targets import simulate_budgeted_fixed_targets as old_replay
from stock_rsi.calendar import TradingCalendar
from stock_rsi.raw_share_account import Distribution
from stock_rsi.stock_distribution_account import StockDistribution, StockDistributionAccount

POLICY = 'low_market_residual_vol_1m_budgeted'


class OrdinaryBudgetedReplayTests(unittest.TestCase):
    def setUp(self):
        try: self.api=importlib.import_module('scripts.replay_ordinary_budgeted_stock_distribution_targets')
        except ModuleNotFoundError:self.fail('separately versioned ordinary budgeted replay is missing')
        self.calendar=TradingCalendar(['2024-04-30','2024-05-06','2024-05-07','2024-05-08','2024-05-09'])
        self.bars={'A':{str(d):{'date':str(d),'tradestatus':'1','isST':'0','open':'14.10','close':'14.10','preclose':'14.10','volume':'1000000'} for d in self.calendar.days}}
        self.targets={'2024-05-06':{'as_of':'2024-04-30','weights':{'A':'.95'}}}
    def replay(self,events=(),**kw):
        return self.api.simulate_ordinary_budgeted_fixed_targets(self.calendar,self.bars,events,self.targets,'20000',lifecycles=kw.pop('lifecycles',{}),**kw)
    def event(self,stock=False):
        args=('e','A',date(2024,4,29),date(2024,5,7),date(2024,5,8),date(2024,5,8),date(2024,5,9),D('.1'),D(0) if stock else D('.4'),not stock)
        return StockDistribution(*args,stock_per_share=D('.4'),stock_taxable_income_per_share=D('.1'),stock_tax_basis_verified=True) if stock else Distribution(*args)
    def test_all_ordinary_matches_every_legacy_budgeted_artifact_with_explicit_policy(self):
        for stock in (False,True):
            with self.subTest(stock=stock):
                for day in ('2024-05-08','2024-05-09'):self.bars['A'][day].update(preclose='10',open='10',close='10')
                before=copy.deepcopy((self.bars,self.targets));events=(self.event(stock),)
                expected=old_replay(self.calendar,self.bars,events,self.targets,'20000',lifecycles={},policy_id=POLICY)
                actual=self.replay(events,policy_id=POLICY)
                self.assertEqual(actual,expected)
                self.assertEqual((self.bars,self.targets),before)
                self.assertEqual(actual['ownership']['2024-05-09'],{'A':1820})
                self.assertTrue(any(r['kind']=='EX_DATE_ENTITLEMENT' for r in actual['corporate_ledger']))
                self.assertTrue(actual['intents'][0]['allocation_receipt'])
    def test_default_policy_preserves_explicit_candidate_snapshot_and_decision_ids(self):
        self.assertEqual(self.replay(),self.replay(policy_id=POLICY))
    def test_unused_ST_is_audited_without_source_or_decision_mutation(self):
        plain=self.replay();self.bars['B']={d:{**r,'isST':'1'} for d,r in self.bars['A'].items()};before=copy.deepcopy(self.bars)
        actual=self.replay();self.assertEqual(len(actual['lifecycle_source_audit']),5)
        self.assertTrue(all(x['reason']=='NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT' for x in actual['lifecycle_source_audit']))
        for key in ('days','fills','orders','ownership','corporate_ledger','intents'):self.assertEqual(actual[key],plain[key])
        self.assertEqual(self.bars,before);self.assertNotIn('NONORDINARY',str(actual['intents']))
    def test_each_required_ST_dependency_fails_before_start_day_or_any_credit(self):
        self.bars['B']={d:{**r,'isST':'1'} for d,r in self.bars['A'].items()}
        event=Distribution('positive','B',date(2024,4,26),date(2024,4,29),date(2024,4,30),date(2024,4,30),None,D('.1'),D(0),False)
        for dependency in ('held','pending_order','pending_stock','target','positive_entitlement'):
            with self.subTest(dependency=dependency):
                holders=[];starts=[]
                class Traced(StockDistributionAccount):
                    def start_day(a,day):starts.append(day);return super().start_day(day)
                def factory(cal,cash,events,**kw):
                    a=Traced(cal,cash,events,**kw)
                    if dependency=='held':a.broker.positions['B']=[{'quantity':100,'price':D('10'),'bought_on':date(2024,4,29)}]
                    if dependency=='pending_order':a.broker.orders.append({'security_id':'B','status':'PENDING'})
                    if dependency=='pending_stock':a.stock_claims.append({'instrument':'B','quantity':100,'credited':False,'listed':date(2024,5,9),'recorded':date(2024,4,29),'event_id':'claim','share_kind':'CAPITAL_TRANSFER'})
                    if dependency=='positive_entitlement':a.entitlements['positive']=100
                    holders.append(a);return a
                prior=copy.deepcopy(self.targets)
                if dependency=='target':self.targets['2024-05-06']['weights']={'B':'.95'}
                before=copy.deepcopy((self.bars,self.targets))
                with self.assertRaisesRegex(ValueError,'required nonordinary'):
                    self.replay((event,) if dependency=='positive_entitlement' else (),account_factory=factory)
                self.assertEqual(starts,[]);a=holders[0];self.assertEqual(a._processed,set());self.assertEqual(a.corporate_ledger,[]);self.assertEqual(a.broker.fills,[]);self.assertEqual(a.broker.cash,D('20000'))
                self.assertEqual((self.bars,self.targets),before);self.targets=prior
    def test_actual_pending_execution_and_held_next_day_ST_stop_before_that_day_start(self):
        for first_st in ('2024-05-06','2024-05-07'):
            with self.subTest(first_st=first_st):
                self.bars['A']={str(d):{'date':str(d),'tradestatus':'1','isST':'1' if str(d)==first_st else '0','open':'14.10','close':'14.10','preclose':'14.10','volume':'1000000'} for d in self.calendar.days}
                starts=[]
                class Traced(StockDistributionAccount):
                    def start_day(a,day):starts.append(day.isoformat());return super().start_day(day)
                with self.assertRaisesRegex(ValueError,'required nonordinary'):self.replay(account_factory=Traced)
                self.assertNotIn(first_st,starts)
    def test_primary_lifecycle_boundary_skips_only_absent_unrequired_source(self):
        self.bars['B']={d:{**r} for d,r in self.bars['A'].items() if d>='2024-05-07'}
        proof={'B':{'kind':'LISTING_BEGIN','effective_date':'2024-05-07','verified_primary_boundary':True,'primary_document_sha256':'a'*64}}
        result=self.replay(lifecycles=proof);self.assertEqual(len(result['lifecycle_source_audit']),2);self.assertNotIn('primary_document_sha256',str(result['intents']))
        with self.assertRaisesRegex(ValueError,'unexplained raw source gap'):self.replay()
        self.targets['2024-05-06']['weights']={'B':'.95'}
        with self.assertRaisesRegex(ValueError,'lifecycle interval still requires'):self.replay(lifecycles=proof)
        proof['B']['verified_primary_boundary']=False
        with self.assertRaisesRegex(ValueError,'authenticated primary'):self.replay(lifecycles=proof)
    def test_priorclose_budgeted_lots_nextopen_cashflow_and_T1_are_preserved(self):
        self.bars['A']['2024-05-06']['open']='14.50'
        actual=self.replay();intent=actual['intents'][0];receipt=intent['allocation_receipt'];fill=actual['fills'][0]
        self.assertEqual(intent['execution_session'],'2024-05-06');self.assertTrue(intent['as_of'].startswith('2024-04-30T'))
        self.assertEqual(fill['quantity'],1300);self.assertEqual(fill['quantity']%100,0);self.assertEqual(D(fill['price']),D('14.50'))
        self.assertFalse(receipt['execution_prices_or_returns_used']);self.assertLessEqual(receipt['final_planned_notional'],19000)
        self.assertEqual(actual['days'][1]['cash'],D('20000')-D('14.50')*1300-D(fill['cost']))
        self.assertTrue(actual['orders'][0]['eligible_at'].startswith('2024-05-06T'))
        # T+1 comes from the same broker: a synthetic same-day lot cannot sell.
        a=StockDistributionAccount(self.calendar,'20000');a.broker.positions={'A':[{'quantity':100,'price':D('10'),'bought_on':date(2024,5,6)}]}
        order=copy.deepcopy(actual['orders'][0]);order.update(action='SELL',quantity=100,status='PENDING');a.broker.orders=[order]
        bar={'security_id':'A','trade_date':'2024-05-06','suspended':False,'open':'14.10','limit_up':'15.00','limit_down':'13.00'}
        self.assertEqual(a.broker.on_market_open([bar]),[]);self.assertEqual(a.broker.orders[0]['status'],'UNFILLED_CASH_OR_T1')
        a.broker.orders[0].update(status='PENDING',expires_at=None,eligible_at=str(self.calendar.at(date(2024,5,7),'09:30:00')))
        bar['trade_date']='2024-05-07';self.assertEqual(a.broker.on_market_open([bar])[0]['quantity'],100)
    def test_unknown_ST_state_fails_closed_even_when_unused(self):
        for state in (None,'',True,'2'):
            self.bars['B']={d:{**r,'isST':state} for d,r in self.bars['A'].items()}
            with self.subTest(state=state),self.assertRaisesRegex(ValueError,'explicit ordinary'):self.replay()

if __name__=='__main__':unittest.main()
