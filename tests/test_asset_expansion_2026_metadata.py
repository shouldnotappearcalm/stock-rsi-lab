from datetime import datetime
from io import BytesIO
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs


def row(title='公司2025年年度报告',identity='123',code='600001',day='2026-04-27'):
    return {'secCode':code,'announcementTime':int(datetime.fromisoformat(day+'T00:00:00+08:00').timestamp()*1000),
        'announcementTitle':title,'announcementId':identity,'adjunctUrl':f'finalpage/{day}/{identity}.PDF'}


def data(rows):return {'totalAnnouncement':len(rows),'hasMore':False,'announcements':rows}


class Asset2026MetadataTests(unittest.TestCase):
    def setUp(self):self.m=importlib.import_module('scripts.capture_asset_expansion_2026_annual_metadata')

    def test_new_resource_has_exact_cutoff_and_keeps_old_collector_cap(self):
        resource=self.m.metadata_resource('SH600001','org')
        self.assertEqual(resource['payload']['seDate'],'2026-01-01~2026-10-21')
        self.assertEqual(resource['payload']['category'],'category_ndbg_szsh')
        old=importlib.import_module('scripts.capture_profitability_historical_metadata')
        with self.assertRaises(ValueError):old.metadata_resource('SH600001','org',2025)

    def test_initial_revised_prior_and_illustrated_full_editions_are_all_retained(self):
        titles=['公司<em>2025</em>年年度报告','公司2025年年度报告（修订版）','2024年度报告（更正后）',
            '2025年年度报告（更新前）','2025年年度报告（图文版）','年报全文','2025年年度报告摘要','2025年年度报告（英文版）']
        rows,candidates=self.m.select_rows('SH600001',data([row(t,str(i+1)) for i,t in enumerate(titles)]))
        self.assertEqual(len(rows),8);self.assertEqual(len(candidates),6)
        self.assertEqual([v['fiscal_year'] for v in candidates],[2025,2025,2024,2025,2025,None])
        self.assertEqual(candidates[3]['classification'],'PRIOR_VERSION_FULL_REPORT_CANDIDATE')
        self.assertEqual(candidates[4]['classification'],'ILLUSTRATED_FULL_REPORT_CANDIDATE')
        self.assertEqual(candidates[5]['classification'],'UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE')

    def test_future_or_wrong_issuer_unsafe_or_duplicate_metadata_fails(self):
        bad=row();bad['adjunctUrl']='../outside.pdf'
        for value in (data([row(day='2026-10-22')]),data([row(day='2025-12-31')]),data([row(code='600002')]),
            data([row(),row()]),data([bad]),{**data([row()]),'totalAnnouncement':31},
            {**data([row()]),'hasMore':True},{**data([row()]),'totalAnnouncement':True}):
            with self.subTest(value),self.assertRaises(ValueError):self.m.select_rows('SH600001',value)

    def test_future_fiscal_title_and_other_notice_are_retained_but_not_used(self):
        rows,candidates=self.m.select_rows('SH600001',data([row('公司2026年年度报告','1'),row('公司年度报告更正公告','2')]))
        self.assertEqual(candidates,[]);self.assertEqual(rows[0]['classification'],'OUTSIDE_FROZEN_FISCAL_SCOPE')
        self.assertIsNone(rows[1]['fiscal_year'])
        self.assertEqual(self.m.select_rows('SH600001',data([])),([],[]))
        with self.assertRaises(ValueError):self.m.select_rows('SH600001',{'totalAnnouncement':0,'announcements':''})

    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);base=Path(temp.name)
        codes=['SH600001','SH600002','SH600003','SH600004']
        request=base/'request.json';self.m.write_once(request,{'synthetic_scope':codes})
        r={'cohort':codes,'resources':{c:self.m.metadata_resource(c,'org') for c in codes}}
        return base,request,r,{request:self.m.file_sha(request)}

    def response(self,body):
        response=BytesIO(json.dumps(body).encode());response.status=200
        response.url='https://www.cninfo.com.cn/new/hisAnnouncement/query'
        response.headers={'Content-Type':'application/json','Content-Length':str(len(response.getvalue()))}
        return response

    def test_three_bad_sources_stop_with_terminal_pending_and_no_success_summary(self):
        base,request,r,bound=self.fixture();calls=[]
        def opener(req,timeout):
            calls.append(req);return self.response(data([row(code='600999')]))
        with patch.object(self.m,'verify',return_value=(r,bound)),self.assertRaisesRegex(ValueError,'three consecutive'):
            self.m.capture(base,base,request,self.m.file_sha(request),base/self.m.OUTPUT,opener=opener,pause=lambda _:None)
        out=base/self.m.OUTPUT;terminal=json.loads((out/'terminal.json').read_text())
        self.assertEqual(len(calls),3);self.assertEqual(terminal['pending'],['SH600004'])
        self.assertTrue(terminal['postcheck']['all_inputs_unchanged']);self.assertFalse((out/'summary.json').exists())
        self.assertEqual(len(list((out/'http').rglob('reservation.json'))),3)

    def test_interrupt_retains_unanswered_attempt_and_all_pending_without_restart(self):
        base,request,r,bound=self.fixture()
        with patch.object(self.m,'verify',return_value=(r,bound)),self.assertRaises(KeyboardInterrupt):
            self.m.capture(base,base,request,self.m.file_sha(request),base/self.m.OUTPUT,
                opener=lambda *_args,**_kw:(_ for _ in ()).throw(KeyboardInterrupt()),pause=lambda _:None)
        out=base/self.m.OUTPUT;terminal=json.loads((out/'terminal.json').read_text())
        self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt')
        self.assertEqual(terminal['pending'],r['cohort']);self.assertEqual(terminal['logical_attempts'],1)
        with self.assertRaises(ValueError):self.m.capture(base,base,request,self.m.file_sha(request),out)

    def test_complete_sources_but_changed_original_input_prevent_success(self):
        base,request,r,bound=self.fixture();calls=[]
        def opener(req,timeout):
            c=parse_qs(req.data.decode())['stock'][0].split(',')[0];calls.append(c)
            if len(calls)==1:request.write_text('changed input')
            return self.response(data([row(code=c,identity=c)]))
        with patch.object(self.m,'verify',return_value=(r,bound)),self.assertRaisesRegex(ValueError,'immutable metadata'):
            self.m.capture(base,base,request,bound[request],base/self.m.OUTPUT,opener=opener,pause=lambda _:None)
        out=base/self.m.OUTPUT;terminal=json.loads((out/'terminal.json').read_text())
        self.assertFalse(terminal['postcheck']['all_inputs_unchanged']);self.assertEqual(len(calls),4)
        self.assertFalse((out/'summary.json').exists())


if __name__=='__main__':unittest.main()
