import copy,json,unittest
from scripts import derive_etf_tencent_interim2026 as subject

DATES=['2025-01-02','2025-12-31','2026-01-05','2026-10-16','2026-10-19','2026-10-20']
def wire(code, rows=None):
 rows=rows or [[d,'2.000','2.001','2.010','1.990','123.45','','','','',''] for d in DATES]
 return ('kline_day2025='+json.dumps({'code':0,'msg':'','data':{code.lower():{'day':rows,'qt':{'ignored':'auxiliary'}}}})).encode()
def sources():return {c:wire(c) for c in ('SH510300','SH510500','SZ159915')}
def old():return {c:[{'date':d,'open':'2.000','close':'2.001','high':'2.010','low':'1.990'} for d in DATES[:2]] for c in sources()}
class TencentDerivationTests(unittest.TestCase):
 def test_unadjusted_overlap_and_observed_extension_without_volume_unit_invention(self):
  packets,days,audit=subject.derive_prices(sources(),old(),DATES[2:4])
  self.assertEqual(days,DATES[2:]);self.assertEqual(audit['overlap_sessions_each'],2)
  self.assertEqual(packets['SH510300']['bars'][0]['volume_provider_raw'],'123.45')
  self.assertFalse(packets['SH510300']['volume_unit_verified'])
 def test_earlier_unrequested_rows_are_quarantined_and_future_rows_reject(self):
  for day,expected in [('2024-12-31',True),('2026-10-21',False)]:
   s=sources();rows=json.loads(s['SH510300'].decode().split('=',1)[1])['data']['sh510300']['day'];rows.append([day,'999','999','999','999','1','','','','','']);rows.sort();s['SH510300']=wire('SH510300',rows)
   if expected:
    _,_,a=subject.derive_prices(s,old(),DATES[2:4]);self.assertEqual(a['excluded_pre2025_rows']['SH510300'],1)
   else:
    with self.assertRaises(ValueError):subject.derive_prices(s,old(),DATES[2:4])
 def test_qfq_only_wrong_identity_mismatched_ohlc_bad_tick_and_calendar_fail_closed(self):
  for mode in ('qfq','identity','overlap','tick','missing','duplicate','json_code'):
   s=sources();v=json.loads(s['SH510300'].decode().split('=',1)[1]);node=v['data']['sh510300'];rows=node['day']
   if mode=='qfq':node['qfqday']=node.pop('day')
   elif mode=='identity':v['data']['sh510500']=v['data'].pop('sh510300')
   elif mode=='overlap':rows[0][2]='2.002'
   elif mode=='tick':rows[-1][1]='2.0001'
   elif mode=='missing':rows.pop(-2)
   elif mode=='duplicate':rows.append(rows[-1])
   else:v['code']=1
   s['SH510300']=('kline_day2025='+json.dumps(v)).encode()
   with self.subTest(mode=mode):
    with self.assertRaises(ValueError):subject.derive_prices(s,old(),DATES[2:4])
 def test_official_closure_endpoint_requires_exact_month_and_day(self):
  self.assertEqual(subject.closure_endpoints('元旦：1月1日（星期四）至1月3日（星期六）休市'),('01-01','01-03'))
  self.assertNotEqual(subject.closure_endpoints('元旦：1月11日至1月13日休市'),('01-01','01-03'))
  self.assertNotEqual(subject.closure_endpoints('元旦：2月1日至2月3日休市'),('01-01','01-03'))
 def test_jsonp_is_never_evaluated(self):
  s=sources();s['SH510300']=b'kline_day2025=__import__("os").system("false")'
  with self.assertRaises(ValueError):subject.derive_prices(s,old(),DATES[2:4])
if __name__=='__main__':unittest.main()
