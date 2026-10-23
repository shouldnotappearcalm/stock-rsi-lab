import copy
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
import importlib
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from tests import test_asset_expansion_raw_horizon_account as legacy
from scripts.replay_stock_distribution_targets import simulate_fixed_targets

from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.stock_distribution_account import StockDistributionAccount
from scripts.run_low_risk_raw_share_validation import clean

try:
    m=importlib.import_module('scripts.run_asset_expansion_tax_proven_horizon')
except ModuleNotFoundError:
    m=None

class ProvenHorizonTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(m,'tax-proven horizon implementation required')

    def fixture(self):
        row={'code':'sh.603737','dividPreNoticeDate':'','dividAgmPumDate':'2026-05-14',
            'dividPlanAnnounceDate':'2026-04-23','dividPlanDate':'2026-05-26','dividRegistDate':'2026-05-29',
            'dividOperateDate':'2026-06-01','dividPayDate':'2026-06-01','dividStockMarketDate':'2026-06-01',
            'dividCashPsBeforeTax':'0.068','dividCashPsAfterTax':'0.0612或0.068','dividStocksPs':'0.000000',
            'dividCashStock':'10转2派0.68元（含税，扣税后0.612或0.68元）','dividReserveToStockPs':'0.200000'}
        packets={'SH603737':{'instrument':'SH603737','distributions':[row]}}
        cal=TradingCalendar(['2026-05-29','2026-06-01','2026-06-02'])
        proof={'documents':[],'capital_tax':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[]}
        events,receipts=compile_distribution_events(packets,proof,cal)
        doc={'instrument':'SH603737','day':'2026-05-26','file':m.PDF,'sha256':m.PDF_SHA}
        return packets,cal,events,receipts,doc

    def test_only_bound_event_identity_and_proof_change(self):
        p,c,events,receipts,doc=self.fixture();before=copy.deepcopy(p)
        new,newr,mapping=m.prove_one_event(p,c,events,receipts,doc)
        self.assertEqual(p,before);self.assertEqual(mapping,{events[0].event_id:new[0].event_id})
        old=asdict(events[0]);got=asdict(new[0])
        self.assertTrue(got.pop('capital_tax_exempt_verified'));old.pop('capital_tax_exempt_verified')
        self.assertNotEqual(got.pop('event_id'),old.pop('event_id'));self.assertEqual(got,old)
        self.assertEqual(newr[0]['primary_source_sha256'],[m.PDF_SHA])
        self.assertFalse(newr[0]['requires_zero_record_ownership_if_tax_unverified'])

    def test_wrong_source_ratio_date_or_issuer_rejected(self):
        for kind in ('ratio','date','issuer','sha'):
            p,c,e,r,doc=self.fixture()
            if kind=='ratio':p['SH603737']['distributions'][0]['dividReserveToStockPs']='0.4'
            elif kind=='date':doc['day']='2026-05-25'
            elif kind=='issuer':doc['instrument']='SH603738'
            else:doc['sha256']='a'*64
            with self.subTest(kind),self.assertRaises(ValueError):m.prove_one_event(p,c,e,r,doc)

    def test_proven_positive_capital_credits_once_unproven_still_fails(self):
        p,c,e,r,d=self.fixture();new,_,_=m.prove_one_event(p,c,e,r,d)
        for event,verified in [(e[0],False),(new[0],True)]:
            a=StockDistributionAccount(c,'1000',[event]);a.broker.positions={'SH603737':[
                {'quantity':2700,'bought_on':date(2026,5,28),'price':Decimal('10')}]}
            a.start_day(date(2026,5,29));a.end_day(date(2026,5,29))
            if not verified:
                with self.assertRaisesRegex(ValueError,'tax treatment is unverified'):a.start_day(date(2026,6,1))
                self.assertEqual(a.owned_quantities(),{'SH603737':2700});continue
            a.start_day(date(2026,6,1));a.start_day(date(2026,6,1))
            self.assertEqual(a.owned_quantities(),{'SH603737':3240})
            self.assertEqual(sum(x['quantity'] for x in a.stock_claims),540)
            self.assertEqual(sum(x['kind']=='CAPITAL_SHARES_LISTED' for x in a.corporate_ledger),1)

    def test_partial_state_mapping_does_not_mask_financial_differences(self):
        old={'last_clock':['2026-05-29',1],'cash':'10','owned':{'SH603737':2700},'orders':[],'fills':[],
            'positions':{},'cash_claims':[],'stock_claims':[],
            'entitlements':{'old':2700},'corporate_ledger':[{'event_id':'old','quantity':2700}]}
        current=copy.deepcopy(old);current['entitlements']={'new':2700};current['corporate_ledger'][0]['event_id']='new'
        self.assertTrue(m.verify_partial(current,old,{'old':'new'}))
        for key,value in [('cash','11'),('fills',[{'unexpected':1}]),('owned',{'SH603737':2800})]:
            altered=copy.deepcopy(current);altered[key]=value
            with self.subTest(key),self.assertRaises(ValueError):m.verify_partial(altered,old,{'old':'new'})
        self.assertEqual(old['entitlements'],{'old':2700})

    def test_unrelated_event_identity_and_receipt_are_exact(self):
        p,c,e,r,d=self.fixture()
        row=copy.deepcopy(p['SH603737']['distributions'][0]);row.update(code='sh.600001',
            dividReserveToStockPs='0',dividCashStock='10派0.68元',dividStockMarketDate='')
        p['SH600001']={'instrument':'SH600001','distributions':[row]}
        e,r=compile_distribution_events(p,{'documents':[],'capital_tax':{},'stock_dividend_tax_bases':{}},c)
        new,newr,_=m.prove_one_event(p,c,e,r,d)
        self.assertEqual(e[0],new[0]);self.assertEqual(r[0],newr[0])

    def test_changed_review_receipt_rejected_before_any_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);p=repo/m.REVIEW;p.parent.mkdir(parents=True);p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'exact independently checked primary receipt'):
                m.checked_review(repo,repo)

    def test_observer_keeps_legacy_snapshots_and_before_january_checkpoint(self):
        days,bars,targets,old,expected=legacy.ContinuousAccountTests().fixture()
        targets['2026-01-05']={'as_of':'2025-12-31','weights':{'SH600001':.5}}
        accounts=[]
        def factory(*args,**kw):
            a=m.ObservedAccount(*args,expected=expected,lifecycles={},expected_partial={},event_id_map={},**kw)
            accounts.append(a);return a
        case=simulate_fixed_targets(TradingCalendar(days),bars,(),targets,'1000000',lifecycles={},
                                    account_factory=factory,policy_id=m.CANDIDATE)
        self.assertTrue(m.verify_prefix(case,expected,set(),{'SH600001'})['passed'])
        self.assertEqual(clean(accounts[0].prefix_checkpoint['orders']),expected['orders'])
        self.assertGreater(len(case['orders']),len(expected['orders']))

    def test_annual_denominator_remains_continuous(self):
        d=Decimal
        case={'days':[{'day':'2024-12-31','equity':d(110)},{'day':m.PREFIX,'equity':d(121)},
              {'day':m.END,'equity':d('133.10'),'exposure':d('.95'),'fees':d(1)}],
              'intents':[{}]*34,'whole_day_volume_violations':0,'fills':[],'orders':[]}
        self.assertTrue(m.summarize(case,'100')['three_return_conditions_met'])
        self.assertEqual(m.summarize(case,'100')['2026_through_'+m.END]['starting_equity_CNY'],'121')

    def test_real_replay_matches_stopped_state_then_credits_without_changing_old_snapshots(self):
        packets,_,events,receipts,doc=self.fixture()
        days=['2023-12-29','2024-01-02','2024-12-31','2025-12-31','2026-05-29','2026-06-01','2026-06-02']
        cal=TradingCalendar(days);new,_,mapping=m.prove_one_event(packets,cal,events,receipts,doc)
        bars={'SH603737':{d:{'date':d,'tradestatus':'1','isST':'0','open':'35.00',
            'close':'35.00','preclose':'35.00','volume':'10000000'} for d in days}}
        target={'2024-01-02':{'as_of':'2023-12-29','weights':{'SH603737':.95}}}
        legacy_case=simulate_fixed_targets(TradingCalendar(days[:4]),bars,events,target,'100000',
                                           lifecycles={},policy_id=m.CANDIDATE)
        expected=clean(legacy_case)
        expected['days']=[{k:str(v) for k,v in row.items()} for row in legacy_case['days']]
        accounts=[]
        def old_factory(*args,**kw):
            a=StockDistributionAccount(*args,**kw);accounts.append(a);return a
        with self.assertRaisesRegex(ValueError,'tax treatment is unverified'):
            simulate_fixed_targets(cal,bars,events,target,'100000',lifecycles={},account_factory=old_factory,policy_id=m.CANDIDATE)
        stopped=clean(m.account_state(accounts[0]));newaccounts=[]
        def new_factory(*args,**kw):
            a=m.ObservedAccount(*args,expected=expected,lifecycles={},expected_partial=stopped,event_id_map=mapping,**kw)
            newaccounts.append(a);return a
        case=simulate_fixed_targets(cal,bars,new,target,'100000',lifecycles={},account_factory=new_factory,policy_id=m.CANDIDATE)
        self.assertTrue(newaccounts[0].partial_verified)
        self.assertEqual(clean(case['intents']),expected['intents'])
        self.assertEqual(case['ownership']['2026-06-01']['SH603737'],3240)
        self.assertEqual(m.verify_capital_credit(case,newaccounts[0],mapping)['capital_shares'],540)

    def test_interrupt_records_pending_cases_original_error_and_posthash(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);request=base/'freeze.json';request.write_text('{}')
            with patch.object(m,'authenticate',return_value=({'extra_cost_bps':[20,40]},{})), \
                 patch.object(m,'load_sources',side_effect=KeyboardInterrupt('source interruption')):
                with self.assertRaisesRegex(KeyboardInterrupt,'source interruption'):
                    m.execute(request,'fake',base,base,base/m.OUTPUT)
            summary=m.read(base/m.OUTPUT/'summary.json')
            self.assertEqual(summary['pending_cost_cases'],['20','40'])
            self.assertEqual(summary['original_error']['error_type'],'KeyboardInterrupt')
            self.assertTrue(m.read(base/m.OUTPUT/'inputs-after.json')['unchanged'])

    def test_failure_writer_error_preserves_both_case_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);request=base/'freeze.json';request.write_text('{}')
            source=base/m.OLD_RAW;source.mkdir();m.save(source/'manifest.json',{'per_code_sha256':{}})
            save=m.save
            def faulty(path,value):
                if Path(path).parts[-2:] == ('20','error.json'):raise OSError('case writer failure')
                save(path,value)
            sources=(None,{}, {},{},(),[],[],set(),{})
            with patch.object(m,'authenticate',return_value=({'extra_cost_bps':[20,40],'initial_CNY':'1000000'},{})), \
                 patch.object(m,'load_sources',return_value=sources),patch.object(m,'expected_prefix',return_value={}), \
                 patch.object(m,'simulate_fixed_targets',side_effect=ValueError('original account failure')), \
                 patch.object(m,'save',side_effect=faulty):
                with self.assertRaisesRegex(OSError,'case writer failure'):
                    m.execute(request,'fake',base,base,base/m.OUTPUT)
            summary=m.read(base/m.OUTPUT/'summary.json')
            self.assertFalse(summary['complete']);self.assertEqual(summary['pending_cost_cases'],[])
            self.assertEqual(set(summary['results_by_extra_bps']),{'20','40'})
            self.assertTrue(all(x['error']=='original account failure' for x in summary['results_by_extra_bps'].values()))
            self.assertEqual(summary['persistence_errors'][0]['error'],'case writer failure')

if __name__=='__main__':unittest.main()
