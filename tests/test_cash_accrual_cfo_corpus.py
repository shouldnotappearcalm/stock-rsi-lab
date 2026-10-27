from concurrent.futures import ThreadPoolExecutor
import hashlib,json
from unittest import TestCase
from scripts import inspect_cash_accrual_cfo_corpus as r
from tests import test_cash_accrual_wrapped_corpus as fixtures

class CashAccrualCfoCorpusTests(TestCase):
    def setUp(self):
        f=fixtures.CashAccrualWrappedCorpusTests('run');f.setUp();self.addCleanup(f.doCleanups);self.f=f;self.base=f.base;self.known=f.known;self.docs=f.docs
        self.req={**f.req,'expected_V2_supported_reports':5}
        for d in self.docs:self.freeze(d)
    def freeze(self,d):
        c=r.previous.inspect_one(self.base,d,None,self.known);self.f.update(self.base/r.previous.OUTPUT/'cases'/(d['capture_key']+'.json'),c)
    def change(self):
        self.f.change_to_wrapped();d=self.docs[0];_,old,cache,_=r.previous.case_paths(self.base,d);p=r.read(cache)
        p['pages'][4]=p['pages'][4].replace('经营活动产生的现金流量净额','经营活动产生的现金流\n量净额')
        self.f.update(cache,p);c=r.read(old);c['all_extracted_page_text_sha256']={str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(p['pages'])}
        self.f.update(old,c);self.f.freeze_v1(d);self.freeze(d);self.req['expected_V2_supported_reports']=4
    def inspect(self):return r.inspect_one(self.base,self.docs[0],None,self.known)
    def test_every_prior_report_preserved_identically(self):
        c=self.inspect();old=r.read(self.base/r.previous.OUTPUT/'cases'/'SYNTHETIC-0.json')
        self.assertEqual(c['report'],old['report']);self.assertEqual(c['source_parser_variant'],'V2_PRESERVED')
    def test_cfo_wrapping_recovers_explicit_new_contract(self):
        self.change();c=self.inspect();self.assertEqual(c['source_parser_variant'],'V3_RECOVERED_CFO_LABEL');self.assertEqual(c['report']['contract'],r.cash.CONTRACT)
        self.assertEqual(c['report']['parsed']['cashflows']['2023-12-31']['operating_cashflow']['value_CNY'],'20.00')
    def test_original_buffers_or_protected_fields_cannot_change(self):
        self.change();c=self.inspect();c['protected_asset_cells_compared']+=1
        with self.assertRaises(ValueError):r.validate_case(c,self.docs[0],self.base,self.known)
        path=r.case_paths(self.base,self.docs[0])[-1];path.write_text('{}')
        with self.assertRaises(ValueError):self.inspect()
    def test_whole_corpus_preservation_and_source_flags(self):
        self.change();t=r.execute(self.req,self.known,self.base/'out',self.base,executor_factory=ThreadPoolExecutor)
        self.assertTrue(t['complete']);self.assertEqual(t['summary']['V2_supported_reports_preserved_identically'],4)
        self.assertEqual(t['summary']['V3_CFO_reports_recovered'],1);self.assertFalse(t['objective_achieved']);self.assertFalse(t['ratios_rankings_or_returns_computed'])
    def test_malformed_recovered_report_keeps_native_failure(self):
        self.change()
        def worker(*args):
            c=r.inspect_one(*args)
            if c['report']['contract']==r.cash.CONTRACT:c['report']['parsed']['cashflows']['2023-12-31']['operating_cashflow']['value_CNY']='0'
            return c
        with self.assertRaises(ValueError):r.execute(self.req,self.known,self.base/'out',self.base,worker=worker,executor_factory=ThreadPoolExecutor)
        self.assertFalse(r.read(self.base/'out/terminal.json')['complete'])
