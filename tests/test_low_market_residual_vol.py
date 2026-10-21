"""Synthetic only: no provider paths, strategy replay, outcomes or network."""
import copy,importlib.util,math,sys,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from stock_rsi import low_market_residual_vol as api
def prices(returns,initial=100.):
 result=[initial]
 for r in returns:result.append(result[-1]*(1+r))
 return result
DEC=tuple(date.fromisoformat(d) for d in ['2023-12-01','2023-12-04','2023-12-05','2023-12-06','2023-12-07','2023-12-08','2023-12-11','2023-12-12','2023-12-13','2023-12-14','2023-12-15','2023-12-18','2023-12-19','2023-12-20','2023-12-21','2023-12-22','2023-12-28','2023-12-29'])
JAN=tuple(date.fromisoformat(d) for d in ['2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-08','2024-01-09','2024-01-10','2024-01-11','2024-01-12','2024-01-15','2024-01-16','2024-01-17','2024-01-18','2024-01-19','2024-01-22','2024-01-23','2024-01-30','2024-01-31'])
class Source:
 calendar=(date(2023,11,30),*DEC,*JAN,date(2024,2,1),date(2026,1,5))
 def __init__(self):
  self.reads=[];self.bad={};x=[-1/64,0.,1/64]*6;e=[1/8192,-2/8192,1/8192]*6;days=self.calendar[:37]
  self.closes={api.MARKET:dict(zip(days,prices(x+x,1024.)))}
  for i in range(10):
   one=[i/16384+(10-i)/4*a+(i+1)*b for a,b in zip(x,e)];two=[-i/16384+(i+1)/4*a+(10-i)*b for a,b in zip(x,e)]
   self.closes[f'SH600{i:03d}']=dict(zip(days,prices(one+two,64.+i)))
 def value(self,code,field,day):
  self.reads.append((code,field,day))
  if day>'2024-01-31':raise AssertionError('future/execution price read')
  if code==api.MARKET and field!='close':raise AssertionError('market source has no volume or factor')
  if (code,field,day) in self.bad:return self.bad[(code,field,day)]
  if field in ('factor','volume'):return 1.
  return self.closes[code].get(date.fromisoformat(day))
def members():
 result={f'SH600{i:03d}':[('2020-01-01','2025-12-31')] for i in range(10)}
 result['SZ000999']=[('2024-02-01','2025-12-31')];result['SH605999']=[('2020-01-01','2023-11-30')];result['SZ300001']=[('2020-01-01','2025-12-31')]
 return result
