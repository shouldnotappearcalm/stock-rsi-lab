import copy
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-tax-proven-ledger-audit-v2.py'
if P.exists():
    s=importlib.util.spec_from_file_location('tax_proven_ledger_audit_v2',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
else:m=None

class PartialLedgerAuditTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(m,'independently reconstructed partial state required')
    def state(self):
        return {'last_clock':['2026-05-29',1],'cash':'10.0000','positions':{},'owned':{},
            'orders':[{'status':'PENDING'}],'fills':[],'cash_claims':[],'stock_claims':[],
            'corporate_ledger':[{'event_id':'old','quantity':2700}],'entitlements':{'old':2700}}
    def test_only_explicit_identity_mapping_is_permitted(self):
        original=self.state();current=copy.deepcopy(original)
        current['corporate_ledger'][0]['event_id']='new';current['entitlements']={'new':2700}
        self.assertTrue(m.check_partial_checkpoint(current,original,{'old':'new'}))
        self.assertEqual(original,self.state())
    def test_changed_cash_owned_lots_orders_claims_or_clock_cannot_hide_behind_flag(self):
        current=self.state();original=self.state()
        for key,value in [('cash','11.0000'),('owned',{'SH603737':1}),('positions',{'SH603737':[{'quantity':1}]}),
                          ('orders',[{'status':'FILLED'}]),('cash_claims',[{'net':'1'}]),
                          ('stock_claims',[{'quantity':540}]),('last_clock',['2026-06-01',0])]:
            wrong=copy.deepcopy(original);wrong[key]=value
            with self.subTest(key),self.assertRaises(AssertionError):m.check_partial_checkpoint(current,wrong,{})
    def test_ast_capture_is_a_separate_explicit_adaptation(self):
        _,changes=m.ledger_namespace()
        self.assertEqual(changes,{'policy':2,'24':4,'179':2,'485':1,'486':1,'lifecycle_loop':1,
            'return_state':1,'partial_loop':1,'partial_state_return':1,'partial_init':1})

if __name__=='__main__':unittest.main()
