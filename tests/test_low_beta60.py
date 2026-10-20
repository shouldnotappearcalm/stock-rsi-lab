import math,unittest
from datetime import date
from stock_rsi import low_beta60 as subject

def prices(rs):
 a=[100.]
 for r in rs:a.append(a[-1]*(1+r))
 return a
class LowBeta60Tests(unittest.TestCase):
 def test_intercept_slope_and_negative_betas_are_not_volatility_or_absolute_beta(self):
  m=[-.02,0,.02]*20
  x=subject.beta60(prices([.003+.5*r for r in m]),prices(m))
  self.assertAlmostEqual(x['beta'],.5);self.assertAlmostEqual(x['alpha'],.003)
  y=subject.beta60(prices([.003-.5*r for r in m]),prices(m));self.assertAlmostEqual(y['beta'],-.5)
  self.assertEqual(subject.lowest_beta_decile({'B':1.,'A':-1.,'C':-1.}),('A',))
 def test_incomplete_invalid_and_degenerate_histories_fail_closed(self):
  good=prices([-.02,0,.02]*20)
  with self.assertRaises(ValueError):subject.beta60(good[:-1],good)
  for value in (None,0.,-1.,math.nan,math.inf):self.assertIsNone(subject.beta60(good[:-1]+[value],good))
  self.assertIsNone(subject.beta60(good,[100.]*61));self.assertIsNone(subject.beta60([100.]*61,good))
 def test_full_calendar_and_historical_membership_future_prices_are_not_read(self):
  ends=[date(2018,12,28)]+[date(y,m,28) for y in range(2019,2024) for m in range(1,13)]
  m=[-.02,0,.02]*20;mp=prices(m)
  class Source:
   calendar=tuple(ends+[date(2024,1,2),date(2026,1,5)])
   def value(self,code,field,day):
    assert day<='2023-12-28','future market record read'
    if field in ('factor','volume'):return 1.
    i=ends.index(date.fromisoformat(day))
    return mp[i] if code=='SH000905' else prices([.001+(int(code[-3:])+1)/100*r for r in m])[i]
  members={f'SH600{i:03d}':[('2010-01-01','2025-12-31')] for i in range(200)};members['SZ000999']=[('2024-01-02','2025-12-31')]
  t,r=subject.build_targets(Source(),members,end='2024-01-02')
  self.assertEqual(r[0]['return_months'][0],'2019-01');self.assertEqual(r[0]['return_months'][-1],'2023-12');self.assertEqual(r[0]['latest_factor_price_read'],'2023-12-28')
  self.assertEqual(tuple(t['low_beta60']['2024-01-02']['weights']),tuple(f'SH600{i:03d}' for i in range(20)))
  self.assertNotIn('SZ000999',t['eligible_equal_weight']['2024-01-02']['weights'])
  with self.assertRaises(ValueError):subject.build_targets(Source(),members,end='2026-01-05')
 def test_missing_month_may_not_shorten_sixty_month_window(self):
  class Source:
   calendar=tuple([date(2018,12,28)]+[date(y,m,28) for y in range(2019,2024) for m in range(1,13) if (y,m)!=(2020,6)]+[date(2024,1,2)])
   def value(self,*args):return 1.
  with self.assertRaises(ValueError):subject.build_targets(Source(),{},end='2024-01-02')
if __name__=='__main__':unittest.main()
