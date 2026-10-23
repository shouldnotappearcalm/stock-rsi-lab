from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import inspect_operating_corpus_source as build
except ImportError:
    build=None
from tests.test_annual_operating import source
from tests.test_industry_catalog import bundle


class OperatingCorpusRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build,'complete operating source runner missing')
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)
        self.docs=[];self.paths={};cases={}
        for i in range(5):
            year=2017 if i==4 else 2023;raw=self.base/f'original-{i}.pdf';raw.write_bytes(b'%PDF-SYNTHETIC-OP-'+str(i).encode())
            doc={'capture_key':f'SYNTHETIC-{i}','instrument':'SH600030' if i==3 else 'SH600001',
                 'effective_fiscal_year':year,'fiscal_year':year,'year_resolved_from_cover_sidecar':False,
                 'day':['2024-04-29','2024-05-29','2024-06-29','2024-07-29','2024-07-30'][i],
                 'captured_at_utc':'2026-10-22T00:00:00+00:00','source_sha256':build.sha(raw),
                 'source_path':raw.name,'announcement_id':str(123456+i),
                 'source_phase':'INITIAL_AUTHENTICATED_PAGE_CACHE' if i%2==0 else 'LATER_ORIGINAL_PDF'}
            pages=[f'公司代码：{doc["instrument"][2:]}\n{year}年年度报告',*source(year,admin='-5.00' if i==4 else '5.00')]
            if i==1:pages[3]=pages[3].replace('管理费用 七、64 5.00 2.00\n','')
            if i==2:pages[1]=pages[1].replace('项目 附注 2023年12月31日 2022年12月31日','项目 期末余额 期初余额')
            if i==3:pages[0]=f'公司代码：600002\n{year}年年度报告'
            from scripts import inspect_profitability_all_v6 as legacy
            old=legacy.inspect_pages(doc,pages,build.op.CAS19_REFERENCE);cases[doc['capture_key']]=old
            folder=build.INITIAL_CACHE if i%2==0 else build.LATER_CACHE
            cache=self.base/folder/(doc['capture_key']+'.pages.json');cache.parent.mkdir(parents=True,exist_ok=True)
            build.write_once(cache,{'source_sha256':doc['source_sha256'],'extractor':'pypdf6.10.0','pages':pages})
            parent=self.base/build.PARENT_OUTPUT/(doc['capture_key']+'.json');parent.parent.mkdir(parents=True,exist_ok=True);build.write_once(parent,old)
            for p in (raw,cache,parent):self.paths['source/'+str(p.relative_to(self.base))]=p
            self.docs.append(doc)
        parent=self.base/build.PARENT_OUTPUT/'case_results.json';build.write_once(parent,cases);self.paths['source/'+build.PARENT_OUTPUT+'/case_results.json']=parent
        catalog=self.base/build.INDUSTRY_OUTPUT/'catalog.json';catalog.parent.mkdir(parents=True);build.write_once(catalog,bundle());self.paths['source/'+build.INDUSTRY_OUTPUT+'/catalog.json']=catalog
        self.req={'documents':self.docs,'normative_basis':build.op.CAS19_REFERENCE,
            'cohort':['SH600001','SH600030','SZ000998'],'formations':[
                {'execution_session':'2024-05-06','as_of':'2024-04-30T15:05:00+08:00'},
                {'execution_session':'2024-07-01','as_of':'2024-06-28T15:05:00+08:00'},
                {'execution_session':'2024-08-01','as_of':'2024-07-31T15:05:00+08:00'}],
            'modes':[build.op.OBSERVED,build.op.RECONSTRUCTED],
            'input_sha256':{k:build.sha(p) for k,p in self.paths.items()}}
        self.request=self.base/'request.json';build.write_once(self.request,self.req);self.reqsha=build.sha(self.request)

    def run_source(self,worker=None):
        with patch.object(build,'verify',return_value=(self.req,self.paths)):
            return build.run(self.base,self.base,self.base/'membership',self.request,self.reqsha,
                executor_factory=ThreadPoolExecutor,worker=worker or build.inspect_one)

    def test_complete_cases_both_caches_failed_latest_and_older_reissue_are_retained(self):
        summary=self.run_source();self.assertEqual(summary['document_count'],5)
        self.assertEqual(summary['status_counts'],{build.SUPPORTED:2,'OPERATING_SOURCE_SCHEMA_UNSUPPORTED':2,'COVER_IDENTITY_UNVERIFIED':1})
        self.assertEqual(summary['source_report_count'],2);self.assertEqual(len(summary['queries']),6)
        self.assertEqual(summary['observed_visible_annual_rows'],0)
        out=self.base/build.OUTPUT;cases=build.read(out/'case_results.json')
        self.assertEqual(cases['SYNTHETIC-4']['fiscal_year'],2017)
        self.assertEqual(cases['SYNTHETIC-4']['operating_report']['payload']['parsed']['income']['2017-12-31']['administrative_expenses']['value_CNY'],'-5.00')
        view=build.read(out/'2024-08-01-RECONSTRUCTED_PUBLICATION_DAY_END.json')
        self.assertEqual(view['classifications'][0]['selected_capture_key'],'SYNTHETIC-2')
        self.assertEqual(view['classifications'][0]['annual_status'],'LATEST_OPERATING_SOURCE_SCHEMA_UNSUPPORTED')
        self.assertNotIn('value_CNY',str(view));self.assertFalse(summary['investment_factor_admitted'])
        self.assertTrue(build.read(out/'terminal.json')['completed'])
        with self.assertRaises(ValueError):self.run_source()

    def test_cache_corruption_is_fatal_even_when_cover_identity_is_unverified(self):
        doc=self.docs[3];cache=self.base/build.LATER_CACHE/(doc['capture_key']+'.pages.json');data=build.read(cache)
        data['pages'][1]+=' changed';cache.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'cached pages'):build.inspect_one(str(self.base),doc,build.op.CAS19_REFERENCE)

    def test_old_GP_cell_disagreement_cannot_be_accepted_as_a_new_source_value(self):
        p=self.base/build.PARENT_OUTPUT/(self.docs[0]['capture_key']+'.json');old=build.read(p)
        old['source_observations'][0]['payload']['cells']['revenue']['value_CNY']='999.00';p.write_text(json.dumps(old))
        with self.assertRaises(ValueError):build.inspect_one(str(self.base),self.docs[0],build.op.CAS19_REFERENCE)

    def test_interrupt_preserves_prefix_original_error_and_mutation_postcheck(self):
        original=KeyboardInterrupt('operating source interrupted')
        def worker(base,doc,basis):
            if doc['capture_key']=='SYNTHETIC-1':
                (Path(base)/doc['source_path']).unlink();self.request.write_text('{}');raise original
            return build.inspect_one(base,doc,basis)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_source(worker)
        self.assertIs(caught.exception,original);out=self.base/build.OUTPUT;terminal=build.read(out/'terminal.json')
        self.assertFalse(terminal['completed']);self.assertEqual(terminal['completed_documents'],1)
        self.assertEqual(len(terminal['pending']),4)
        self.assertEqual({x['input'] for x in terminal['postcheck']['mismatches']},{'source/original-1.pdf','frozen_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_summary_write_interrupt_rechecks_inputs_and_never_publishes_completion(self):
        writer=build.write_once;original=KeyboardInterrupt('summary write interrupted')
        def interrupt(path,value):
            if path.name=='.summary-pending.json':
                path.write_text('{partial');self.request.write_text('{}');raise original
            writer(path,value)
        with patch.object(build,'write_once',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:self.run_source()
        self.assertIs(caught.exception,original);out=self.base/build.OUTPUT;terminal=build.read(out/'terminal.json')
        self.assertFalse(terminal['completed']);self.assertFalse(terminal['postcheck']['all_inputs_unchanged'])
        self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt');self.assertFalse((out/'summary.json').exists())


if __name__=='__main__':unittest.main()
