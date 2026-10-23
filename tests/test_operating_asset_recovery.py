from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    from scripts import recover_operating_assets as build
except ImportError:
    build=None
from stock_rsi import annual_operating as op
from stock_rsi import operating_availability as availability
from stock_rsi.data import digest
from tests.test_operating_source_bridge import synthetic_inputs
from tests.test_industry_catalog import bundle


class OperatingAssetRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build,'prospective complete source recovery runner missing')
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)
        self.docs=[];self.original={};self.geometries={};self.paths={}
        from scripts import inspect_profitability_all_v6 as legacy
        for i in range(7):
            doc,texts,geo,_=synthetic_inputs();doc.update(capture_key=f'SYNTHETIC-{i}',announcement_id=str(123456+i),
                instrument=['SH600001','SH600001','SH600002','SH600005','SH600006','SH600003','SH600004'][i],
                day=['2024-04-29','2024-05-29','2025-07-01','2024-04-29','2024-04-29','2024-04-29','2024-04-29'][i],
                fiscal_year=2023,year_resolved_from_cover_sidecar=False,source_phase='INITIAL_AUTHENTICATED_PAGE_CACHE')
            raw=self.base/f'original-{i}.pdf';raw.write_bytes(b'%PDF-SYNTHETIC-BRIDGE-'+str(i).encode());doc['source_path']=raw.name;doc['source_sha256']=build.sha(raw)
            texts=[f'公司代码：{doc["instrument"][2:]}\n2023年年度报告',*texts]
            if i==1:texts[3]=texts[3].replace('研发费用 七、65 7.00 6.00\n','')
            if i==3:texts[-1]=texts[-1].replace('主要会计数据和财务指标','其他信息')
            gp=legacy.inspect_pages(doc,texts,op.CAS19_REFERENCE)
            for page in geo:page['physical_page']+=1;page['source_sha256']=doc['source_sha256']
            self.geometries[doc['capture_key']]=geo
            if i<5:original={'status':'OPERATING_SOURCE_SCHEMA_UNSUPPORTED','error':build.DATE_ERROR,'operating_report':None}
            elif i==5:original={'status':availability.SUPPORTED,'operating_report':op.make_report(doc['instrument'],2023,doc['day'],doc['captured_at_utc'],doc['source_sha256'],doc['announcement_id'],op.parse_report(texts,2023))}
            else:original={'status':'COVER_IDENTITY_UNVERIFIED','operating_report':None}
            original.update(capture_key=doc['capture_key'],instrument=doc['instrument'],fiscal_year=2023,source_sha256=doc['source_sha256'])
            self.original[doc['capture_key']]=original;self.docs.append(doc)
            for relative,value in ((build.GP_OUTPUT+'/'+doc['capture_key']+'.json',gp),
                (build.LEGACY_OUTPUT+'/'+doc['capture_key']+'.json',original),
                (build.INITIAL_CACHE+'/'+doc['capture_key']+'.pages.json',{'source_sha256':doc['source_sha256'],'extractor':'pypdf6.10.0','pages':texts})):
                path=self.base/relative;path.parent.mkdir(parents=True,exist_ok=True);build.write_once(path,value);self.paths['source/'+relative]=path
            self.paths['source/'+raw.name]=raw
        self.req={'documents':self.docs,'targets':[d['capture_key'] for d in self.docs[:5]],'normative_basis':build.geometry.NORMATIVE_BASIS,
          'cohort':sorted({d['instrument'] for d in self.docs}),'modes':[op.OBSERVED,op.RECONSTRUCTED],
          'formations':[{'execution_session':'2024-05-06','as_of':'2024-04-30T15:05:00+08:00'},
                        {'execution_session':'2024-06-03','as_of':'2024-05-31T15:05:00+08:00'}]}
        for formation in self.req['formations']:
            for mode in self.req['modes']:
                view=availability.snapshot_availability(self.docs,self.original.__getitem__,bundle(),self.req['cohort'],formation['as_of'],mode=mode)
                relative=build.LEGACY_OUTPUT+'/'+formation['execution_session']+'-'+mode+'.json';p=self.base/relative;build.write_once(p,view);self.paths['source/'+relative]=p
        self.req['input_sha256']={k:build.sha(p) for k,p in self.paths.items()};self.request=self.base/'request.json';build.write_once(self.request,self.req);self.reqsha=build.sha(self.request)

    def geometry_reader(self,pdf,pages,source_sha256,expected_page_count):
        key=next(d['capture_key'] for d in self.docs if self.base/d['source_path']==Path(pdf))
        known={p['physical_page']:p for p in self.geometries[key]}
        for number in pages:yield copy.deepcopy(known.get(number,{'physical_page':number,'width':600,'height':800,'source_sha256':source_sha256,'tables':[],'words':[]}))

    def inspect(self,base,doc,basis):
        return build.inspect_one(base,doc,basis)

    def run_source(self,worker=None):
        with patch.object(build,'verify',return_value=(self.req,self.paths)),patch.object(build,'extract_geometry',side_effect=self.geometry_reader):
            return build.run(self.base,self.base,self.base/'membership',self.request,self.reqsha,executor_factory=ThreadPoolExecutor,worker=worker or self.inspect)

    def test_locator_has_frozen_twenty_page_two_window_budget_and_no_guess_on_absence(self):
        texts=['']*24;texts[1]='主要会计数据 2022年末 总资产';texts[7]=texts[1];texts[22]=texts[1]
        self.assertEqual(build.candidate_pages(texts,2023,24),[1,2,7,8,24])
        self.assertEqual(build.candidate_pages(['']*24,2023,24),[])
        with self.assertRaises(ValueError):build.candidate_pages(texts,2023,25)

    def test_complete_corpus_preserves_legacy_partial_failures_and_latest_source_witnesses(self):
        summary=self.run_source();out=self.base/build.OUTPUT;cases=build.read(out/'case_results.json')
        self.assertEqual(len(cases),7);self.assertEqual(summary['target_documents_completed'],5)
        self.assertEqual(summary['effective_source_status_counts'],{build.bridge.SUPPORTED:2,build.bridge.STILL_UNSUPPORTED:4,build.bridge.LEGACY_SUPPORTED:1})
        self.assertEqual(cases['SYNTHETIC-1']['failure_stage'],'INCOME_SOURCE');self.assertIsNotNone(cases['SYNTHETIC-1']['asset_bridge'])
        self.assertEqual(cases['SYNTHETIC-2']['failure_stage'],'REGULATORY_VERSION');self.assertEqual(cases['SYNTHETIC-3']['failure_stage'],'SUMMARY_WINDOW_ABSENT')
        self.assertEqual(cases['SYNTHETIC-5']['effective_record_id'],self.original['SYNTHETIC-5']['operating_report']['record_id'])
        late=build.read(out/'2024-06-03-RECONSTRUCTED_PUBLICATION_DAY_END.json')['classifications'][0]
        self.assertEqual(late['selected_capture_key'],'SYNTHETIC-1');self.assertEqual(late['effective_source_status'],build.bridge.STILL_UNSUPPORTED)
        self.assertEqual(summary['observed_visible_annual_rows'],0);self.assertEqual(len(summary['queries']),4)
        self.assertFalse(summary['investment_factor_admitted']);self.assertNotIn('value_CNY',str(late))
        with self.assertRaises(ValueError):self.run_source()

    def test_later_regulatory_source_does_not_decode_or_extract_new_income(self):
        with patch.object(build,'extract_geometry',side_effect=AssertionError('unregistered source decode')):
            result=self.inspect(str(self.base),self.docs[2],build.geometry.NORMATIVE_BASIS)
        self.assertEqual(result['failure_stage'],'REGULATORY_VERSION');self.assertIsNone(result['source_record'])

    def test_cache_hash_or_protected_GP_value_corruption_is_fatal(self):
        doc=self.docs[0];path=self.base/build.INITIAL_CACHE/(doc['capture_key']+'.pages.json');data=build.read(path);data['pages'][1]+=' changed';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'cached'):self.inspect(str(self.base),doc,build.geometry.NORMATIVE_BASIS)
        path.write_text(json.dumps({**data,'pages':[t.replace(' changed','') for t in data['pages']]}))
        gp_path=self.base/build.GP_OUTPUT/(doc['capture_key']+'.json');gp=build.read(gp_path);gp['source_observations'][0]['payload']['cells']['revenue']['value_CNY']='999.00';gp_path.write_text(json.dumps(gp))
        with patch.object(build,'extract_geometry',side_effect=self.geometry_reader),self.assertRaises(ValueError):self.inspect(str(self.base),doc,build.geometry.NORMATIVE_BASIS)

    def test_first_failure_drains_three_submitted_peers_and_does_not_submit_fifth(self):
        barrier=threading.Barrier(4);original=RuntimeError('source worker failed after peers')
        def worker(base,doc,basis):
            if doc['capture_key']=='SYNTHETIC-0':barrier.wait(timeout=10);raise original
            result=self.inspect(base,doc,basis);barrier.wait(timeout=10);return result
        with self.assertRaises(RuntimeError) as caught:self.run_source(worker)
        self.assertIs(caught.exception,original);terminal=build.read(self.base/build.OUTPUT/'terminal.json')
        self.assertEqual(terminal['completed_target_documents'],3);self.assertEqual(terminal['unsubmitted_target_keys'],['SYNTHETIC-4'])
        self.assertEqual(terminal['failed_documents'][0]['capture_key'],'SYNTHETIC-0');self.assertFalse(terminal['completed'])
        self.assertEqual(len(build.read(self.base/build.OUTPUT/'case_results.json')),7)

    def test_interruption_preserves_original_error_partial_geometry_and_source_mutation(self):
        original=KeyboardInterrupt('interrupted source read');original.partial_geometry=[{'prefix':'uncommitted source witness'}]
        def worker(base,doc,basis):
            if doc['capture_key']=='SYNTHETIC-0':self.request.write_text('{}');raise original
            return self.inspect(base,doc,basis)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_source(worker)
        self.assertIs(caught.exception,original);out=self.base/build.OUTPUT;terminal=build.read(out/'terminal.json')
        self.assertFalse(terminal['postcheck']['all_inputs_unchanged']);self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt')
        self.assertTrue((out/'SYNTHETIC-0.partial-geometry.json').exists());self.assertFalse((out/'summary.json').exists())

    def test_geometry_interrupted_or_fatal_io_never_completes_source_run(self):
        reader=self.geometry_reader;original=InterruptedError('original source interrupted')
        def interrupted(pdf,pages,source_sha256,expected_page_count):
            if Path(pdf).name=='original-0.pdf':
                yield next(iter(reader(pdf,pages,source_sha256,expected_page_count)))
                raise original
            yield from reader(pdf,pages,source_sha256,expected_page_count)
        self.geometry_reader=interrupted
        with self.assertRaises(InterruptedError) as caught:self.run_source()
        self.assertIs(caught.exception,original);out=self.base/build.OUTPUT
        terminal=build.read(out/'terminal.json');self.assertFalse(terminal['completed'])
        self.assertEqual(terminal['original_error']['type'],'InterruptedError');self.assertFalse((out/'summary.json').exists())
        self.assertEqual(len(build.read(out/'SYNTHETIC-0.partial-geometry.json')['pages']),1)

    def test_summary_failure_rehashes_request_and_keeps_no_completed_summary(self):
        writer=build.write_once;original=KeyboardInterrupt('summary interrupted')
        def interrupt(path,value):
            if path.name=='.summary-pending.json':self.request.write_text('{}');raise original
            writer(path,value)
        with patch.object(build,'write_once',side_effect=interrupt),self.assertRaises(KeyboardInterrupt) as caught:self.run_source()
        self.assertIs(caught.exception,original);terminal=build.read(self.base/build.OUTPUT/'terminal.json')
        self.assertFalse(terminal['completed']);self.assertFalse(terminal['postcheck']['all_inputs_unchanged'])
        self.assertFalse((self.base/build.OUTPUT/'summary.json').exists())

    def test_initial_legacy_read_interrupt_still_rehashes_request_and_keeps_terminal(self):
        original=KeyboardInterrupt('legacy source read interrupted');reader=build.legacy_reference
        def interrupt(base,doc,targeted=False):
            if doc['capture_key']=='SYNTHETIC-1':self.request.write_text('{}');raise original
            return reader(base,doc,targeted)
        with patch.object(build,'legacy_reference',side_effect=interrupt),self.assertRaises(KeyboardInterrupt) as caught:self.run_source()
        self.assertIs(caught.exception,original);out=self.base/build.OUTPUT
        self.assertTrue((out/'terminal.json').exists(),'initial source reads must be inside the exit/postcheck guard')
        terminal=build.read(out/'terminal.json');self.assertFalse(terminal['completed']);self.assertFalse(terminal['postcheck']['all_inputs_unchanged'])


if __name__=='__main__':unittest.main()
