import unittest
from unittest.mock import patch
from scripts.capture_etf_interim2026_quote_retry import read_wire,SOURCES
class Reply:
 code=200;headers={'Content-Type':'application/json','Content-Length':'8'}
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def geturl(self):return SOURCES[0]['url']
 def read(self,n):
  value=getattr(self,'pending',b'{"rc":0}');self.pending=b'';return value
class Opener:
 def open(self,request,timeout):
  self.request=request;return Reply()
class QuoteTransportTests(unittest.TestCase):
 def test_pinned_quote_request_headers_and_registered_same_url_only(self):
  op=Opener()
  with patch('scripts.capture_etf_interim2026_quote_retry.build_opener',return_value=op):
   fields,rows=read_wire(SOURCES[0]['url'],tuple(s['url'] for s in SOURCES))
  self.assertEqual(op.request.get_header('Referer'),'https://quote.eastmoney.com/')
  self.assertEqual(op.request.full_url,SOURCES[0]['url']);self.assertEqual(fields,['http_response'])
  self.assertTrue(rows[0]['body_complete']);self.assertEqual(rows[0]['status'],200)
  with self.assertRaises(ValueError):read_wire(SOURCES[0]['url']+'&end=20261021',tuple(s['url'] for s in SOURCES))
if __name__=='__main__':unittest.main()
