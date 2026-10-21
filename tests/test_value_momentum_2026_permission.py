import unittest
from datetime import date
from pathlib import Path
from scripts.prepare_value_momentum_2026_targets import assert_cap_only_change
from stock_rsi.exchange_value_momentum_extended import build_targets


class Composite2026PermissionTests(unittest.TestCase):
 def test_only_date_permission_can_differ_from_frozen_investment_core(self):
  root=Path(__file__).resolve().parents[1]/'src/stock_rsi'
  old=(root/'exchange_value_momentum.py').read_text();new=(root/'exchange_value_momentum_extended.py').read_text()
  assert_cap_only_change(old,new)
  with self.assertRaises(ValueError):assert_cap_only_change(old,new.replace('.475','.48'))
  with self.assertRaises(ValueError):assert_cap_only_change(old,new.replace('closes[-2]','closes[-1]'))

 def fixture(self):
  ends=[date(2024,12,28)]+[date(2025,m,28) for m in range(1,13)]
  class Prices:
   calendar=tuple(ends+[date(2026,1,5),date(2026,1,30)])
   def __init__(self,future):self.future=future;self.reads=[]
   def value(self,code,field,day):
    self.reads.append(day)
    if day>'2025-12-28':return self.future
    if field in ('factor','volume'):return 1.
    return 100.+int(code[-3:])/100 if date.fromisoformat(day)==ends[-2] else 100.
  names={f'SZ000{i:03d}':[('2020-01-01','2026-12-31')] for i in range(100,200)}
  stocks={c:{'pe':str(i+1),'reported_special_name':False} for i,c in enumerate(names)}
  reports={'2025-11':{'month':'2025-11','article_build_day':'2025-12-07','table_build_day':'2025-12-07','table_sha256':'fixture','stocks':stocks}}
  return Prices,names,reports

 def test_2026_permission_never_opens_future_quotes_for_a_decision(self):
  Prices,m,r=self.fixture()
  with self.assertRaises(ValueError):build_targets(Prices(1),m,r,start='2026-01-05',end='2026-01-30')
  p=Prices(1);q=Prices(99999)
  t,receipts=build_targets(p,m,r,start='2026-01-05',end='2026-01-30',permitted_end='2026-01-30')
  self.assertEqual((t,receipts),build_targets(q,m,r,start='2026-01-05',end='2026-01-30',permitted_end='2026-01-30'))
  self.assertEqual(max(p.reads),'2025-12-28');self.assertEqual(receipts[0]['source_month'],'2025-11')
  self.assertAlmostEqual(sum(t['szse_value_momentum_equal']['2026-01-05']['weights'].values()),.95)
  self.assertEqual(receipts[0]['skipped_ranking_month'],'2025-12')
  with self.assertRaises(ValueError):build_targets(p,m,r,start='2026-01-05',end='2026-01-30',permitted_end='2026-01-29')

if __name__=='__main__':unittest.main()
