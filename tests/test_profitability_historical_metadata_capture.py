from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from scripts import capture_profitability_historical_metadata as capture


def row(code='600001',year=2022,title=None,identity='123456'):
    publication=year+1
    stamp=int(datetime.fromisoformat(f'{publication}-04-27T00:00:00+08:00').timestamp()*1000)
    return {'secCode':code,'announcementTime':stamp,'announcementTitle':title or f'公司{year}年年度报告',
        'announcementId':identity,'adjunctUrl':f'finalpage/{publication}-04-27/{identity}.PDF'}


def metadata(rows): return {'totalAnnouncement':len(rows),'hasMore':False,'announcements':rows}


class Response(BytesIO):
    def __init__(self,body,status=200):
        super().__init__(body);self.status=status;self.url='https://www.cninfo.com.cn/new/hisAnnouncement/query'
        self.headers={'Content-Type':'application/json','Content-Length':str(len(body))}


class HistoricalAnnualMetadataCaptureTests(unittest.TestCase):
    def test_prefixed_html_and_all_initial_revised_editions_retained_without_two_report_cap(self):
        data=metadata([row(title='公司<em>2022</em>年度报告全文'),
            row(title='2022年年度报告（修订版）',identity='222222'),
            row(title='公司2022年年度报告（更新后）',identity='333333'),
            row(title='公司2022年年度报告（全文）',identity='444444'),
            row(title='公司2022年年度报告摘要',identity='555555'),
            row(title='公司2022年年度报告（可视版）',identity='666666'),
            row(title='公司2022年年度报告（英文版）',identity='777777')])
        rows,selected=capture.select_rows('SH600001',2022,data)
        self.assertEqual(len(rows),7);self.assertEqual(len(selected),4)
        self.assertEqual(selected[0]['edition_role'],'INITIAL_OR_UNSPECIFIED_EDITION')
        self.assertEqual(selected[1]['edition_role'],'EXPLICIT_REVISED_EDITION')
        self.assertEqual([r['classification'] for r in rows[-3:]],['SUMMARY','VISUAL_EDITION','ENGLISH_EDITION'])

    def test_complete_empty_or_summary_only_response_is_missing_candidate_not_invented_report(self):
        self.assertEqual(capture.select_rows('SH600001',2022,metadata([])),([],[]))
        rows,selected=capture.select_rows('SH600001',2022,metadata([row(title='2022年年度报告摘要')]))
        self.assertEqual(len(rows),1);self.assertEqual(selected,[])

    def test_bad_count_page_identity_path_date_or_duplicate_is_rejected(self):
        future=row();future['announcementTime']=int(datetime.fromisoformat('2026-04-27T00:00:00+08:00').timestamp()*1000)
        unsafe=row();unsafe['adjunctUrl']='../outside.pdf'
        for data in (metadata([future]),metadata([row(code='600002')]),metadata([row(),row()]),
                     metadata([unsafe]),{**metadata([row()]),'totalAnnouncement':31},
                     {**metadata([row()]),'hasMore':True},{**metadata([row()]),'totalAnnouncement':True}):
            with self.subTest(data=data),self.assertRaises(ValueError):
                capture.select_rows('SH600001',2022,data)

    def test_each_fiscal_query_keeps_its_publication_year_and_other_year_titles_unselected(self):
        for year in (2022,2023,2024):
            data=metadata([row(year=year,title=f'公司{year}年年度报告（修订稿）')])
            _,selected=capture.select_rows('SH600001',year,data)
            self.assertEqual(selected[0]['fiscal_year'],year)
        _,selected=capture.select_rows('SH600001',2023,metadata([row(year=2023,title='2022年年度报告（修订版）')]))
        self.assertEqual(selected,[])
        with self.assertRaises(ValueError): capture.metadata_resource('SH600001','org',2025)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.raw=self.base/'old.json';self.raw.write_text('old source');self.paths={'source/old.json':self.raw}
        self.specs=[{'resource_key':code+'-'+str(year),'instrument':code,'fiscal_year':year,'reason':'SYNTHETIC_SOURCE_SCOPE'}
            for code,year in [('SH600001',2022),('SH600002',2022),('SH600003',2023),('SZ000001',2024)]]
        self.req={'specifications':self.specs,'resources':{s['resource_key']:capture.metadata_resource(s['instrument'],'org',s['fiscal_year']) for s in self.specs},
                  'input_sha256':{k:capture.file_sha(p) for k,p in self.paths.items()}}
        self.request=self.base/'request.json';capture.write_once(self.request,self.req);self.sha=capture.file_sha(self.request);self.calls=[]

    def opener(self,request,timeout):
        fields=parse_qs(request.data.decode());code=fields['stock'][0].split(',')[0]
        window=fields['seDate'][0];year=int(window[:4])-1;self.calls.append((code,window))
        return Response(json.dumps(metadata([row(code,year,identity=str(year)+code)])).encode())

    def run_capture(self,opener):
        with patch.object(capture,'verify',return_value=(self.req,self.paths)):
            return capture.capture(self.base,self.base,self.raw,self.request,self.sha,self.base/capture.OUTPUT,
                                   opener=opener,pause=lambda seconds:None)

    def test_fixed_resources_once_raw_bytes_and_no_overwrite(self):
        result=self.run_capture(self.opener)
        self.assertEqual(result['logical_attempts'],4);self.assertEqual(result['full_report_candidates'],4)
        self.assertEqual([w for _,w in self.calls],['2023-01-01~2023-12-31']*2+['2024-01-01~2024-12-31','2025-01-01~2025-12-31'])
        self.assertEqual(len(list((self.base/capture.OUTPUT).rglob('body.bin'))),4)
        self.assertFalse(result['investment_factor_admitted'])
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_capture(self.opener)
        self.assertEqual(len(self.calls),4)

    def test_three_http_rejections_abort_preserving_raw_bodies_and_pending_resource(self):
        def fail(request,timeout):self.calls.append(request.full_url);return Response(b'original503',503)
        with self.assertRaisesRegex(ValueError,'three consecutive'):self.run_capture(fail)
        terminal=capture.read(self.base/capture.OUTPUT/'terminal.json')
        self.assertEqual(len(self.calls),3);self.assertEqual(terminal['logical_attempts'],3)
        self.assertEqual(terminal['pending'],[self.specs[-1]['resource_key']])
        self.assertEqual(len(list((self.base/capture.OUTPUT).rglob('body.bin'))),3)
        self.assertFalse((self.base/capture.OUTPUT/'summary.json').exists())

    def test_nonconsecutive_rejection_is_not_retried_or_hidden(self):
        def once_bad(request,timeout):
            if not self.calls:self.calls.append(('first','503'));return Response(b'original503',503)
            return self.opener(request,timeout)
        result=self.run_capture(once_bad)
        self.assertEqual(len(self.calls),4);self.assertEqual(result['logical_attempts'],4)
        self.assertEqual(result['status_counts']['METADATA_SOURCE_REJECTED'],1)

    def test_original_interruption_and_changed_request_source_survive_postcheck(self):
        original=KeyboardInterrupt('source capture interruption')
        def interrupt(request,timeout):self.raw.unlink();self.request.write_text('{}');raise original
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_capture(interrupt)
        self.assertIs(caught.exception,original)
        terminal=capture.read(self.base/capture.OUTPUT/'terminal.json')
        self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt')
        self.assertEqual({m['input'] for m in terminal['postcheck']['mismatches']},{'source/old.json','frozen_source_request'})
        self.assertFalse((self.base/capture.OUTPUT/'summary.json').exists())


if __name__=='__main__':unittest.main()
