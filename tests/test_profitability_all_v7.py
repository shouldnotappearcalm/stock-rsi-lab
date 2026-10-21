from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import inspect_profitability_all_v7 as inspect
from tests.test_annual_profitability import pages


class CachedWholeV7Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.old=self.base/inspect.PREVIOUS_OUTPUT;self.old.mkdir();self.docs=[];self.paths={};old_cases={}
        for i in range(3):
            raw=self.base/f'source-{i}.bin';raw.write_bytes(b'%PDF-SYNTHETIC-'+str(i).encode())
            d={'capture_key':f'SYNTHETIC-{i}','instrument':'SH600001','fiscal_year':2024,'effective_fiscal_year':2024,
               'year_resolved_from_cover_sidecar':False,'day':'2025-04-27','captured_at_utc':'2026-10-22T00:00:00+00:00',
               'source_sha256':inspect.file_sha(raw),'source_path':raw.name,'announcement_id':str(123456+i),
               'source_phase':'INITIAL_AUTHENTICATED_PAGE_CACHE' if i==0 else 'LATER_ORIGINAL_PDF'}
            source=pages(2024)
            if i==1:source[0]=source[0].replace('项目 附注 2024年12月31日 2023年12月31日','项目 期末余额 期初余额')
            source.insert(0,'公司代码：600001\n2024年年度报告')
            case=inspect.prior.inspect_pages(d,source,inspect.grammar.CAS19_REFERENCE);old_cases[d['capture_key']]=case
            cache=self.base/inspect.INITIAL_CACHE_OUTPUT if i==0 else self.old;cache.mkdir(exist_ok=True)
            paths={self.old/(d['capture_key']+'.json'):case,cache/(d['capture_key']+'.pages.json'):{'source_sha256':d['source_sha256'],'extractor':'pypdf6.10.0','pages':source}}
            for path,value in paths.items():inspect.write_once(path,value);self.paths['source/'+str(path.relative_to(self.base))]=path
            self.paths['source/'+raw.name]=raw;self.docs.append(d)
        inspect.write_once(self.old/'case_results.json',old_cases);self.paths['source/'+inspect.PREVIOUS_OUTPUT+'/case_results.json']=self.old/'case_results.json'
        self.request={'input_sha256':{k:inspect.file_sha(p) for k,p in self.paths.items()},'normative_basis':inspect.grammar.CAS19_REFERENCE,
                      'old_supported_report_count':2,'source_range_issuer_count':1}
        self.request_file=self.base/'request.json';inspect.write_once(self.request_file,self.request);self.request_sha=inspect.file_sha(self.request_file)

    def run_source(self,worker=None):
        with patch.object(inspect,'verify',return_value=(self.request,self.paths,self.docs)):
            return inspect.run(self.base,self.base,self.base/'membership',self.request_file,self.request_sha,self.base/inspect.OUTPUT,
                executor_factory=ThreadPoolExecutor,**({} if worker is None else {'worker':worker}))

    def test_both_authenticated_cache_locations_keep_old_cells_and_add_only_current_generic_period(self):
        result=self.run_source()
        self.assertEqual(result['document_count'],3);self.assertEqual(result['source_observation_count'],5)
        self.assertEqual(result['old_supported_reports_preserved_identically'],2)
        self.assertEqual(result['newly_supported_documents'],['SYNTHETIC-1'])
        self.assertEqual(result['generic_balance_current_only_documents'],['SYNTHETIC-1'])
        self.assertEqual(result['original_PDF_text_decodings_performed'],0)
        self.assertFalse(result['investment_factor_admitted']);self.assertFalse(result['security_ranking_or_portfolio_returns_computed'])
        out=self.base/inspect.OUTPUT;self.assertFalse(any(out.glob('*.pages.json')))
        case=inspect.read(out/'SYNTHETIC-1.json');self.assertEqual([o['fiscal_end'] for o in case['source_observations']],['2024-12-31'])
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_source()

    def test_interrupt_preserves_original_and_rechecks_deleted_source_and_modified_request(self):
        original=KeyboardInterrupt('cached source interrupted')
        def failed(base,d,basis):
            if d['capture_key']=='SYNTHETIC-0':
                (self.base/d['source_path']).unlink();self.request_file.write_text('{}');raise original
            return inspect.inspect_one(base,d,basis)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_source(failed)
        self.assertIs(caught.exception,original)
        out=self.base/inspect.OUTPUT;terminal=inspect.read(out/'terminal.json')
        self.assertEqual(terminal['completed_documents'],0);self.assertEqual(len(terminal['submitted_keys']),3)
        self.assertEqual({m['input'] for m in terminal['postcheck']['mismatches']},{'source/source-0.bin','frozen_source_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_loss_of_old_success_blocks_summary_after_all_source_cases_are_retained(self):
        def failed(base,d,basis):
            c=inspect.inspect_one(base,d,basis)
            if d['capture_key']=='SYNTHETIC-0':c.update(status='SOURCE_SCHEMA_UNSUPPORTED',source_observations=[])
            return c
        with self.assertRaisesRegex(ValueError,'old supported report'):self.run_source(failed)
        out=self.base/inspect.OUTPUT;self.assertEqual(inspect.read(out/'terminal.json')['completed_documents'],3)
        self.assertTrue(inspect.read(out/'input-postcheck.json')['all_inputs_unchanged']);self.assertFalse((out/'summary.json').exists())

    def test_corrupted_cache_is_not_a_valid_source_even_if_current_file_is_readable(self):
        def corrupt(base,d,basis):
            if d['capture_key']=='SYNTHETIC-0':
                p=self.base/inspect.INITIAL_CACHE_OUTPUT/(d['capture_key']+'.pages.json');j=inspect.read(p);j['pages'][0]+=' changed';p.write_text(__import__('json').dumps(j))
            return inspect.inspect_one(base,d,basis)
        with self.assertRaisesRegex(ValueError,'authenticated cached page text'):self.run_source(corrupt)
        out=self.base/inspect.OUTPUT;self.assertFalse((out/'summary.json').exists())
        terminal=inspect.read(out/'terminal.json');self.assertFalse(terminal['postcheck']['all_inputs_unchanged'])


if __name__=='__main__':unittest.main()
