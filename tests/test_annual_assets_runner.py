from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import inspect_annual_assets_source as build
except ImportError:
    build=None

from tests.test_annual_profitability import pages


class AnnualAssetsRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build,'annual-assets source runner missing')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        old=self.base/build.PARENT_OUTPUT;old.mkdir();self.docs=[];self.paths={};cases={}
        for i in range(4):
            raw=self.base/f'original-{i}.bin';raw.write_bytes(b'%PDF-SYNTHETIC-ASSET-'+str(i).encode())
            doc={'capture_key':f'SYNTHETIC-{i}','instrument':'SH600001','effective_fiscal_year':2023,
                'fiscal_year':2023,'year_resolved_from_cover_sidecar':False,
                'day':'2024-04-27','captured_at_utc':'2026-10-22T00:00:00+00:00',
                'source_sha256':build.sha(raw),'source_path':raw.name,'announcement_id':str(123456+i),
                'source_phase':'INITIAL_AUTHENTICATED_PAGE_CACHE' if i%2==0 else 'LATER_ORIGINAL_PDF'}
            source=['公司代码：600001\n2023年年度报告',*pages()]
            if i in (1,2):source[3]=source[3].replace('其中：营业成本 70.00 60.00','无法识别的成本版式')
            if i==2:source[1]=source[1].replace('项目 附注 2023年12月31日 2022年12月31日','项目 期末余额 期初余额')
            if i==3:source[0]='公司代码：600002\n2023年年度报告'
            from scripts import inspect_profitability_all_v6 as old_build
            case=old_build.inspect_pages(doc,source,build.assets.CAS19_REFERENCE)
            cases[doc['capture_key']]=case
            folder=self.base/build.INITIAL_CACHE if i%2==0 else self.base/build.LATER_CACHE;folder.mkdir(exist_ok=True)
            cache=folder/(doc['capture_key']+'.pages.json')
            build.write_once(cache,{'source_sha256':doc['source_sha256'],'extractor':'pypdf6.10.0','pages':source})
            path=old/(doc['capture_key']+'.json');build.write_once(path,case)
            for p in (raw,cache,path):self.paths['source/'+str(p.relative_to(self.base))]=p
            self.docs.append(doc)
        build.write_once(old/'case_results.json',cases);self.paths['source/'+build.PARENT_OUTPUT+'/case_results.json']=old/'case_results.json'
        self.req={'documents':self.docs,'normative_basis':build.assets.CAS19_REFERENCE,'old_GP_supported_reports':1,
            'old_GP_asset_cell_count':2,'cohort_count':1,'input_sha256':{k:build.sha(v) for k,v in self.paths.items()}}
        self.request=self.base/'request.json';build.write_once(self.request,self.req);self.reqsha=build.sha(self.request)

    def run_source(self,worker=None):
        with patch.object(build,'verify',return_value=(self.req,self.paths)):
            return build.run(self.base,self.base,self.base/'membership',self.request,self.reqsha,
                executor_factory=ThreadPoolExecutor,worker=worker or build.inspect_one)

    def test_old_assets_are_identical_new_balance_fields_ignore_income_failure_and_no_prior_is_invented(self):
        result=self.run_source();self.assertEqual(result['document_count'],4)
        self.assertEqual(result['old_GP_supported_reports_preserved'],1)
        self.assertEqual(result['asset_report_count'],3);self.assertEqual(result['asset_cell_count'],5)
        self.assertEqual(result['newly_supported_documents'],['SYNTHETIC-1','SYNTHETIC-2'])
        out=self.base/build.OUTPUT;cases=build.read(out/'case_results.json')
        self.assertEqual(set(cases['SYNTHETIC-2']['asset_report']['payload']['balances']),{'2023-12-31'})
        self.assertEqual(cases['SYNTHETIC-3']['status'],'COVER_IDENTITY_UNVERIFIED')
        self.assertEqual(result['observed_pre2026_reports_visible'],0)
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['portfolio_returns_computed'])
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_source()

    def test_original_interrupt_keeps_completed_prefix_and_rehashes_deleted_source_and_request(self):
        original=KeyboardInterrupt('assets source interrupted')
        def worker(base,doc,basis):
            if doc['capture_key']=='SYNTHETIC-1':
                (Path(base)/doc['source_path']).unlink();self.request.write_text('{}');raise original
            return build.inspect_one(base,doc,basis)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_source(worker)
        self.assertIs(caught.exception,original)
        terminal=build.read(self.base/build.OUTPUT/'terminal.json')
        self.assertEqual(terminal['completed_documents'],1);self.assertEqual(len(terminal['pending']),3)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},{'source/original-1.bin','frozen_request'})
        self.assertFalse((self.base/build.OUTPUT/'summary.json').exists())

    def test_corrupted_new_cache_cannot_be_downgraded_to_an_ordinary_schema_failure(self):
        def worker(base,doc,basis):
            if doc['capture_key']=='SYNTHETIC-1':
                p=Path(base)/build.LATER_CACHE/(doc['capture_key']+'.pages.json');data=build.read(p)
                data['pages'][1]+=' altered';p.write_text(__import__('json').dumps(data))
            return build.inspect_one(base,doc,basis)
        with self.assertRaisesRegex(ValueError,'authenticated cached pages'):self.run_source(worker)
        self.assertFalse((self.base/build.OUTPUT/'summary.json').exists())
        self.assertFalse(build.read(self.base/build.OUTPUT/'input-postcheck.json')['all_inputs_unchanged'])

    def test_loss_or_change_of_reused_legacy_asset_blocks_success(self):
        def worker(base,doc,basis):
            case=build.inspect_one(base,doc,basis)
            if doc['capture_key']=='SYNTHETIC-0':
                case['asset_report']['payload']['balances']['2023-12-31']['value_CNY']='999.00'
            return case
        with self.assertRaisesRegex(ValueError,'old audited asset cells'):self.run_source(worker)
        self.assertFalse((self.base/build.OUTPUT/'summary.json').exists())


if __name__=='__main__':unittest.main()
