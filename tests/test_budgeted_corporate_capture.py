import base64
import json
from pathlib import Path
import tempfile
import unittest
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

from scripts.fundamental_query_journal import QueryJournal
try:
    from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes, select_notice
except ImportError:
    journaled_bytes = select_notice = None


def response(body=b'%PDF-1.7 fixture', status=200, truncated=False):
    return ['http_response'], [{'status': status, 'body_base64': base64.b64encode(body).decode(),
        'body_truncated': truncated, 'body_complete': not truncated,
        'read_error_type': None, 'read_error': None,
        'content_type': 'application/pdf', 'final_url': 'https://static.cninfo.com.cn/fixture'}]


class BudgetedCorporateCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(journaled_bytes)
        self.assertIsNotNone(select_notice)

    def test_original_http_error_body_is_retained_without_free_retry(self):
        calls=[]
        def fetch():calls.append(1);return response(b'synthetic maintenance',503)
        with tempfile.TemporaryDirectory() as d:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'HTTP response'):
                    journaled_bytes(QueryJournal(d,max_queries=1,max_attempts=1),{'id':'bounded'},fetch)
            record=json.loads(next(Path(d).rglob('response-1.json')).read_text())['payload']['rows'][0]
            self.assertEqual(base64.b64decode(record['body_base64']),b'synthetic maintenance')
            self.assertEqual(len(calls),1)

    def test_truncated_http_body_is_not_accepted_as_a_document(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'HTTP response'):
                journaled_bytes(QueryJournal(d,max_queries=1,max_attempts=1),{'id':'oversize'},lambda:response(truncated=True))
            self.assertEqual(len(list(Path(d).rglob('response-1.json'))),1)

    def test_successful_original_bytes_and_receipt_survive_restart(self):
        with tempfile.TemporaryDirectory() as d:
            j=QueryJournal(d,max_queries=1,max_attempts=1)
            body,receipt=journaled_bytes(j,{'id':'pdf'},response)
            self.assertEqual(body,b'%PDF-1.7 fixture')
            self.assertTrue((Path(d)/receipt['response_file']).is_file())
            def denied():raise AssertionError('requery')
            self.assertEqual(journaled_bytes(j,{'id':'pdf'},denied),(body,receipt))

    def test_notice_selection_binds_code_day_and_original_pdf_location(self):
        case={'instrument':'SH603298','publication_day':'2024-05-24'}
        row={'code':'603298','day':'2024-05-24','title':'2023年年度权益分派实施公告',
            'announcement_id':'1220000001','pdf_path':'finalpage/2024-05-24/1220000001.PDF'}
        self.assertEqual(select_notice([row],case),row)
        for altered in ({'code':'600001'},{'day':'2026-05-24'},
                        {'pdf_path':'../2024-05-24/1220000001.PDF'},
                        {'pdf_path':'finalpage/2024-05-24/1220000002.PDF'}):
            with self.assertRaises(ValueError):select_notice([{**row,**altered}],case)
        with self.assertRaises(ValueError):select_notice([row,row],case)

    def test_final_response_identity_mismatch_is_rejected_after_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'HTTP response'):
                journaled_bytes(QueryJournal(d,max_queries=1,max_attempts=1),
                    {'url':'https://static.cninfo.com.cn/finalpage/2024-05-24/1220000001.PDF'},response)
            self.assertEqual(len(list(Path(d).rglob('response-1.json'))),1)

    def test_http_redirect_is_not_followed_outside_the_reserved_request(self):
        from scripts import capture_budgeted_corporate_notices_pre2026 as capture
        paths=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                # Consume the request before closing the connection: unread POST
                # bytes can cause a TCP reset that discards our fixture response.
                self.rfile.read(int(self.headers['Content-Length']))
                paths.append(self.path);self.send_response(302)
                self.send_header('Location','/finalpage/2026-01-01/1220000002.PDF');self.end_headers()
                self.wfile.write(b'synthetic redirect body')
            def do_GET(self):
                paths.append(self.path);self.send_response(200);self.end_headers()
                self.wfile.write(b'%PDF-1.7 synthetic later document')
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            origin='http://127.0.0.1:'+str(server.server_port)
            url=origin+'/new/hisAnnouncement/query'
            with tempfile.TemporaryDirectory() as d,patch.object(capture,'CNINFO',origin):
                with self.assertRaisesRegex(ValueError,'HTTP response'):
                    journaled_bytes(QueryJournal(d,max_queries=1,max_attempts=1),{'url':url},lambda:capture.read_wire(url,{'fixture':'only'}))
                saved=json.loads(next(Path(d).rglob('response-1.json')).read_text())['payload']['rows'][0]
                self.assertEqual(saved['status'],302)
                self.assertEqual(base64.b64decode(saved['body_base64']),b'synthetic redirect body')
            self.assertEqual(paths,['/new/hisAnnouncement/query'])
        finally:
            server.shutdown();thread.join(timeout=2);server.server_close()

    def test_incomplete_read_partial_bytes_survive_in_the_journal(self):
        from scripts import capture_budgeted_corporate_notices_pre2026 as capture
        url='https://static.cninfo.com.cn/finalpage/2024-05-24/1220000001.PDF'
        class Wire:
            code=200;headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return url
            def read(self,n):raise IncompleteRead(b'%PDF received partial bytes',90)
        with tempfile.TemporaryDirectory() as d,patch.object(capture,'urlopen',return_value=Wire(),create=True),patch.object(capture,'build_opener',return_value=SimpleNamespace(open=lambda *args,**kwargs:Wire()),create=True):
            with self.assertRaises(ValueError):
                journaled_bytes(QueryJournal(d,max_queries=1,max_attempts=1),{'url':url},lambda:capture.read_wire(url,None))
            saved=json.loads(next(Path(d).rglob('response-1.json')).read_text())
            self.assertEqual(saved['status'],'CAPTURED')
            wire=saved['payload']['rows'][0]
            self.assertEqual(base64.b64decode(wire['body_base64']),b'%PDF received partial bytes')
            self.assertEqual(wire['read_error_type'],'IncompleteRead')
            self.assertFalse(wire['body_complete'])

    def test_early_eof_is_incomplete_when_content_length_is_not_met(self):
        from scripts import capture_budgeted_corporate_notices_pre2026 as capture
        url='https://static.cninfo.com.cn/finalpage/2024-05-24/1220000001.PDF'
        class Wire:
            code=200;headers={'Content-Length':'1000'}
            def __init__(self):self.calls=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return url
            def read(self,n):
                self.calls+=1;return b'%PDF short body' if self.calls==1 else b''
        with tempfile.TemporaryDirectory() as d,patch.object(capture,'urlopen',return_value=Wire(),create=True),patch.object(capture,'build_opener',return_value=SimpleNamespace(open=lambda *args,**kwargs:Wire()),create=True):
            with self.assertRaisesRegex(ValueError,'HTTP response'):
                journaled_bytes(QueryJournal(d,max_queries=1,max_attempts=1),{'url':url},lambda:capture.read_wire(url,None))
            wire=json.loads(next(Path(d).rglob('response-1.json')).read_text())['payload']['rows'][0]
            self.assertEqual(base64.b64decode(wire['body_base64']),b'%PDF short body')
            self.assertFalse(wire['body_complete'])
