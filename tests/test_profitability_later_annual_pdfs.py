from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import capture_profitability_later_annual_pdfs as capture


class Response(BytesIO):
    def __init__(self,url,body):
        super().__init__(body);self.url,self.status=url,200
        self.headers={'Content-Type':'application/pdf','Content-Length':str(len(body))}


class LaterAnnualSelectionTests(unittest.TestCase):
    def row(self,title,identity='123456',day='2025-04-30'):
        stamp=int(datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=8))).timestamp()*1000)
        return {'title':title,'announcement_id':identity,'day':day,'timestamp_ms':stamp,'pdf_path':'finalpage/'+day+'/'+identity+'.PDF'}

    def test_all_source_backed_full_title_variants_remain_distinct_from_summaries_and_yearless(self):
        titles={'2023年年度报告（更新前）':2023,'2024年年度报告全文（更正后）':2024,
            '海南橡胶2017年年度报告（2024年4月修订版）':2017,'2024年年报报告（修订版）':2024,
            '鹏都农牧股份有限公司2023年年度报告（修正后）':2023,
            '雅戈尔时尚股份有限公司2024年年度报告（图文版）':2024,'600511_国药股份_2023年_年度报告':2023}
        for title,year in titles.items():
            with self.subTest(title=title):
                classified=capture.classify_title(title)
                self.assertIn('CANDIDATE',classified['kind']);self.assertEqual(classified['fiscal_year'],year)
        unknown=capture.classify_title('年报全文')
        self.assertEqual(unknown['kind'],'UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE');self.assertIsNone(unknown['fiscal_year'])
        for title in ('2024年年度报告摘要','2024 Annual Report','2024年年度报告（英文版）',
                      '2024年年度报告（可视版）','关于2024年年度报告的更正公告','2024年半年度报告','2026年年度报告'):
            with self.subTest(title=title):self.assertNotIn('CANDIDATE',capture.classify_title(title)['kind'])

    def test_all_editions_source_refs_and_yearless_gap_are_retained_without_preferred_version(self):
        cohort=['SH600001','SZ000001'];ref={'path':'metadata/a.json','sha256':'a'*64};ref2={'path':'metadata/b.json','sha256':'b'*64}
        rows=[('SH600001',self.row(title,str(100+i)),ref) for i,title in enumerate([
            '2023年年度报告','2023年年度报告（更新前）','2023年年度报告全文（更正后）','2023年年度报告（图文版）','年报全文'])]
        rows.append(('SH600001',rows[0][1],ref2))
        docs,inventory=capture.select_documents(cohort,rows,[])
        self.assertEqual(len(docs),5)
        original=next(d for d in docs if d['announcement_id']=='100')
        self.assertEqual(original['metadata_source_refs'],[ref,ref2])
        self.assertIsNone(docs[-1]['fiscal_year'])
        self.assertEqual(inventory['missing_explicit_fiscal_year_candidates_by_issuer']['2024'],cohort)
        self.assertEqual(inventory['missing_explicit_fiscal_year_candidates_by_issuer']['2023'],['SZ000001'])

    def test_conflicting_same_ID_wrong_date_path_or_cache_identity_fail_closed(self):
        ref={'path':'metadata/a.json','sha256':'a'*64};row=self.row('2024年年度报告')
        for changed in ({**row,'title':'2024年年度报告（更正后）'},{**row,'day':'2025-04-29'}):
            with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'conflicting original metadata'):
                capture.select_documents(['SH600001'],[('SH600001',row,ref),('SH600001',changed,ref)],[])
        for changed in ({**row,'day':'2025-04-29'},{**row,'pdf_path':'https://example.com/123456.PDF'}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                capture.select_documents(['SH600001'],[('SH600001',changed,ref)],[])
        bad_cache={**row,'instrument':'SH600002','fiscal_year':2024}
        with self.assertRaisesRegex(ValueError,'cached original metadata identity'):
            capture.select_documents(['SH600001'],[('SH600001',row,ref)],[bad_cache])


class LaterAnnualTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.old=self.base/'old.pdf';self.old.write_bytes(b'%PDF-SYNTHETIC old original')
        self.paths={'source/old.pdf':self.old};self.documents=[];self.calls=[]
        for i in range(5):
            d={'capture_key':'SYNTHETIC-'+str(i),'instrument':'SH600001','fiscal_year':None if i==1 else 2024,
               'url':'https://static.cninfo.com.cn/finalpage/2025-04-30/'+str(123456+i)+'.PDF',
               'source_kind':'REUSE_AUTHENTICATED_ORIGINAL_PDF' if i==0 else 'FRESH_FROZEN_PDF_GET'}
            if i==0:d.update(source_path='old.pdf',source_sha256=capture.file_sha(self.old))
            self.documents.append(d)
        self.request={'documents':self.documents,'resources':capture.resources(self.documents),'cache_reuse_count':1,
                      'source_inventory':{'yearless_source_candidates':['SYNTHETIC-1']},
                      'input_sha256':{k:capture.file_sha(p) for k,p in self.paths.items()}}
        self.request_file=self.base/'request.json';capture.write_once(self.request_file,self.request);self.sha=capture.file_sha(self.request_file)

    def run_capture(self,opener):
        with patch.object(capture,'verify',return_value=(self.request,self.paths)):
            return capture.capture(self.base,self.base,self.old,self.request_file,self.sha,self.base/capture.OUTPUT,opener=opener,pause=lambda _:None)

    def good(self,request,timeout):
        self.calls.append(request.full_url);return Response(request.full_url,b'%PDF-'+b'SYNTHETIC'*125)

    def test_every_GET_and_cache_record_retained_without_guessing_unknown_year_or_financial_admission(self):
        result=self.run_capture(self.good)
        self.assertEqual(len(self.calls),4);self.assertEqual(result['documents_recorded'],5)
        self.assertEqual(result['logical_GET_attempts'],4);self.assertEqual(result['cached_originals_reused'],1)
        self.assertIsNone(result['results_by_document']['SYNTHETIC-1']['fiscal_year'])
        self.assertFalse(result['PDF_text_or_financial_values_decoded']);self.assertFalse(result['investment_factor_admitted'])
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_capture(self.good)
        self.assertEqual(len(self.calls),4)

    def test_original_bad_responses_retained_and_three_consecutive_rejections_stop(self):
        def fail(request,timeout):
            self.calls.append(request.full_url);return Response(request.full_url,b'original not-PDF body')
        with self.assertRaisesRegex(ValueError,'three consecutive'):self.run_capture(fail)
        out=self.base/capture.OUTPUT;terminal=capture.read(out/'terminal.json')
        self.assertEqual(terminal['logical_attempts'],3);self.assertEqual(terminal['completed_documents'],4)
        self.assertEqual(len(list(out.rglob('body.bin'))),3);self.assertEqual(terminal['pending'],['SYNTHETIC-4'])
        self.assertFalse((out/'summary.json').exists())

    def test_original_interruption_rehashes_deleted_cached_body_and_changed_request(self):
        original=KeyboardInterrupt('later original interrupted')
        def interrupted(request,timeout):
            self.old.unlink();self.request_file.write_text('{}');raise original
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_capture(interrupted)
        self.assertIs(caught.exception,original)
        out=self.base/capture.OUTPUT;terminal=capture.read(out/'terminal.json')
        self.assertEqual({d['input'] for d in terminal['postcheck']['mismatches']},{'source/old.pdf','frozen_source_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_nonconsecutive_rejection_remains_in_complete_result_without_false_byte_success(self):
        def one_bad(request,timeout):
            self.calls.append(request.full_url)
            return Response(request.full_url,b'original bad response' if len(self.calls)==1 else b'%PDF-'+b'SYNTHETIC'*125)
        result=self.run_capture(one_bad)
        self.assertEqual(result['rejected_documents'],1)
        self.assertEqual(result['status'],'LATER_ANNUAL_PDF_CAPTURE_WITH_SOURCE_REJECTIONS')
        self.assertEqual(result['results_by_document']['SYNTHETIC-1']['status'],'PDF_SOURCE_REJECTED')
        self.assertEqual(result['logical_GET_attempts'],4)
        self.assertFalse(result['investment_factor_admitted'])


if __name__=='__main__':unittest.main()
