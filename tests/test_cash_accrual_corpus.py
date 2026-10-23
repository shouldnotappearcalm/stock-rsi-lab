from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib,json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
try:
    from scripts import inspect_cash_accrual_corpus as runner
except ImportError:runner=None
from tests.test_annual_cash_accruals import DOC,source
from stock_rsi import annual_profitability as old

class CashAccrualCorpusTests(TestCase):
    def setUp(self):
        self.assertIsNotNone(runner,'cash source cohort runner missing');t=TemporaryDirectory();self.addCleanup(t.cleanup);self.base=Path(t.name);self.docs=[];self.known={}
        for i in range(5):
            key='SYNTHETIC-'+str(i);raw=self.base/(key+'.pdf');raw.write_bytes(b'%PDF synthetic original '+str(i).encode());pages=source()
            d={**DOC,'capture_key':key,'source_path':raw.name,'source_sha256':runner.sha(raw),'source_phase':'INITIAL_AUTHENTICATED_PAGE_CACHE'};self.docs.append(d)
            prior=self.base/runner.parent.PARENT_OUTPUT/(key+'.json');cache=self.base/runner.parent.INITIAL_CACHE/(key+'.pages.json');prior.parent.mkdir(exist_ok=True);cache.parent.mkdir(exist_ok=True)
            case={'capture_key':key,'instrument':d['instrument'],'fiscal_year':2023,'source_sha256':d['source_sha256'],'cover_code_consistent':True,'cover_annual_year_consistent':True,'page_count':len(pages),'all_extracted_page_text_sha256':{str(j+1):hashlib.sha256(v.encode()).hexdigest() for j,v in enumerate(pages)},'source_observations':[]}
            prior.write_text(json.dumps(case));cache.write_text(json.dumps({'source_sha256':d['source_sha256'],'extractor':'pypdf6.10.0','pages':pages}))
            for p in (raw,prior,cache):self.known[str(p.resolve())]=runner.sha(p)
        self.req={'documents':self.docs,'cohort':['SH600001'],'normative_basis':None,'request_sha256':'synthetic'}
    def inspect(self,i=0):return runner.inspect_one(self.base,self.docs[i],None,self.known)
    def update(self,p,value):p.write_text(json.dumps(value));self.known[str(p.resolve())]=runner.sha(p)
    def test_real_adapter_preserves_current_prior_cells_and_cover_failures(self):
        c=self.inspect();self.assertEqual(c['status'],runner.SUPPORTED);self.assertEqual(c['report']['parsed']['income']['2023-12-31']['net_profit']['value_CNY'],'-5.00');self.assertEqual(c['source_page_cache_sha256'],self.known[str((self.base/runner.parent.INITIAL_CACHE/'SYNTHETIC-0.pages.json').resolve())])
        p=self.base/runner.parent.PARENT_OUTPUT/'SYNTHETIC-0.json';v=runner.read(p);v['cover_code_consistent']=False;self.update(p,v);c=self.inspect();self.assertEqual(c['status'],'COVER_IDENTITY_UNVERIFIED');self.assertIsNone(c['report'])
    def test_authenticated_actual_buffers_not_forged_cache_self_hashes(self):
        p=self.base/runner.parent.INITIAL_CACHE/'SYNTHETIC-0.pages.json';v=runner.read(p);v['pages'][2]=v['pages'][2].replace('-5.00','-6.00');p.write_text(json.dumps(v))
        with self.assertRaises(ValueError):self.inspect()
        self.known[str(p.resolve())]=runner.sha(p)
        with self.assertRaises(ValueError):self.inspect()
    def test_unsupported_new_fields_retained_but_protected_asset_disagreement_fatal(self):
        prior=self.base/runner.parent.PARENT_OUTPUT/'SYNTHETIC-0.json';v=runner.read(prior);cells=old.parse_consolidated_tables(source(),2023);obs=old.make_observation('SH600001',2023,'2023-12-31','2024-04-27',DOC['captured_at_utc'],self.docs[0]['source_sha256'],DOC['announcement_id'],cells['2023-12-31']);v['source_observations']=[obs];self.update(prior,v);self.assertEqual(self.inspect()['protected_asset_cells_compared'],1)
        v['source_observations'][0]['payload']['cells']['total_assets']['value_CNY']='999.00';v['source_observations'][0]['record_id']=runner.digest({k:x for k,x in v['source_observations'][0].items() if k!='record_id'});self.update(prior,v)
        with self.assertRaisesRegex(ValueError,'protected'):self.inspect()
    def execute(self,worker=None):return runner.execute(self.req,self.known,self.base/'out',self.base,worker=worker or runner.inspect_one,executor_factory=ThreadPoolExecutor)
    def test_complete_batch_success_is_source_only_no_financial_score(self):
        terminal=self.execute();self.assertTrue(terminal['complete']);self.assertEqual(terminal['completed_documents'],5);self.assertEqual(terminal['summary']['raw_monetary_cells'],30);self.assertFalse(terminal['ratios_rankings_or_returns_computed']);self.assertFalse(terminal['objective_achieved']);self.assertEqual(terminal['pending'],[])
    def test_native_worker_failure_drains_submitted_peers_and_never_starts_next_batch(self):
        seen=[]
        def worker(base,doc,norm,known):
            seen.append(doc['capture_key'])
            if doc['capture_key']=='SYNTHETIC-0':raise ValueError('native first peer failure')
            return runner.inspect_one(base,doc,norm,known)
        with self.assertRaisesRegex(ValueError,'native first peer failure'):self.execute(worker)
        t=runner.read(self.base/'out/terminal.json');self.assertFalse(t['complete']);self.assertEqual(len(seen),4);self.assertEqual(t['completed_documents'],3);self.assertEqual(t['unsubmitted_keys'],['SYNTHETIC-4']);self.assertEqual(len(t['failed_documents']),1);self.assertEqual(t['failed_row_index'],0)
    def test_worker_identity_forgery_never_published_as_supported(self):
        def worker(*args):v=runner.inspect_one(*args);v['instrument']='SZ000001';return v
        with self.assertRaises(ValueError):self.execute(worker)
        t=runner.read(self.base/'out/terminal.json');self.assertFalse(t['complete']);self.assertEqual(t['completed_documents'],0)
    def test_input_and_output_mutations_retain_failure_terminal(self):
        for mode in ('input','output'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                out=Path(folder)/'out';p=self.base/self.docs[0]['source_path'];original=p.read_bytes();persist=runner.persist
                def altered(out,name,value,outputs):
                    persist(out,name,value,outputs)
                    if name=='cases/SYNTHETIC-0.json':
                        if mode=='input':p.write_bytes(b'changed')
                        else:(out/name).write_text('changed')
                with patch.object(runner,'persist',side_effect=altered),self.assertRaises(ValueError):runner.execute(self.req,self.known,out,self.base,executor_factory=ThreadPoolExecutor)
                terminal=runner.read(out/'terminal.json');self.assertFalse(terminal['complete']);self.assertFalse(terminal['ratios_rankings_or_returns_computed']);p.write_bytes(original)
    def test_after_terminal_publication_mutation_cannot_claim_complete(self):
        real=runner.os.replace;p=self.base/self.docs[0]['source_path']
        def replace(src,dst):
            real(src,dst)
            if Path(src).name=='.terminal-pending.json':p.write_bytes(b'changed after publication')
        with patch.object(runner.os,'replace',side_effect=replace),self.assertRaises(ValueError):self.execute()
        terminal=runner.read(self.base/'out/terminal.json');self.assertFalse(terminal['complete']);self.assertFalse(terminal['all_inputs_unchanged']);self.assertFalse(terminal['ratios_rankings_or_returns_computed']);self.assertTrue((self.base/'out/terminal-rejected-published.json').exists())

    def test_forged_worker_source_buffer_provenance_is_rejected(self):
        def worker(*args):v=runner.inspect_one(*args);v['source_page_cache_sha256']='b'*64;return v
        with self.assertRaises(ValueError):self.execute(worker)
        self.assertFalse(runner.read(self.base/'out/terminal.json')['complete'])
    def test_input_disappearing_immediately_after_output_creation_retains_setup_failure(self):
        real=Path.mkdir;raw=self.base/self.docs[0]['source_path'];out=self.base/'out'
        def mkdir(path,*args,**kwargs):
            real(path,*args,**kwargs)
            if path==out:raw.unlink()
        with patch.object(Path,'mkdir',mkdir),self.assertRaises(FileNotFoundError):self.execute()
        terminal=runner.read(out/'terminal.json');self.assertFalse(terminal['complete']);self.assertEqual(terminal['prior_failure']['failed_stage'],'SETUP')

    def test_unsupported_cash_row_stays_failed_source_not_zero_filled(self):
        prior=self.base/runner.parent.PARENT_OUTPUT/'SYNTHETIC-0.json';cache=self.base/runner.parent.INITIAL_CACHE/'SYNTHETIC-0.pages.json';v=runner.read(cache);v['pages'][4]=v['pages'][4].replace('经营活动产生的现金流量净额','经营现金流未知口径');self.update(cache,v);old=runner.read(prior);old['all_extracted_page_text_sha256']={str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(v['pages'])};self.update(prior,old)
        case=self.inspect();self.assertEqual(case['status'],runner.UNSUPPORTED);self.assertIsNone(case['report']);self.assertIn('unique consolidated',case['error'])
