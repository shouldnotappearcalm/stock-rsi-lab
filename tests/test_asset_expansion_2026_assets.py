import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.test_annual_profitability import pages


class Asset2026ExtractionTests(unittest.TestCase):
    def setUp(self):self.m=importlib.import_module('scripts.inspect_asset_expansion_2026_assets')

    def doc(self,year=2025):
        return {'key':'SH600001-123','instrument':'SH600001','announcement_id':'123',
            'metadata_fiscal_year':year,'day':'2026-04-28','captured_at_utc':'2026-10-23T01:00:00+00:00',
            'source_sha256':'a'*64,'source_path':'synthetic.pdf'}

    def source(self):return ['公司代码：600001\n2025年年度报告',*pages(2025)]

    def test_same_grammar_extracts2025_assets_without_income_values_or_admission(self):
        source=self.source();source[3]=source[3].replace('其中：营业成本 70.00 60.00','无法识别的营业成本')
        before=copy.deepcopy(source);result=self.m.inspect_pages(self.doc(),source,self.m.assets.CAS19_REFERENCE)
        self.assertEqual(result['status'],'ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA')
        self.assertEqual(set(result['asset_report']['payload']['balances']),{'2025-12-31','2024-12-31'})
        self.assertEqual(result['asset_report']['payload']['balances']['2025-12-31']['value_CNY'],'200.00')
        self.assertEqual(source,before);self.assertFalse(result['investment_factor_admitted'])

    def test_wrong_cover_blocks_all_numeric_interpretation(self):
        source=self.source();source[0]='公司代码：600002\n2025年年度报告'
        with patch.object(self.m.assets,'parse_balance_only',side_effect=AssertionError('must not parse')):
            result=self.m.inspect_pages(self.doc(),source,self.m.assets.CAS19_REFERENCE)
        self.assertEqual(result['status'],'COVER_IDENTITY_UNVERIFIED');self.assertIsNone(result['asset_report'])

    def test_unknown_cover_year_is_literal_not_publication_minus_one_and_ambiguity_fails(self):
        result=self.m.inspect_pages(self.doc(None),self.source(),self.m.assets.CAS19_REFERENCE)
        self.assertEqual(result['fiscal_year'],2025);self.assertTrue(result['year_resolved_from_literal_cover'])
        source=self.source();source[0]+='\n2024年年度报告'
        result=self.m.inspect_pages(self.doc(None),source,self.m.assets.CAS19_REFERENCE)
        self.assertEqual(result['status'],'COVER_IDENTITY_UNVERIFIED');self.assertIsNone(result['asset_report'])

    def test_generic_opening_is_not_relabelled_prior_december_and_currency_conflict_fails(self):
        source=self.source();source[1]=source[1].replace('项目 附注 2025年12月31日 2024年12月31日','项目 期末余额 期初余额')
        result=self.m.inspect_pages(self.doc(),source,self.m.assets.CAS19_REFERENCE)
        self.assertEqual(set(result['asset_report']['payload']['balances']),{'2025-12-31'})
        source=self.source();source[1]=source[1].replace('币种:人民币','币种:港币')
        result=self.m.inspect_pages(self.doc(),source,self.m.assets.CAS19_REFERENCE)
        self.assertEqual(result['status'],'ASSET_SOURCE_SCHEMA_UNSUPPORTED');self.assertIsNone(result['asset_report'])

    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);base=Path(temp.name)
        source=base/'old-source.bin';source.write_bytes(b'original')
        request=base/'request.json';request.write_text('{}')
        docs=[{**self.doc(),'key':'SYNTHETIC-'+str(i)} for i in range(400)]
        req={'documents':docs,'normative_basis':self.m.assets.CAS19_REFERENCE}
        return base,source,request,req,{source:self.m.sha(source),request:self.m.sha(request)}

    def worker(self,base,doc,norm):
        return {'capture_key':doc['key'],'source_sha256':doc['source_sha256'],'page_count':0,
            'status':'COVER_IDENTITY_UNVERIFIED','asset_report':None},None

    def test_runner_keeps_all400_failed_source_cases_without_manufacturing_reports(self):
        base,source,request,r,bound=self.fixture()
        with patch.object(self.m,'verify',return_value=(r,bound)),redirect_stdout(StringIO()):
            result=self.m.run(base,base,request,bound[request],base/self.m.OUTPUT,
                executor_factory=ThreadPoolExecutor,worker=self.worker)
        self.assertEqual(result['asset_report_count'],0);self.assertEqual(result['status_counts'],{'COVER_IDENTITY_UNVERIFIED':400})
        self.assertEqual(result['visibility_at_cutoff'][self.m.assets.OBSERVED]['count'],0)
        self.assertFalse(result['2026_ranks_or_portfolio_returns_computed'])
        with self.assertRaises(ValueError):self.m.run(base,base,request,bound[request],base/self.m.OUTPUT)

    def test_worker_interrupt_keeps_prefix_original_error_and_rehashes_deleted_inputs(self):
        base,source,request,r,bound=self.fixture();original=KeyboardInterrupt('original source interrupt')
        def interrupted(b,doc,n):
            if doc['key']=='SYNTHETIC-1':source.unlink();request.unlink();raise original
            return self.worker(b,doc,n)
        with patch.object(self.m,'verify',return_value=(r,bound)),redirect_stdout(StringIO()),self.assertRaises(KeyboardInterrupt) as caught:
            self.m.run(base,base,request,bound[request],base/self.m.OUTPUT,
                executor_factory=ThreadPoolExecutor,worker=interrupted)
        self.assertIs(caught.exception,original)
        terminal=json.loads((base/self.m.OUTPUT/'terminal.json').read_text())
        self.assertEqual(terminal['completed_resources'],1);self.assertEqual(len(terminal['submitted']),4)
        self.assertEqual(len(terminal['pending']),399);self.assertEqual(len(terminal['changed_original_inputs']),2)
        self.assertFalse((base/self.m.OUTPUT/'summary.json').exists())


if __name__=='__main__':unittest.main()
