import copy
import json
import unittest
from scripts.derive_etf_interim2026_prices import derive_prices
CODES=('SH510300','SH510500','SZ159915')
DATES=['2026-01-05','2026-10-16','2026-10-19','2026-10-20']
def originals():
 return {c:json.dumps({'rc':0,'data':{'code':c[2:],'market':1 if c.startswith('SH') else 0,'klines':[d+',2.000,2.001,2.010,1.990,100,20000.00,1,1,1,1' for d in DATES]}}).encode() for c in CODES}
class InterimETFPriceTests(unittest.TestCase):
 def test_observed_three_asset_dates_must_extend_exact_explicit_reference(self):
  rows,sessions=derive_prices(originals(),DATES[:2])
  self.assertEqual(sessions,DATES);self.assertEqual(len(rows),3)
  self.assertEqual(rows['SH510300']['bars'][-1]['date'],'2026-10-20')
  self.assertFalse(rows['SH510300']['historical_arrival_certified'])
 def test_missing_or_different_asset_dates_reject_without_synthesizing_calendar(self):
  for code in CODES:
   source=originals();p=json.loads(source[code]);p['data']['klines'].pop(1);source[code]=json.dumps(p).encode()
   with self.assertRaises(ValueError):derive_prices(source,DATES[:2])
  with self.assertRaises(ValueError):derive_prices(originals(),['2026-01-06','2026-10-16'])
 def test_future_duplicate_wrong_identity_invalid_tick_fail_closed(self):
  for alteration in ('future','duplicate','identity','tick'):
   source=originals();p=json.loads(source['SH510300'])
   if alteration=='future':p['data']['klines'][-1]=p['data']['klines'][-1].replace('2026-10-20','2026-10-21')
   elif alteration=='duplicate':p['data']['klines'][1]=p['data']['klines'][0]
   elif alteration=='identity':p['data']['market']=0
   else:p['data']['klines'][0]=p['data']['klines'][0].replace('2.000','2.0001')
   source['SH510300']=json.dumps(p).encode()
   with self.subTest(alteration=alteration):
    with self.assertRaises(ValueError):derive_prices(source,DATES[:2])
if __name__=='__main__':unittest.main()
