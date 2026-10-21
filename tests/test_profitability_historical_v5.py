from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import hashlib

from scripts import inspect_profitability_historical_v5 as inspect
from tests.test_annual_profitability import pages


class HistoricalV5InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.source=self.base/'source.pdf';self.source.write_bytes(b'SYNTHETIC source')
        self.old=self.base/inspect.predecessor.OUTPUT;self.old.mkdir()
        self.documents=[];self.paths={'source/source.pdf':self.source};cases={}
        for i in range(3):
            d={'capture_key':'SYNTHETIC-'+str(i),'instrument':'SH600001','fiscal_year':2022,
               'day':'2023-04-27','captured_at_utc':'2026-10-22T00:00:00+00:00','source_sha256':inspect.file_sha(self.source),
               'source_path':'source.pdf','announcement_id':str(123456+i)}
            text=['公司代码：600001\n2022年年度报告',*pages(2022)]
            if i:
                text=[p.replace('单位:元 币种:人民币','单位:元').replace('七、61','61') for p in text]
                text.append('本公司编制本财务报表时所采用的货币为人民币。')
            case=inspect.predecessor.fixed.inspect_document(d,text)
            case['all_extracted_page_text_sha256']={str(j+1):hashlib.sha256(p.encode()).hexdigest() for j,p in enumerate(text)}
            for suffix,value in [('.json',case),('.pages.json',{'extractor':'pypdf6.10.0','source_sha256':d['source_sha256'],'pages':text})]:
                path=self.old/(d['capture_key']+suffix);inspect.write_once(path,value)
                self.paths['source/'+inspect.predecessor.OUTPUT+'/'+path.name]=path
            self.documents.append(d);cases[d['capture_key']]=case
        inspect.write_once(self.old/'case_results.json',cases)
        self.paths['source/'+inspect.predecessor.OUTPUT+'/case_results.json']=self.old/'case_results.json'
        self.request={'input_sha256':{k:inspect.file_sha(p) for k,p in self.paths.items()},
                      'source_range_issuer_count':2,'remaining_source_gap_issuers':['SZ001286']}
        self.request_file=self.base/'request.json';inspect.write_once(self.request_file,self.request)
        self.sha=inspect.file_sha(self.request_file)

    def run_inspection(self, inspector=None):
        with patch.object(inspect,'verify',return_value=(self.request,self.paths,self.documents)):
            return inspect.run(self.base,self.base,self.source,self.request_file,self.sha,self.base/inspect.OUTPUT,inspector=inspector)

    def test_all_versions_same_old_observations_and_new_support_without_factor_admission(self):
        result=self.run_inspection()
        self.assertEqual(result['document_count'],3)
        self.assertEqual(result['all_V4_supported_reports_preserved_identically'],1)
        self.assertEqual(result['newly_supported_documents'],['SYNTHETIC-1','SYNTHETIC-2'])
        self.assertEqual(result['remaining_source_gap_issuers'],['SZ001286'])
        self.assertEqual(result['source_observation_count'],6)
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['historical_arrival_verified'])
        self.assertFalse(result['security_ranking_or_portfolio_returns_computed'])
        self.assertFalse(result['2026_financial_or_market_values_read'])
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_inspection()

    def test_corrupt_page_cache_does_not_produce_a_supported_case(self):
        def corrupt(base,d):
            if d['capture_key']=='SYNTHETIC-0':
                path=self.old/(d['capture_key']+'.pages.json');value=inspect.read(path)
                value['pages'][0]+='changed';path.write_text(__import__('json').dumps(value))
            return inspect.inspect_cached_document(base,d)
        with self.assertRaisesRegex(ValueError,'original source/page text identity'):self.run_inspection(corrupt)
        out=self.base/inspect.OUTPUT;terminal=inspect.read(out/'terminal.json')
        self.assertEqual(terminal['completed_documents'],0)
        self.assertFalse(terminal['postcheck']['all_inputs_unchanged'])
        self.assertFalse((out/'summary.json').exists())

    def test_original_interrupt_is_preserved_alongside_changed_input_and_request(self):
        original=KeyboardInterrupt('cached source interrupted')
        def interrupted(base,d):
            self.source.unlink();self.request_file.write_text('{}');raise original
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_inspection(interrupted)
        self.assertIs(caught.exception,original)
        out=self.base/inspect.OUTPUT;terminal=inspect.read(out/'terminal.json')
        self.assertEqual({x['input'] for x in terminal['postcheck']['mismatches']},{'source/source.pdf','frozen_source_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_old_success_regression_retains_cases_but_refuses_successful_summary(self):
        def regression(base,d):
            result=inspect.inspect_cached_document(base,d)
            if d['capture_key']=='SYNTHETIC-0':result.update(status='SOURCE_SCHEMA_UNSUPPORTED',source_observations=[])
            return result
        with self.assertRaisesRegex(ValueError,'old supported initial report lost'):self.run_inspection(regression)
        out=self.base/inspect.OUTPUT;terminal=inspect.read(out/'terminal.json')
        self.assertEqual(terminal['completed_documents'],3)
        self.assertTrue(terminal['postcheck']['all_inputs_unchanged'])
        self.assertFalse((out/'summary.json').exists())


if __name__=='__main__':unittest.main()
