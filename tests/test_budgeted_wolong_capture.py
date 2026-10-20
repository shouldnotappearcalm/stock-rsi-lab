from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
try:
    from scripts.capture_budgeted_wolong_tax_source_pre2026 import select_source, capture_sources
except ImportError:
    select_source=capture_sources=None


class BudgetedWolongCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(select_source)
        self.proposal={'code':'600580','day':'2025-04-26','title':'卧龙电驱：关于2024年度利润分配及资本公积转增股本方案的公告',
            'announcement_id':'1220000001','pdf_path':'finalpage/2025-04-26/1220000001.PDF','timestamp_ms':1745596800000}
        self.annual={**self.proposal,'title':'卧龙电驱：2024年年度报告','announcement_id':'1220000002','pdf_path':'finalpage/2025-04-26/1220000002.PDF'}

    def test_selects_unique_exact_day_original_plan_and_full_annual_report(self):
        rows=[self.proposal,self.annual,{**self.annual,'title':'2024年年度报告摘要'}]
        self.assertEqual(select_source(rows,'proposal'),self.proposal)
        self.assertEqual(select_source(rows,'annual'),self.annual)

    def test_rejects_wrong_security_future_path_summary_and_ambiguity(self):
        for change in ({'code':'600001'},{'day':'2026-04-26'}, {'pdf_path':'finalpage/2026-04-26/1220000002.PDF'},
                {'pdf_path':'../2025-04-26/1220000002.PDF'},{'announcement_id':'../2'},
                {'title':'2024年年度报告（更正后）'},{'title':'2024年年度报告摘要'}):
            with self.subTest(change=change),self.assertRaises(ValueError):select_source([{**self.annual,**change}],'annual')
        with self.assertRaises(ValueError):select_source([self.annual,self.annual],'annual')

    def test_missing_plan_does_not_prevent_retaining_annual_document_and_replay_uses_no_network(self):
        import json,base64
        from scripts import capture_budgeted_wolong_tax_source_pre2026 as c
        wire_calls=[]
        def wire(url,payload):
            wire_calls.append(url)
            if payload is not None:
                body=json.dumps({'totalAnnouncement':1,'announcements':[{'secCode':'600580','announcementTitle':self.annual['title'],
                    'announcementTime':self.annual['timestamp_ms'],'announcementId':'1220000002','adjunctUrl':self.annual['pdf_path']}]}).encode()
            else:body=b'%PDF-1.7 synthetic fixture'
            return ['http_response'],[{'status':200,'content_type':'fixture','final_url':url,'body_base64':base64.b64encode(body).decode(),
                'body_truncated':False,'body_complete':True,'read_error_type':None,'read_error':None}]
        with tempfile.TemporaryDirectory() as d,patch.object(c,'read_wire',side_effect=wire):
            request={'minimum_interval_seconds':0.,'maximum_http_queries':4,'max_pages':2}
            docs,errors=capture_sources(request,Path(d),'a'*64)
            self.assertEqual(set(docs),{'annual'});self.assertEqual(set(errors),{'proposal'})
            self.assertEqual(len(wire_calls),2)
            repeated=capture_sources(request,Path(d),'a'*64)
            self.assertEqual((docs,errors),repeated);self.assertEqual(len(wire_calls),2)


if __name__=='__main__':unittest.main()