class ResidualVolTests(unittest.TestCase):
 def setUp(self):self.assertIsNotNone(api,'factor draft implementation is missing')
 def test_exact_intercept_beta_and_n_minus_two_residual_sigma(self):
  x=[-1/64,0.,1/64]*6;e=[1/128,-2/128,1/128]*6;y=[1/256+2*a+b for a,b in zip(x,e)];r=api.fit_residual_volatility(y,x)
  self.assertEqual(r['n'],18);self.assertAlmostEqual(r['alpha'],1/256);self.assertAlmostEqual(r['beta'],2.);self.assertAlmostEqual(r['sigma'],3/256)
  self.assertAlmostEqual(r['sigma']**2,r['sse']/(18-2));self.assertNotAlmostEqual(r['sigma'],math.sqrt(r['sse']/(18-1)))
 def test_beta_and_total_volatility_rank_differ_from_residual_volatility(self):
  x=[-1/64,0.,1/64]*6;e=[1/1024,-2/1024,1/1024]*6
  a=api.fit_residual_volatility([3*z+b for z,b in zip(x,e)],x);b=api.fit_residual_volatility([.125*z+2*v for z,v in zip(x,e)],x)
  self.assertGreater(a['beta'],b['beta']);self.assertGreater(a['total_volatility'],b['total_volatility']);self.assertLess(a['sigma'],b['sigma'])
  self.assertEqual(api.lowest_quintile({'A':a['sigma'],'B':b['sigma']}),('A',))
 def test_affine_market_addition_and_alpha_offset_leave_residual_sigma_unchanged(self):
  x=[-1/64,0.,1/64]*6;e=[1/128,-2/128,1/128]*6;y=[2*a+b for a,b in zip(x,e)];one=api.fit_residual_volatility(y,x);two=api.fit_residual_volatility([v+1/32+4*a for v,a in zip(y,x)],x)
  self.assertAlmostEqual(two['beta'],one['beta']+4);self.assertAlmostEqual(two['alpha'],one['alpha']+1/32);self.assertAlmostEqual(two['sigma'],one['sigma'])
 def test_minimum15_is_local_admission_and_missing_or_degenerate_samples_not_neutral(self):
  self.assertEqual(api.MIN_OBSERVATIONS,15);x=[-1/64,0.,1/64]*5;e=[1/128,-2/128,1/128]*5;y=[a+b for a,b in zip(x,e)]
  self.assertIsNotNone(api.fit_residual_volatility(y,x));self.assertIsNone(api.fit_residual_volatility(y[:-1],x[:-1]));self.assertIsNone(api.fit_residual_volatility(y,[.01]*15));self.assertIsNone(api.fit_residual_volatility(x,x))
  with self.assertRaises(ValueError):api.fit_residual_volatility(y,x[:-1])
  for bad in (None,True,math.nan,math.inf):
   vals=list(y);vals[3]=bad;self.assertIsNone(api.fit_residual_volatility(vals,x))
 def test_fixed_numerical_guard_rejects_tiny_ss_not_only_exact_zero(self):
  self.assertEqual(api.NUMERIC_SS_EPSILON,1e-24)
  x=[-1e-15,0.,1e-15]*5;y=[.01,-.02,.01]*5
  self.assertIsNone(api.fit_residual_volatility(y,x))
  x=[-1/64,0.,1/64]*5;e=[1e-15,-2e-15,1e-15]*5
  self.assertIsNone(api.fit_residual_volatility([a+b for a,b in zip(x,e)],x))
 def test_calendar15_is_admitted_and14_fails_without_shortening_or_filling(self):
  s=Source();s.calendar=(date(2023,11,30),*DEC[:15],date(2024,1,2))
  t,r=api.build_targets(s,members(),end='2024-01-02');self.assertEqual(r[0]['n'],15);self.assertEqual(len(r[0]['close_dates']),16)
  s=Source();s.calendar=(date(2023,11,30),*DEC[:14],date(2024,1,2))
  with self.assertRaises(ValueError):api.build_targets(s,members(),end='2024-01-02')
  self.assertEqual(s.reads,[])
 def test_closes_are_simple_returns_with_scale_invariance_and_strict_invalid_prices(self):
  x=[-1/64,0.,1/64]*6;e=[1/1024,-2/1024,1/1024]*6;y=[.01+2*a+b for a,b in zip(x,e)];a=api.residual_volatility_1m(prices(y),prices(x));b=api.residual_volatility_1m(prices(y,700.),prices(x,3.))
  self.assertAlmostEqual(a['sigma'],b['sigma']);self.assertAlmostEqual(a['alpha'],.01);self.assertAlmostEqual(a['beta'],2.)
  for bad in (None,True,0.,-1.,math.nan,math.inf):
   close=prices(y);close[5]=bad;self.assertIsNone(api.residual_volatility_1m(close,prices(x)))
  with self.assertRaises(ValueError):api.residual_volatility_1m(prices(y),prices(x)[:-1])
 def test_floor20percent_tie_boundary_and_at_least_one_helper(self):
  for n,expected in [(1,1),(4,1),(5,1),(9,1),(10,2),(14,2),(15,3),(19,3),(20,4),(21,4)]:
   scores={f'C{i:03d}':1. for i in reversed(range(n))};self.assertEqual(api.lowest_quintile(scores),tuple(f'C{i:03d}' for i in range(expected)))
  for scores in ({},{'A':0.},{'A':math.nan},{'A':True}):
   with self.assertRaises(ValueError):api.lowest_quintile(scores)
 def test_two_complete_manual_months_priorclose_historical_membership_and_controls(self):
  s=Source();targets,receipts=api.build_targets(s,members(),end='2024-02-01');self.assertEqual(set(targets),{'low_market_residual_vol_1m','eligible_equal_weight','low_total_vol_1m_control'});self.assertEqual(len(receipts),2)
  r1,r2=receipts;self.assertEqual(r1['return_dates'],[d.isoformat() for d in DEC]);self.assertEqual(r1['baseline_close_day'],'2023-11-30');self.assertEqual(r2['return_dates'],[d.isoformat() for d in JAN]);self.assertEqual(r2['baseline_close_day'],'2023-12-29')
  self.assertEqual(r1['selected'],['SH600000','SH600001']);self.assertEqual(r2['selected'],['SH600009','SH600008']);self.assertEqual(r1['control_selected'],['SH600009','SH600008']);self.assertEqual(r2['control_selected'],['SH600000','SH600001'])
  for row in receipts:
   self.assertEqual(row['minimum_return_observations'],15);self.assertEqual(row['historical_members'],10);self.assertEqual(row['eligible'],10);self.assertFalse(row['controls_selectable']);self.assertEqual(row['formation_at'],row['formation_asof']+'T15:05:00+08:00');self.assertEqual(row['latest_factor_price_read'],row['formation_asof']);self.assertEqual({v['n'] for v in row['fits'].values()},{18})
   self.assertAlmostEqual(sum(targets[api.FAMILIES[0]][row['execution_session']]['weights'].values()),.95)
  self.assertLessEqual(max(d for _,_,d in s.reads),'2024-01-31');self.assertFalse(any(c in ('SZ000999','SH605999','SZ300001') for c,_,_ in s.reads))
 def test_stock_missing_zero_volume_or_factor_entire_month_excluded_without_dropping_rows(self):
  for field,bad in [('close',None),('volume',0.),('factor',0.),('volume',math.nan),('factor',-1.)]:
   s=Source();s.bad[('SH600000',field,'2023-12-12')]=bad;t,r=api.build_targets(s,members(),end='2024-01-31');self.assertEqual(r[0]['eligible'],9);self.assertIn('SH600000',r[0]['excluded']);self.assertNotIn('SH600000',t['eligible_equal_weight']['2024-01-02']['weights'])
  s=Source();s.bad[('SH600000','volume','2023-11-30')]=0.;self.assertIn('SH600000',api.build_targets(s,members(),end='2024-01-31')[1][0]['excluded'])
 def test_market_close_only_missing_or_constant_market_and_small_pool_fail_closed(self):
  s=Source();s.bad[(api.MARKET,'close','2023-12-12')]=None
  with self.assertRaises(ValueError):api.build_targets(s,members(),end='2024-01-31')
  s=Source();s.closes[api.MARKET]={d:100. for d in s.calendar[:37]}
  with self.assertRaises(ValueError):api.build_targets(s,members(),end='2024-01-31')
  for code in range(6):s.bad[(f'SH600{code:03d}','volume','2023-12-12')]=0.
  s=Source()
  for code in range(6):s.bad[(f'SH600{code:03d}','volume','2023-12-12')]=0.
  with self.assertRaisesRegex(ValueError,'five|5'):api.build_targets(s,members(),end='2024-01-31')
 def test_missing_calendar_baseline_or_previous_month_cannot_shorten_window(self):
  s=Source();s.calendar=s.calendar[1:]
  with self.assertRaises(ValueError):api.build_targets(s,members(),end='2024-01-31')
  s=Source();s.calendar=(date(2023,10,31),*DEC,*JAN,date(2024,2,1))
  with self.assertRaises(ValueError):api.build_targets(s,members(),end='2024-01-31')
 def test_2026_cap_and_AsOfPrices_future_attempt_raise_before_delegation(self):
  s=Source()
  with self.assertRaises(ValueError):api.build_targets(s,members(),end='2026-01-05')
  self.assertEqual(s.reads,[]);view=api.AsOfPrices(s,date(2023,12,29))
  with self.assertRaises(ValueError):view.value('SH600000','close','2024-01-02')
  self.assertEqual(s.reads,[])
 def test_each_read_has_a_separate_priorclose_cap_never_its_current_execution_day(self):
  from stock_rsi.prior_close_orders import AsOfPrices
  observed=[]
  class Spy(AsOfPrices):
   def value(self,c,f,d):observed.append((self.as_of.isoformat(),d));return super().value(c,f,d)
  with patch.object(api,'AsOfPrices',Spy):api.build_targets(Source(),members(),end='2024-02-01')
  self.assertTrue(observed);self.assertTrue(all(d<=cap and d<'2026-01-01' for cap,d in observed));self.assertFalse(any(cap=='2023-12-29' and d>cap for cap,d in observed))
if __name__=='__main__':unittest.main()
