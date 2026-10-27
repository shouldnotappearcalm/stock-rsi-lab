from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from scripts import run_cash_accrual_raw_pre2026 as r

class CashAccrualRawAccountTests(TestCase):
    def fixture(self):
        event=SimpleNamespace(event_id='test',instrument='SH600001',recorded=date(2024,5,20))
        receipt={'event_id':'test','requires_zero_record_ownership_if_tax_unverified':True}
        case={'ownership':{'2024-05-20':{}},'corporate_ledger':[{'kind':'EX_DATE_ENTITLEMENT','event_id':'test','registered_quantity':0}]}
        return case,[event],[receipt]
    def test_unverified_capital_events_require_actual_zero_ownership_and_exact_receipt(self):
        case,events,receipts=self.fixture();self.assertEqual(r.unknown_checks(case,events,receipts)[0]['actual_owned_shares'],0)
        for mode in ('owned','receipt','missing','wrongid'):
            case,events,receipts=self.fixture()
            if mode=='owned':case['ownership']['2024-05-20']['SH600001']=100
            if mode=='receipt':case['corporate_ledger'][0]['registered_quantity']=100
            if mode=='missing':receipts=[]
            if mode=='wrongid':receipts[0]['event_id']='forged'
            with self.subTest(mode=mode),self.assertRaises(ValueError):r.unknown_checks(case,events,receipts)
    def test_fixed_strategy_cost_window_and_fractional_policy_cannot_be_waived(self):
        for k,v in [('extra_bps',[0]),('window',['2023-12-29','2026-10-27']),('source_names',30),('unverified_noncash_require_actual_zero_ownership',0),('fractional_policy','FLOOR_ALL')]:
            with self.subTest(k=k),self.assertRaises(ValueError):r.validate({**r.PROFILE,k:v})
    def test_native_account_failure_keeps_state_and_no_completed_return(self):
        with TemporaryDirectory() as t:
            out=Path(t)/'out';auth={'known':{},'request_sha256':'a'*64,'events':[],'event_receipts':[],'calendar':None,'bars':{},'targets':{}}
            def failed(*a,**kw):
                e=ValueError('strict source guard');e.account_failure_state={'owned_shares':{'SH600001':100},'cash':'100.00'};raise e
            with self.assertRaisesRegex(ValueError,'strict source guard'):r.execute(auth,out,simulation=failed)
            v=r.r.read(out/'terminal.json');self.assertFalse(v['complete']);self.assertFalse(v['portfolio_return_computed']);self.assertTrue((out/'failed_account_state.json').exists());self.assertFalse((out/'results.json').exists())
