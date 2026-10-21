"""Synthetic integration of phase-bound regime execution and the frozen allocator."""
import copy
import hashlib
import importlib
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from functools import partial

from stock_rsi.execution_cost import ExecutionCostBroker

from scripts.replay_ordinary_budgeted_stock_distribution_targets import simulate_ordinary_budgeted_fixed_targets as ordinary_replay
from stock_rsi.calendar import TradingCalendar
from stock_rsi.broker import Broker
from stock_rsi.raw_share_account import Distribution
from stock_rsi.stock_distribution_account import StockDistributionAccount

POLICY = 'low_market_residual_vol_1m_budgeted'


class RegimeBudgetedReplayTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('scripts.replay_regime_budgeted_stock_distribution_targets')
        except ModuleNotFoundError:
            self.fail('independently versioned regime replay is missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calendar = TradingCalendar(['2024-04-30','2024-05-06','2024-05-07','2024-05-08','2024-05-09'])
        self.bars = {'SH600079':{str(d):{'date':str(d),'tradestatus':'1','isST':'0',
            'open':'14.10','close':'14.10','preclose':'14.10','volume':'1000000'} for d in self.calendar.days}}
        self.targets = {'2024-05-06':{'as_of':'2024-04-30','weights':{'SH600079':'.95'}}}
        rule = Path(self.tmp.name)/'rule.pdf'
        rule.write_bytes(b'synthetic independently authenticated rule fixture')
        self.evidence = {'contract':'SSE_MAINBOARD_RISK_WARNING_PRE2026_V1',
            'rule_document':{'source_file':rule.name,'sha256':hashlib.sha256(rule.read_bytes()).hexdigest(),
                'published_on':'2023-12-28','valid_from':'2023-12-29','valid_through':'2025-12-31'},
            'state_intervals':[], 'account_capabilities':{'risk_warning_buy_permission':False}}

    def replay(self, events=(), **kw):
        return self.api.simulate_regime_budgeted_fixed_targets(self.calendar,self.bars,events,
            self.targets,'20000',lifecycles=kw.pop('lifecycles',{}),regime_evidence=self.evidence,**kw)

    def risk_interval(self, start='2024-05-07', available=None):
        path=Path(self.tmp.name)/'issuer.pdf';path.write_bytes(b'synthetic issuer risk-warning original')
        self.evidence['state_intervals']=[{'instrument':'SH600079','exchange':'SSE','board':'MAINBOARD',
            'risk_status':'OTHER_RISK_WARNING','effective_from':start,'effective_through':'2024-05-09',
            'published_on':'2024-04-29','engineering_available_at':available or start+'T09:00:00+08:00',
            'actual_arrival_verified':False,'source_file':path.name,
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
        for day,row in self.bars['SH600079'].items():
            row['isST']='1' if day>=start else '0'

    def test_all_ordinary_every_old_artifact_exact_and_inputs_immutable(self):
        event=Distribution('e','SH600079',date(2024,4,29),date(2024,5,7),date(2024,5,8),
            date(2024,5,8),date(2024,5,9),D('.1'),D('.4'),True)
        for day in ('2024-05-08','2024-05-09'):
            self.bars['SH600079'][day].update(open='10',close='10',preclose='10')
        before=copy.deepcopy((self.bars,self.targets,self.evidence))
        expected=ordinary_replay(self.calendar,self.bars,(event,),self.targets,'20000',lifecycles={},policy_id=POLICY)
        actual=self.replay((event,),policy_id=POLICY)
        for key,value in expected.items():self.assertEqual(actual[key],value,key)
        self.assertEqual((self.bars,self.targets,self.evidence),before)
        self.assertTrue(actual['intents'][0]['allocation_receipt'])
        self.assertEqual(actual['ownership']['2024-05-09'],{'SH600079':1820})

    def test_execution_cost_profiles_preserve_each_ordinary_artifact(self):
        for extra in (20,40):
            with self.subTest(extra=extra):
                factory=partial(StockDistributionAccount,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=extra))
                expected=ordinary_replay(self.calendar,self.bars,(),self.targets,'20000',
                    lifecycles={},policy_id=POLICY,account_factory=factory)
                actual=self.replay(account_factory=factory)
                for key,value in expected.items():self.assertEqual(actual[key],value,key)

    def test_held_transition_with_no_orders_keeps_raw_marks_and_physical_shares(self):
        plain=self.replay();self.risk_interval();before=copy.deepcopy((self.bars,self.targets,self.evidence))
        actual=self.replay()
        for key in ('days','fills','orders','ownership','corporate_ledger','intents'):
            self.assertEqual(actual[key],plain[key],key)
        self.assertEqual(actual['ownership']['2024-05-09'],{'SH600079':1300})
        self.assertTrue(actual['regime_audit'])
        self.assertEqual((self.bars,self.targets,self.evidence),before)

    def test_bad_second_open_is_validated_before_start_day_cash_claims_or_first_fill(self):
        self.bars['SH600080']=copy.deepcopy(self.bars['SH600079'])
        self.targets['2024-05-06']['weights']={'SH600079':'.475','SH600080':'.475'}
        self.bars['SH600080']['2024-05-06']['open']='14.101'
        starts=[];accounts=[]
        class Traced(StockDistributionAccount):
            def start_day(a,day):starts.append(str(day));return super().start_day(day)
        def factory(*args,**kw):
            a=Traced(*args,**kw);accounts.append(a)
            a.cash_claims.append({'event_id':'due','net':D('1'),
                'available_on':date(2024,5,6),'paid':False})
            return a
        with self.assertRaises(ValueError):self.replay(account_factory=factory)
        self.assertNotIn('2024-05-06',starts)
        self.assertEqual(accounts[0].broker.fills,[])
        self.assertEqual(accounts[0].broker.cash,D('20000'))
        self.assertFalse(accounts[0].cash_claims[0]['paid'])

    def test_future_close_and_whole_day_volume_do_not_choose_opening_fill(self):
        plain=self.replay()
        self.bars['SH600079']['2024-05-06'].update(close='15.00',volume='1')
        observed=[]
        class OpenTrace(Broker):
            def on_market_open(b,rows):
                observed.extend(copy.deepcopy(rows));return super().on_market_open(rows)
        changed=self.replay(account_factory=partial(StockDistributionAccount,broker_factory=OpenTrace))
        self.assertTrue(observed)
        for row in observed:self.assertFalse(set(row)&{'close','high','low','volume','amount'})
        self.assertEqual(changed['fills'],plain['fills'])
        self.assertEqual(changed['orders'],plain['orders'])
        self.assertEqual(changed['intents'],plain['intents'])
        self.assertEqual(changed['execution_status'],'INVALID_OBSERVED_TAPE_CAPACITY')
        self.assertNotEqual(changed['days'][1]['equity'],plain['days'][1]['equity'])

    def test_next_target_dependency_enters_at_close_and_late_held_proof_fails_preopen(self):
        self.risk_interval('2024-04-30',available='2024-04-30T15:00:00+08:00')
        # The first day has no owned/pending dependency; target becomes known at15:05.
        starts=[]
        class Traced(StockDistributionAccount):
            def start_day(a,day):starts.append(str(day));return super().start_day(day)
        refused=self.replay(account_factory=Traced)
        # BUY permission creates an auditable terminal refusal, without a fill.
        self.assertEqual(refused['fills'],[])
        self.assertEqual(refused['orders'][0]['status'],'UNFILLED_RISK_WARNING_PERMISSION')
        self.assertEqual(refused['days'][-1]['cash'],D('20000'))
        self.assertIn('2024-04-30',starts)
        self.assertIn('2024-05-06',starts)
        first=refused['phase_audit']
        self.assertEqual(first[0]['phase'],'PREOPEN_SOURCE_VALIDATED')
        self.assertEqual(first[0]['required'],[])
        self.assertEqual(first[1]['phase'],'OPEN_VALIDATED_BEFORE_ACCOUNT_START')
        self.assertEqual(first[1]['as_of'],str(self.calendar.at(date(2024,4,30),'09:30:00')).replace(' ', 'T'))
        close=next(x for x in first if x['session']=='2024-04-30' and x['phase']=='CLOSE_RECORDED')
        self.assertEqual(close['required'],['SH600079'])
        self.risk_interval('2024-05-07',available='2024-05-07T15:00:00+08:00');starts.clear()
        with self.assertRaises(ValueError):self.replay(account_factory=Traced)
        self.assertNotIn('2024-05-07',starts)

    def test_monthly_target_can_sell_supported_ST_without_forced_liquidation(self):
        # The rotation is a literal monthly target, not a state-triggered sell.
        self.calendar=TradingCalendar([str(d) for d in self.calendar.days]+['2024-05-31','2024-06-03','2024-06-04'])
        for day in ('2024-05-31','2024-06-03','2024-06-04'):
            self.bars['SH600079'][day]={**self.bars['SH600079']['2024-05-09'],'date':day}
        self.bars['SH600080']=copy.deepcopy(self.bars['SH600079'])
        self.targets['2024-06-03']={'as_of':'2024-05-31','weights':{'SH600080':'.95'}}
        ordinary=self.replay()
        self.risk_interval();self.evidence['state_intervals'][0]['effective_through']='2024-06-04'
        actual=self.replay()
        for key in ('days','ownership','corporate_ledger'):
            self.assertEqual(actual[key],ordinary[key],key)
        # A formation-day ST source changes evidence IDs, but not cash economics.
        economic=lambda result:[{k:v for k,v in f.items() if k!='order_id'} for f in result['fills']]
        self.assertEqual(economic(actual),economic(ordinary))
        sells=[f for f in actual['fills'] if f['action']=='SELL']
        self.assertEqual(len(sells),1);self.assertEqual(sells[0]['security_id'],'SH600079')
        self.assertEqual(sells[0]['quantity'],1300)
        sell_order=next(o for o in actual['orders'] if o['action']=='SELL')
        self.assertEqual(sell_order['order_type'],'LIMIT')
        self.assertEqual(D(sell_order['limit_price']),D('13.40'))
        self.assertEqual(actual['ownership']['2024-05-31'],{'SH600079':1300})
        self.assertEqual(self.targets['2024-06-03']['weights'],{'SH600080':'.95'})

    def test_lifecycle_and_unknown_capital_tax_guards_remain_fail_closed(self):
        self.bars['SH600080']={d:copy.deepcopy(r) for d,r in self.bars['SH600079'].items() if d>='2024-05-07'}
        with self.assertRaises(ValueError):self.replay()
        proof={'SH600080':{'kind':'LISTING_BEGIN','effective_date':'2024-05-07',
            'verified_primary_boundary':True,'primary_document_sha256':'a'*64}}
        self.assertTrue(self.replay(lifecycles=proof)['lifecycle_source_audit'])
        del self.bars['SH600080']
        event=Distribution('unknown','SH600079',date(2024,4,29),date(2024,5,7),date(2024,5,8),
            date(2024,5,8),date(2024,5,9),D('.1'),D('.4'),False)
        with self.assertRaises(ValueError):self.replay((event,))
        fractional=Distribution('fractional','SH600079',date(2024,4,29),date(2024,5,7),date(2024,5,8),
            date(2024,5,8),date(2024,5,9),D('.1'),D('.0001'),True)
        with self.assertRaisesRegex(ValueError,'fractional'):self.replay((fractional,))

if __name__=='__main__':unittest.main()
