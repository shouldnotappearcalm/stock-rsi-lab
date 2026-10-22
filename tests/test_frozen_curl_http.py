from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import importlib
import json
import tempfile
import unittest
from urllib.error import URLError
from urllib.request import Request


class FrozenCurlTests(unittest.TestCase):
    def setUp(self):
        self.m=importlib.import_module('scripts.frozen_curl_http')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.url='https://www.cninfo.com.cn/new/hisAnnouncement/query'
        self.resources={'one':{'method':'POST','url':self.url,'payload':{'stock':'600001,org'}}};self.calls=[]

    def runner(self,args,**kw):
        self.calls.append(args)
        Path(args[args.index('--dump-header')+1]).write_bytes(b'HTTP/1.1 200 Connection established\r\n\r\nHTTP/2 200\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n')
        Path(args[args.index('--output')+1]).write_bytes(b'{}')
        return SimpleNamespace(returncode=0,stdout=('200\n'+self.url).encode(),stderr=b'')

    def test_exact_registered_post_has_one_attempt_and_final_response_headers(self):
        opener=self.m.FrozenCurlOpener(self.root/'transport',self.resources,max_body_bytes=100,runner=self.runner)
        response=opener(Request(self.url,data=b'stock=600001%2Corg',method='POST'),timeout=20)
        self.assertEqual(response.read(),b'{}');self.assertEqual(response.status,200);self.assertEqual(response.headers['Content-Length'],'2')
        with self.assertRaises(ValueError):opener(Request(self.url,data=b'stock=600001%2Corg',method='POST'),timeout=20)
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('--retry',self.calls[0]);self.assertNotIn('--location',self.calls[0])

    def test_unregistered_future_request_is_rejected_before_transport(self):
        opener=self.m.FrozenCurlOpener(self.root/'transport',self.resources,max_body_bytes=100,runner=self.runner)
        with self.assertRaises(ValueError):opener(Request(self.url,data=b'stock=600001%2Corg&seDate=2027',method='POST'),timeout=20)
        self.assertEqual(self.calls,[])

    def test_TLS_error_retains_transport_artifacts_before_raising(self):
        def fail(args,**kw):
            r=self.runner(args,**kw);r.returncode=35;r.stderr=b'SSL EOF';return r
        opener=self.m.FrozenCurlOpener(self.root/'transport',self.resources,max_body_bytes=100,runner=fail)
        with self.assertRaises(URLError):opener(Request(self.url,data=b'stock=600001%2Corg',method='POST'),timeout=20)
        records=list((self.root/'transport').glob('*/transport.json'));self.assertEqual(len(records),1)
        record=json.loads(records[0].read_text());self.assertEqual(record['returncode'],35)
        self.assertEqual(records[0].with_name('stderr.bin').read_bytes(),b'SSL EOF')

    def test_success_code_cannot_hide_oversized_body_or_redirect(self):
        for label in ('oversize','redirect'):
            def bad(args,**kw):
                r=self.runner(args,**kw)
                if label=='oversize':Path(args[args.index('--output')+1]).write_bytes(b'X'*101)
                else:r.stdout=b'200\nhttps://other.example/future'
                return r
            opener=self.m.FrozenCurlOpener(self.root/label,self.resources,max_body_bytes=100,runner=bad)
            with self.subTest(label),self.assertRaises(URLError):opener(Request(self.url,data=b'stock=600001%2Corg',method='POST'),timeout=20)


if __name__=='__main__':unittest.main()
