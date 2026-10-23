from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import hashlib,json
try:
    from scripts import inspect_cash_accrual_wrapped_corpus as r
except ImportError:r=None
from scripts import inspect_cash_accrual_corpus as v1
from tests import test_cash_accrual_corpus as fixtures
from tests.test_annual_cash_accruals_v2 import wrapped
from stock_rsi import annual_profitability as gp
from tests.test_annual_cash_accruals import DOC,source

class CashAccrualWrappedCorpusTests(TestCase):
    def setUp(self):
        self.assertIsNotNone(r,'wrapped whole-corpus source runner missing');f=fixtures.CashAccrualCorpusTests('run');f.setUp();self.addCleanup(f.doCleanups);self.base=f.base;self.docs=f.docs;self.known=f.known;self.req={**f.req,'expected_V1_supported_reports':5}
        for d in self.docs:self.freeze_v1(d)
    def update(self,p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value));self.known[str(p.resolve())]=v1.sha(p)
    def freeze_v1(self,d):
        case=v1.inspect_one(self.base,d,None,self.known);self.update(self.base/v1.OUTPUT/'cases'/(d['capture_key']+'.json'),case);return case
    def change_to_wrapped(self,i=0,cfo_missing=False):
        d=self.docs[i];_,old,cache=v1.case_paths(self.base,d);p=v1.read(cache);p['pages']=wrapped()
        if cfo_missing:p['pages'][4]=p['pages'][4].replace('经营活动产生的现金流量净额','缺失现金流字段')
        self.update(cache,p);prior=v1.read(old);prior['all_extracted_page_text_sha256']={str(j+1):hashlib.sha256(t.encode()).hexdigest() for j,t in enumerate(p['pages'])};self.update(old,prior);self.freeze_v1(d);self.req['expected_V1_supported_reports']-=1
    def inspect(self,i=0):return r.inspect_one(self.base,self.docs[i],None,self.known)
    def execute(self,worker=None,out=None):return r.execute(self.req,self.known,out or self.base/'out',self.base,worker=worker or r.inspect_one,executor_factory=ThreadPoolExecutor)
    def test_old_report_and_digest_preserved_identically(self):
        c=self.inspect();old=v1.read(self.base/v1.OUTPUT/'cases'/'SYNTHETIC-0.json');self.assertEqual(c['report'],old['report']);self.assertEqual(c['source_parser_variant'],'V1_PRESERVED');self.assertEqual(c['v1_source_case_sha256'],self.known[str((self.base/v1.OUTPUT/'cases'/'SYNTHETIC-0.json').resolve())])
    def test_wrapped_failure_recovers_source_only_with_explicit_contract(self):
        self.change_to_wrapped();case=self.inspect();self.assertEqual(case['status'],r.SUPPORTED);self.assertEqual(case['source_parser_variant'],'V2_RECOVERED_LABEL');self.assertEqual(case['v1_source_status'],r.UNSUPPORTED);self.assertEqual(case['report']['contract'],r.cash.CONTRACT);self.assertEqual(case['report']['parsed']['income']['2023-12-31']['net_profit']['value_CNY'],'-5.00')
    def test_unmodified_actual_buffers_and_original_case_reproduction_required(self):
        p=self.base/v1.OUTPUT/'cases'/'SYNTHETIC-0.json';case=v1.read(p);case['publication_day']='2024-04-26';self.update(p,case)
        with self.assertRaisesRegex(ValueError,'V1'):self.inspect()
    def test_cover_and_unsupported_remain_missing_and_metadata_is_native(self):
        d=self.docs[0];_,old,_=v1.case_paths(self.base,d);c=v1.read(old);c['cover_code_consistent']=False;self.update(old,c);self.freeze_v1(d);case=self.inspect();self.assertEqual(case['status'],'COVER_IDENTITY_UNVERIFIED');self.assertIsNone(case['report']);self.docs[0]['day']='2023-04-27'
        with self.assertRaises(ValueError):self.inspect()
    def test_missing_cfo_cannot_hide_protected_assets_or_fabricate_report(self):
        self.change_to_wrapped(cfo_missing=True);self.assertIsNone(self.inspect()['report']);_,prior,_=v1.case_paths(self.base,self.docs[0]);c=v1.read(prior);cells=gp.parse_consolidated_tables(source(),2023);obs=gp.make_observation('SH600001',2023,'2022-12-31','2024-04-27',DOC['captured_at_utc'],self.docs[0]['source_sha256'],DOC['announcement_id'],cells['2022-12-31']);obs['payload']['cells']['total_assets']['value_CNY']='999.00';obs['record_id']=v1.digest({k:v for k,v in obs.items() if k!='record_id'});c['source_observations']=[obs];self.update(prior,c)
        with self.assertRaisesRegex(ValueError,'protected'):self.inspect()
    def test_whole_batch_preserves_all_old_successes_and_source_only_flags(self):
        self.change_to_wrapped();t=self.execute();self.assertTrue(t['complete']);self.assertEqual(t['summary']['V1_supported_reports_preserved_identically'],4);self.assertEqual(t['summary']['V2_wrapped_reports_recovered'],1);self.assertEqual(t['summary']['raw_monetary_cells'],30);self.assertFalse(t['ratios_rankings_or_returns_computed']);self.assertFalse(t['objective_achieved']);self.assertEqual(t['pending'],[])
    def test_worker_relabelled_report_and_missing_old_success_stop(self):
        self.change_to_wrapped()
        def forged(*a):
            case=r.inspect_one(*a)
            if case['report']['contract']==r.cash.CONTRACT:case['report']['contract']=v1.cash.CONTRACT
            return case
        with self.assertRaises(ValueError):self.execute(forged)
        self.assertFalse(v1.read(self.base/'out/terminal.json')['complete'])
        case=self.inspect(1);case.update(status=r.UNSUPPORTED,report=None,source_parser_variant='V2_STILL_UNSUPPORTED')
        with self.assertRaises(ValueError):r.validate_case(case,self.docs[1],self.base,self.known)
    def test_native_failure_drains_all_submitted_peers_and_no_next_batch(self):
        seen=[]
        def worker(base,doc,norm,known):
            seen.append(doc['capture_key'])
            if doc['capture_key']=='SYNTHETIC-0':raise ValueError('native first peer error')
            return r.inspect_one(base,doc,norm,known)
        with self.assertRaisesRegex(ValueError,'native first peer'):self.execute(worker)
        t=v1.read(self.base/'out/terminal.json');self.assertFalse(t['complete']);self.assertEqual(len(seen),4);self.assertEqual(t['completed_documents'],3);self.assertEqual(t['failed_row_index'],0);self.assertEqual(t['unsubmitted_keys'],['SYNTHETIC-4'])
    def test_input_and_output_mutations_retained(self):
        for kind in ('input','output'):
            with self.subTest(kind=kind),TemporaryDirectory() as t:
                out=Path(t)/'out';raw=self.base/self.docs[0]['source_path'];old=raw.read_bytes();persist=r.persist
                def altered(out,name,value,outputs):
                    persist(out,name,value,outputs)
                    if name=='cases/SYNTHETIC-0.json':(raw if kind=='input' else out/name).write_bytes(b'changed')
                with patch.object(r,'persist',side_effect=altered),self.assertRaises(ValueError):self.execute(out=out)
                terminal=v1.read(out/'terminal.json');self.assertFalse(terminal['complete']);self.assertFalse(terminal['ratios_rankings_or_returns_computed']);raw.write_bytes(old)
    def test_setup_and_terminal_publication_errors_retain_failure(self):
        out=self.base/'out';raw=self.base/self.docs[0]['source_path'];mkdir=Path.mkdir
        def removed(path,*a,**kw):
            mkdir(path,*a,**kw)
            if path==out:raw.unlink()
        with patch.object(Path,'mkdir',removed),self.assertRaises(FileNotFoundError):self.execute()
        self.assertFalse(v1.read(out/'terminal.json')['complete'])
    def test_after_atomic_terminal_mutation_not_complete(self):
        raw=self.base/self.docs[0]['source_path'];replace=r.os.replace
        def altered(src,dst):
            replace(src,dst)
            if Path(src).name=='.terminal-pending.json':raw.write_bytes(b'changed')
        with patch.object(r.os,'replace',side_effect=altered),self.assertRaises(ValueError):self.execute()
        t=v1.read(self.base/'out/terminal.json');self.assertFalse(t['complete']);self.assertFalse(t['all_inputs_unchanged']);self.assertFalse(t['ratios_rankings_or_returns_computed'])
