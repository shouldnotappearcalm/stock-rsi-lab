from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pypdf
from scripts import inspect_profitability_all_v6 as inspect
from tests.test_annual_profitability import pages


class WholeV6SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        old=self.base/inspect.initial.predecessor.OUTPUT;old.mkdir()
        self.documents=[];self.paths={};self.pages={};self.baselines=[{},{}]
        for i in range(5):
            year=2022 if i<2 else 2024 if i==3 else 2023
            raw=self.base/('source-'+str(i)+'.pdf');raw.write_bytes(b'%PDF-SYNTHETIC-'+str(i).encode())
            d={'capture_key':'SYNTHETIC-'+str(i),'instrument':'SH600001','fiscal_year':None if i==3 else year,
               'effective_fiscal_year':year,'year_resolved_from_cover_sidecar':i==3,
               'source_phase':'INITIAL_AUTHENTICATED_PAGE_CACHE' if i<2 else 'LATER_ORIGINAL_PDF',
               'day':str(year+1)+'-04-27','captured_at_utc':'2026-10-22T00:00:00+00:00',
               'source_sha256':inspect.file_sha(raw),'source_path':raw.name,'announcement_id':str(123456+i)}
            text=['公司代码：600001\n'+str(year)+'年年度报告',*pages(year)]
            if i==1:
                text=[p.replace('单位:元 币种:人民币','单位:元') for p in text]
                text.append('1、遵循企业会计准则的声明\n本财务报表符合企业会计准则的要求，真实、完整地反映了公司的财务状况。')
            self.pages[raw.name]=text;self.documents.append(d);self.paths['source/'+raw.name]=raw
            before=inspect.initial.predecessor.fixed.inspect_document({**d,'fiscal_year':year},text)
            before['all_extracted_page_text_sha256']={str(j+1):hashlib.sha256(t.encode()).hexdigest() for j,t in enumerate(text)}
            if i<2:
                for suffix,value in [('.json',before),('.pages.json',{'source_sha256':d['source_sha256'],'extractor':'pypdf6.10.0','pages':text})]:
                    path=old/(d['capture_key']+suffix);inspect.write_once(path,value);self.paths['source/'+inspect.initial.predecessor.OUTPUT+'/'+path.name]=path
            if i in (0,2):self.baselines[0 if i==0 else 1][d['capture_key']]=before
        self.request={'input_sha256':{k:inspect.file_sha(p) for k,p in self.paths.items()},
                      'normative_basis':inspect.grammar.CAS19_REFERENCE,'source_range_issuer_count':2}
        self.request_file=self.base/'request.json';inspect.write_once(self.request_file,self.request);self.sha=inspect.file_sha(self.request_file)

    def decode(self,path):return self.pages[Path(path).name]

    def run_inspection(self,worker=None,decoder=None):
        with patch.object(inspect,'verify',return_value=(self.request,self.paths,self.documents)),patch.object(
                inspect,'baseline_cases',return_value=self.baselines),patch.object(
                inspect.initial.predecessor.fixed,'pages_from_pdf',side_effect=self.decode if decoder is None else decoder):
            return inspect.run(self.base,self.base,self.base/'membership',self.request_file,self.sha,self.base/inspect.OUTPUT,
                executor_factory=ThreadPoolExecutor,**({} if worker is None else {'worker':worker}))

    def test_entire_source_set_cache_and_PDF_phases_keep_old_observations_and_cover_year(self):
        result=self.run_inspection()
        self.assertEqual(result['document_count'],5);self.assertEqual(result['source_observation_count'],10)
        self.assertEqual(result['new_page_caches_written'],3);self.assertEqual(result['old_supported_reports_preserved_identically'],2)
        self.assertEqual(result['regulatory_currency_inference_documents'],['SYNTHETIC-1'])
        self.assertFalse(result['investment_factor_admitted']);self.assertFalse(result['security_ranking_or_portfolio_returns_computed'])
        case=inspect.read(self.base/inspect.OUTPUT/'SYNTHETIC-3.json')
        self.assertIsNone(case['raw_capture_fiscal_year']);self.assertEqual(case['fiscal_year'],2024)
        self.assertTrue(case['year_resolved_from_cover_sidecar'])
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_inspection()

    def test_unreadable_new_PDF_is_an_explicit_case_with_no_financial_values(self):
        def failed(path):
            if Path(path).name=='source-4.pdf':raise pypdf.errors.PdfReadError('original unreadable PDF')
            return self.decode(path)
        result=self.run_inspection(decoder=failed)
        self.assertEqual(result['document_count'],5);self.assertEqual(result['status_counts']['SOURCE_PDF_EXTRACTION_UNSUPPORTED'],1)
        self.assertEqual(result['new_page_caches_written'],2)
        case=inspect.read(self.base/inspect.OUTPUT/'SYNTHETIC-4.json')
        self.assertEqual(case['source_observations'],[]);self.assertIsNone(case['page_count'])
        self.assertFalse(case['investment_factor_admitted'])

    def test_original_interrupt_stops_before_next_batch_and_rehashes_source_and_request(self):
        original=KeyboardInterrupt('whole corpus source interrupted')
        def failed(base,d,basis):
            if d['capture_key']=='SYNTHETIC-0':
                (self.base/d['source_path']).unlink();self.request_file.write_text('{}');raise original
            return inspect.inspect_one(base,d,basis)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_inspection(worker=failed)
        self.assertIs(caught.exception,original)
        out=self.base/inspect.OUTPUT;terminal=inspect.read(out/'terminal.json')
        self.assertEqual(len(terminal['submitted_keys']),4);self.assertEqual(terminal['completed_documents'],0)
        self.assertEqual({c['input'] for c in terminal['postcheck']['mismatches']},{'source/source-0.pdf','frozen_source_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_old_success_regression_retains_complete_cases_without_success_summary(self):
        def failed(base,d,basis):
            result,text=inspect.inspect_one(base,d,basis)
            if d['capture_key']=='SYNTHETIC-0':result.update(status='SOURCE_SCHEMA_UNSUPPORTED',source_observations=[])
            return result,text
        with self.assertRaisesRegex(ValueError,'old supported initial report lost'):self.run_inspection(worker=failed)
        out=self.base/inspect.OUTPUT;terminal=inspect.read(out/'terminal.json')
        self.assertEqual(terminal['completed_documents'],5);self.assertTrue(terminal['postcheck']['all_inputs_unchanged'])
        self.assertFalse((out/'summary.json').exists())


if __name__=='__main__':unittest.main()
