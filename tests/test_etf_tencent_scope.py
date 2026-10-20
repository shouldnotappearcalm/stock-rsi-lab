import unittest
from urllib.parse import urlsplit,parse_qs
from scripts.capture_etf_tencent_interim2026 import SOURCES,history_url
class TencentETFSourceScopeTests(unittest.TestCase):
 def test_raw_overlap_period_has_explicit_end_and_no_adjustment_or_extra_query(self):
  self.assertEqual(len(SOURCES),3)
  for code in ('SH510300','SH510500','SZ159915'):
   url=history_url(code);parts=urlsplit(url);p=parse_qs(parts.query,keep_blank_values=True)
   self.assertEqual(parts.netloc,'proxy.finance.qq.com')
   self.assertEqual(p['param'],[code.lower()+',day,2025-01-01,2026-10-20,640,'])
   self.assertEqual(p['_var'],['kline_day2025']);self.assertNotIn('qfq',url);self.assertNotIn('hfq',url)
  with self.assertRaises(ValueError):history_url('SH600000')
if __name__=='__main__':unittest.main()
