import copy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_asset_expansion_raw_horizon as m
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.run_low_risk_raw_share_validation import clean
from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistributionAccount


class ContinuousAccountTests(unittest.TestCase):
    def fixture(self):
        old_days = ['2023-12-29','2024-01-02','2024-12-31','2025-12-31']
        days = old_days + ['2026-01-05','2026-01-06']
        bars = {'SH600001':{d:{'date':d,'tradestatus':'1','isST':'0','open':'10.00',
            'close':'10.00','preclose':'10.00','volume':'10000000'} for d in days}}
        target = {'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}}
        old = simulate_fixed_targets(TradingCalendar(old_days), bars, (), target, '1000000', lifecycles={}, policy_id=m.CANDIDATE)
        expected = clean(old)
        expected['days'] = [{k:str(v) for k,v in row.items()} for row in old['days']]
        return days, bars, target, old, expected

    def run_observed(self, expected):
        days, bars, target, old, _ = self.fixture()
        target['2026-01-05'] = {'as_of':'2025-12-31','weights':{'SH600001':.5}}
        accounts = []
        def factory(*a, **kw):
            account = m.ObservedAccount(*a, expected=expected, lifecycles={}, **kw)
            accounts.append(account)
            return account
        case = simulate_fixed_targets(TradingCalendar(days), bars, (), target, '1000000', lifecycles={},
                                      account_factory=factory, policy_id=m.CANDIDATE)
        return case, accounts[0], target

    def test_observer_preserves_economics_and_checkpoints_before_january_intent(self):
        days,bars,_,old,expected = self.fixture()
        observed,account,targets = self.run_observed(expected)
        plain = simulate_fixed_targets(TradingCalendar(days), bars, (), targets, '1000000',
                                       lifecycles={}, account_factory=StockDistributionAccount, policy_id=m.CANDIDATE)
        self.assertEqual(observed,plain)
        self.assertEqual(clean(account.prefix_checkpoint['orders']),expected['orders'])
        self.assertGreater(len(observed['orders']),len(account.prefix_checkpoint['orders']))
        self.assertEqual(observed['intents'][-1]['execution_session'],'2026-01-05')
        check = m.verify_prefix(observed,expected,set(),{'SH600001'})
        self.assertTrue(check['passed'])
        self.assertEqual(account.prefix_checkpoint['last_clock'],(date(2025,12,31),1))

    def test_wrong_cash_shares_fills_or_order_status_stop_before_2026(self):
        for key in ('cash','ownership','fills','orders'):
            expected = self.fixture()[-1]
            if key == 'cash':expected['days'][-1]['cash']='0'
            elif key == 'ownership':expected[key][m.PREFIX]['SH600001']+=100
            elif key == 'fills':expected[key][0]['cost']='0'
            else:expected[key][0]['status']='PENDING'
            with self.subTest(key), self.assertRaisesRegex(ValueError,'checkpoint differs before next intent'):
                self.run_observed(expected)

    def test_full_prefix_rejects_financial_snapshot_and_added_nonzero_events(self):
        _,_,_,_,expected = self.fixture(); case,_,_ = self.run_observed(expected)
        for kind in ('daily','snapshot','extra_event'):
            altered = copy.deepcopy(case)
            if kind == 'daily':altered['days'][1]['equity']+=Decimal('.01')
            elif kind == 'snapshot':altered['intents'][0]['snapshot_sha256']='forged'
            else:altered['corporate_ledger'].append({'day':date(2025,6,1),'kind':'RECORD_DATE_OWNERSHIP',
                'event_id':'new','instrument':'SH600002','quantity':1})
            with self.subTest(kind),self.assertRaises(ValueError):
                m.verify_prefix(altered,expected,set(),{'SH600001'})
        case['corporate_ledger'].append({'day':date(2025,6,1),'kind':'RECORD_DATE_OWNERSHIP',
            'event_id':'new','instrument':'SH600002','quantity':0})
        self.assertEqual(m.verify_prefix(case,expected,set(),{'SH600001'})['extra_zero_ledger_entries'],1)

    def test_exit_checks_actual_claims_not_just_absence_from_targets(self):
        cal = TradingCalendar(['2026-03-30','2026-03-31'])
        for kind in ('cash','stock','order','owned','clear'):
            a = m.ObservedAccount(cal,'1000',expected={},lifecycles={'SH603056':{'effective_date':'2026-03-31'}})
            if kind == 'cash':a.cash_claims=[{'instrument':'SH603056','paid':False}]
            if kind == 'stock':a.stock_claims=[{'instrument':'SH603056','credited':False,'quantity':1}]
            if kind == 'order':a.broker.orders=[{'security_id':'SH603056','status':'PENDING'}]
            if kind == 'owned':a.broker.positions={'SH603056':[{'quantity':1,'bought_on':date(2026,3,30),'price':Decimal(10)}]}
            if kind == 'clear':
                a.start_day(date(2026,3,31));self.assertEqual(len(a.exit_checks),1)
            else:
                with self.subTest(kind),self.assertRaisesRegex(ValueError,'post-exit'):
                    a.start_day(date(2026,3,31))

    def test_year_return_uses_old_december_equity_without_reset(self):
        d = Decimal
        case = {'days':[{'day':'2024-12-31','equity':d(110)}, {'day':m.PREFIX,'equity':d(121)},
            {'day':m.END,'equity':d('133.10'),'exposure':d('.95'),'fees':d('1')}],
            'intents':[{}]*34,'whole_day_volume_violations':0,'fills':[],'orders':[]}
        summary=m.summarize(case,'100')
        self.assertEqual(summary['2026_through_'+m.END]['return_pct'],10.)
        self.assertEqual(summary['2026_through_'+m.END]['starting_equity_CNY'],'121')
        self.assertTrue(summary['three_return_conditions_met'])
        case['days'][-1]['equity']=d('133.09')
        self.assertFalse(m.summarize(case,'100')['three_return_conditions_met'])

    def test_unexpected_error_is_preserved_with_pending_cases_and_posthash(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);request=base/'freeze.json';request.write_text('{}')
            inputs={str(request):m.file_sha(request)}
            with patch.object(m,'authenticate',return_value=({'extra_cost_bps':[20,40]},inputs)), \
                 patch.object(m,'load_sources',side_effect=KeyboardInterrupt('original stop')):
                with self.assertRaisesRegex(KeyboardInterrupt,'original stop'):
                    m.execute(request,'fake',base,base,base/m.OUTPUT)
            out=base/m.OUTPUT;summary=m.read(out/'summary.json')
            self.assertEqual(summary['original_error']['error_type'],'KeyboardInterrupt')
            self.assertEqual(summary['pending_cost_cases'],['20','40'])
            self.assertTrue(m.read(out/'inputs-after.json')['unchanged'])
            self.assertFalse(summary['complete'])

    def test_posthash_interrupt_is_retained_and_propagated(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);request=base/'freeze.json';request.write_text('{}')
            sources=(None,{}, {},{},(),[],[],set())
            with patch.object(m,'authenticate',return_value=({'extra_cost_bps':[20,40]},{str(request):'fake'})), \
                 patch.object(m,'load_sources',return_value=sources), \
                 patch.object(m,'file_sha',side_effect=KeyboardInterrupt('posthash stop')):
                with self.assertRaisesRegex(KeyboardInterrupt,'posthash stop'):
                    m.execute(request,'fake',base,base,base/(m.OUTPUT+'-preflight'),True)
            summary=m.read(base/(m.OUTPUT+'-preflight')/'summary.json')
            self.assertEqual(summary['original_error']['error'],'posthash stop')
            self.assertEqual(summary['changed_inputs'],[str(request)])
            self.assertFalse(summary['complete'])

    def test_initial_write_error_still_records_original_error_and_posthash(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);request=base/'freeze.json';request.write_text('{}')
            original_save=m.save
            def failing_save(path,value):
                if Path(path).name=='inputs-before.json':raise OSError('initial failure')
                original_save(path,value)
            with patch.object(m,'authenticate',return_value=({'extra_cost_bps':[20,40]},{})), \
                 patch.object(m,'save',side_effect=failing_save):
                with self.assertRaisesRegex(OSError,'initial failure'):
                    m.execute(request,'fake',base,base,base/m.OUTPUT)
            summary=m.read(base/m.OUTPUT/'summary.json')
            self.assertEqual(summary['original_error']['error'],'initial failure')
            self.assertTrue((base/m.OUTPUT/'inputs-after.json').is_file())

    def test_finalization_error_cannot_hide_original_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);request=base/'freeze.json';request.write_text('{}')
            original_save=m.save
            def failing_save(path,value):
                if Path(path).name=='inputs-after.json':raise OSError('disk failure')
                original_save(path,value)
            with patch.object(m,'authenticate',return_value=({'extra_cost_bps':[20,40]},{})), \
                 patch.object(m,'load_sources',side_effect=ValueError('source failure')),patch.object(m,'save',side_effect=failing_save):
                with self.assertRaisesRegex(ValueError,'source failure'):
                    m.execute(request,'fake',base,base,base/m.OUTPUT)
            summary=m.read(base/m.OUTPUT/'summary.json')
            self.assertEqual(summary['original_error']['error'],'source failure')
            self.assertEqual(summary['persistence_errors'][0]['error'],'disk failure')


if __name__=='__main__':unittest.main()
