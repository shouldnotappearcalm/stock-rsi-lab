import base64
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest


class CorporateCapture2026Tests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.capture_low_beta60_corporate_2026')
        except ModuleNotFoundError:self.fail('bounded 2026 primary capture is absent')

    def request(self,base):
        original=b'%PDF-1.4\noriginal cached bytes\n';(base/'original.pdf').write_bytes(original)
        return {'documents':[
            {'document_id':'cached','instrument':'SH601128','publication_day':'2026-06-03',
             'reuse_file':'original.pdf','reuse_sha256':hashlib.sha256(original).hexdigest()},
            {'document_id':'direct','instrument':'SZ000975','publication_day':'2026-04-17',
             'url':'https://static.cninfo.com.cn/finalpage/2026-04-17/1225111389.PDF'},
            {'document_id':'listed','instrument':'SH603826','publication_day':'2026-07-08',
             'organization_id':'9900030692','exact_title':'2025年年度权益分派实施公告'}],
            'maximum_http_queries':3}

    def wire(self,url,data):
        return ['http_response'],[{'status':200,'content_type':'application/pdf',
            'final_url':url,'body_base64':base64.b64encode(data).decode(),
            'body_complete':True,'body_truncated':False,'read_error_type':None,'read_error':None}]

    def listing(self,**changes):
        row={'secCode':'603826','announcementTitle':'坤彩科技：2025年年度权益分派实施公告',
             'announcementTime':1783440000000,'announcementId':'1234567890',
             'adjunctUrl':'finalpage/2026-07-08/1234567890.PDF'}
        row.update(changes)
        return json.dumps({'totalAnnouncement':1,'announcements':[row]}).encode()

    # Dropping byte preservation or issuing a second request after restart must fail.
    def test_reuses_original_bytes_and_journals_unique_listing_and_pdf_without_resume(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);r=self.request(base);calls=[]
            def fetch(url,payload):
                calls.append((url,payload))
                return self.wire(url,self.listing() if payload is not None else b'%PDF-1.4\nfresh\n')
            out=base/'capture';m=api.capture_documents(r,base,out,fetch,request_sha='a'*64)
            self.assertEqual(3,m['http_query_reservations']);self.assertEqual(3,len(m['documents']))
            self.assertEqual((base/'original.pdf').read_bytes(),(out/'cached.pdf').read_bytes())
            self.assertFalse(m['documents_financially_reviewed']);self.assertFalse(m['portfolio_returns_computed'])
            self.assertEqual('2026-07-08~2026-07-08',calls[1][1]['seDate'])
            self.assertEqual('603826,9900030692',calls[1][1]['stock'])
            self.assertEqual('https://static.cninfo.com.cn/finalpage/2026-07-08/1234567890.PDF',calls[2][0])
            self.assertEqual(3,len(list(out.rglob('response-1.json'))))
            with self.assertRaises(ValueError):api.capture_documents(r,base,out,fetch,request_sha='a'*64)
            self.assertEqual(3,len(calls))

    # A changed cached file or an inflated/boolean budget must be rejected before any HTTP call.
    def test_reuse_tamper_and_budget_fail_before_output_or_network(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);r=self.request(base)
            def forbidden(*args):self.fail('source call before authentication')
            for budget in (True,4,2):
                with self.subTest(budget=budget):
                    with self.assertRaises(ValueError):api.capture_documents({**r,'maximum_http_queries':budget},base,base/'out',forbidden,request_sha='a'*64)
                    self.assertFalse((base/'out').exists())
            (base/'original.pdf').write_bytes(b'%PDF-1.4 changed')
            with self.assertRaises(ValueError):api.capture_documents(r,base,base/'out',forbidden,request_sha='a'*64)
            self.assertFalse((base/'out').exists())

    # Accepting another issuer, ambiguous listing, future publication or a foreign URL must fail before PDF retrieval.
    def test_wrong_listing_is_retained_as_failed_document_without_pdf_fallback(self):
        api=self.api()
        for changes in ({'secCode':'600000'},{'announcementTime':1783526400000},
                        {'adjunctUrl':'https://example.com/evil.PDF'},
                        {'announcementTitle':'2025年年度报告'}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as d:
                base=Path(d);r=self.request(base);r['documents']=r['documents'][2:];r['maximum_http_queries']=2
                def fetch(url,payload):
                    self.assertIsNotNone(payload,'invalid listing caused a PDF request')
                    return self.wire(url,self.listing(**changes))
                m=api.capture_documents(r,base,base/'out',fetch,request_sha='a'*64)
                self.assertEqual(['listed'],list(m['errors']));self.assertEqual(1,m['http_query_reservations'])
                self.assertEqual(0,len(m['documents']));self.assertFalse(m['capture_complete'])

    # Restarting/failing sources cannot consume a fourth call after the three-failure stop.
    def test_three_failures_keep_receipts_and_pending_instead_of_retries(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);r={'documents':[{'document_id':'d'+str(i),'instrument':'SH601918',
                'publication_day':'2026-01-30','url':f'https://static.cninfo.com.cn/finalpage/2026-01-30/{i+1}.PDF'}
                for i in range(4)],'maximum_http_queries':4}
            def fetch(url,payload):raise OSError('synthetic transport failure')
            m=api.capture_documents(r,base,base/'out',fetch,request_sha='a'*64)
            self.assertEqual(3,m['http_query_reservations']);self.assertEqual(['d3'],m['pending_documents'])
            self.assertTrue(m['stopped_after_three_failures']);self.assertFalse(m['capture_complete'])
            self.assertEqual(3,len(list((base/'out').rglob('response-1.json'))))
            self.assertEqual([],list((base/'out').rglob('reserved-2.json')))

    def test_cli_rejects_wrong_external_request_sha_before_creating_capture(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);path=base/'request.json';path.write_text('{}\n')
            with self.assertRaises(ValueError):api.main(['--request',str(path),
                '--expected-request-sha256','0'*64,'--source-root',str(base),
                '--output-dir',str(base/'out')])
            self.assertFalse((base/'out').exists())


if __name__=='__main__':unittest.main()
