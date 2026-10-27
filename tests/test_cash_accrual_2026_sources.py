from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib,json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from scripts import inspect_cash_accrual_2026_sources as r
from stock_rsi import annual_assets as assets
from tests.test_annual_cash_accruals import DOC,source

class Cash2026SourceTests(TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup);self.base=Path(t.name);self.docs=[];self.known={}
        for i in range(5):
            raw=self.base/f'{i}.pdf';raw.write_bytes(b'%PDF synthetic '+str(i).encode());d={**DOC,'instrument':f'SH{600001+i}','day':'2026-04-27','capture_key':f'SYNTHETIC-{i}','source_path':raw.name,'source_sha256':r.sha(raw)}
            self.known[str(raw.resolve())]=r.sha(raw);pages=source();cache={'source_sha256':d['source_sha256'],'extractor':'pypdf6.10.0','pages':pages}
            _,oldpath,cachepath=r.case_paths(self.base,d);self.update(cachepath,cache)
            report=assets.make_report(d['instrument'],2023,d['day'],d['captured_at_utc'],d['source_sha256'],d['announcement_id'],assets.parse_balance_only(pages,2023))
            c={'capture_key':d['capture_key'],'instrument':d['instrument'],'fiscal_year':2023,'publication_day':d['day'],'observed_at':d['captured_at_utc'],'source_sha256':d['source_sha256'],'page_count':len(pages),
               'source_page_cache_sha256':r.sha(cachepath),'all_extracted_page_text_sha256':{str(n+1):hashlib.sha256(v.encode()).hexdigest() for n,v in enumerate(pages)},'cover_code_consistent':True,'cover_annual_year_consistent':True,'asset_report':report}
            self.update(oldpath,c);self.docs.append(d)
        self.req={'documents':self.docs,'cohort':[d['instrument'] for d in self.docs],'normative_basis':None,'request_sha256':'a'*64}
    def update(self,p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v));self.known[str(p.resolve())]=r.sha(p)
    def inspect(self):return r.inspect_one(self.base,self.docs[0],None,self.known)
    def test_unchanged_parser_reads_signed_cells_and_protects_old_asset_values(self):
        c=self.inspect();self.assertEqual(c['status'],r.SUPPORTED);self.assertEqual(c['protected_asset_cells_compared'],2)
        self.assertEqual(c['report']['parsed']['income']['2023-12-31']['net_profit']['value_CNY'],'-5.00')
    def test_missing_cash_field_cannot_hide_asset_disagreement(self):
        d=self.docs[0];_,p,cache=r.case_paths(self.base,d);v=r.read(p);record=v['asset_report'];record['payload']['balances']['2023-12-31']['value_CNY']='999.00';record['record_id']=r.digest({k:x for k,x in record.items() if k!='record_id'});self.update(p,v)
        c=r.read(cache);c['pages'][4]=c['pages'][4].replace('经营活动产生的现金流量净额','缺失字段');self.update(cache,c);v['source_page_cache_sha256']=r.sha(cache);v['all_extracted_page_text_sha256']={str(n+1):hashlib.sha256(x.encode()).hexdigest() for n,x in enumerate(c['pages'])};self.update(p,v)
        with self.assertRaisesRegex(ValueError,'protected'):self.inspect()
    def test_unknown_fiscal_cover_stays_missing_not_invented_current_year(self):
        d=self.docs[0];d['effective_fiscal_year']=None;_,p,_=r.case_paths(self.base,d);v=r.read(p);v.update(fiscal_year=None,cover_annual_year_consistent=False,asset_report=None);self.update(p,v)
        c=self.inspect();self.assertIsNone(c['fiscal_year']);self.assertEqual(c['status'],'COVER_IDENTITY_UNVERIFIED');self.assertIsNone(c['report'])
    def test_future_monetary_callback_not_invoked_and_metadata_invalid_is_native(self):
        d=self.docs[0]
        def poison():raise AssertionError('future financial payload')
        self.assertIsNone(r.cash.visible_report(d,'2026-04-27T15:05:00+08:00',poison,r.cash.RECONSTRUCTED))
        d['captured_at_utc']='2026-04-01T00:00:00+00:00'
        with self.assertRaises(ValueError):self.inspect()
    def test_whole_source_only_completion_and_peer_failure_draining(self):
        t=r.execute(self.req,self.known,self.base/'out',self.base,executor_factory=ThreadPoolExecutor);self.assertTrue(t['complete']);self.assertEqual(t['summary']['raw_monetary_cells'],30);self.assertFalse(t['ratios_rankings_or_returns_computed'])
        seen=[]
        def worker(base,doc,norm,known):
            seen.append(doc['capture_key'])
            if doc['capture_key']=='SYNTHETIC-0':raise ValueError('native worker failure')
            return r.inspect_one(base,doc,norm,known)
        with self.assertRaises(ValueError):r.execute(self.req,self.known,self.base/'failed',self.base,worker=worker,executor_factory=ThreadPoolExecutor)
        t=r.read(self.base/'failed/terminal.json');self.assertFalse(t['complete']);self.assertEqual(len(seen),4);self.assertEqual(t['completed_documents'],3)
