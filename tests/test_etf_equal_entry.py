import copy,unittest
from datetime import date
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from stock_rsi.raw_share_account import Distribution
from stock_rsi import etf_equal_entry as subject
from stock_rsi import etf_replay_v3 as engine
CODES=('SH510300','SH510500','SZ159915')
DATES=['2023-12-29','2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-31','2024-02-01']
def bars():return {d:{c:{'date':d,'open':'2.000','close':'2.000','volume_provider_raw':'100000'} for c in CODES} for d in DATES}
def run(data=None,events=()):return engine.replay_with_signal(TradingCalendar(DATES),data or bars(),events,signal_factory=subject.InitialEqualWeight,decision_reason='fixed initial equal-weight buy and hold',extra_cost_bps=40,initial_cash='12000')
class EqualEntryTests(unittest.TestCase):
 def test_exact_rational_thirds_do_not_lose_one_hundred_units_at_boundary(self):
  orders=subject.plan_rational_targets('12000',{}, {c:['19','60'] for c in CODES},{c:'2' for c in CODES})
  self.assertEqual(orders,(('BUY','SH510300',1900),('BUY','SH510500',1900),('BUY','SZ159915',1900)))
  with self.assertRaises(ValueError):subject.plan_rational_targets('12000',{}, {c:['1','2'] for c in CODES},{c:'2' for c in CODES})
 def test_only_initial_decision_future_prices_cannot_change_quantities(self):
  x=run();p=bars();p['2024-01-02'][CODES[0]]['open']='2.100';p['2024-01-31'][CODES[1]]['close']='3.000';y=run(p)
  self.assertEqual(x['intents'],y['intents']);self.assertEqual(len(x['intents']),1);self.assertEqual(len(x['fills']),3)
  self.assertEqual(x['days'][0]['cash'],D('539.40')) # three*(3800 +5min +15.20extra)
  self.assertEqual(x['days'][0]['positions'],{c:1900 for c in CODES})
 def test_nonzero_distribution_is_receivable_then_cash_after_payment_never_reinvested(self):
  e=Distribution('cash',CODES[0],date(2023,12,20),date(2024,1,2),date(2024,1,3),date(2024,1,4),None,D('.1'),D(0),True)
  p=bars()
  for d in DATES[2:]:p[d][CODES[0]].update(open='1.900',close='1.900')
  x=run(p,[e]);self.assertEqual(x['days'][1]['cash_receivable'],D('190.00'));self.assertEqual(x['days'][2]['dividend_cash_available'],0)
  self.assertEqual(x['days'][3]['dividend_cash_available'],D('190.00'));self.assertEqual(x['days'][3]['cash'],D('729.40'));self.assertEqual(len(x['fills']),3)
 def test_invalid_initial_window_or_missing_asset_reject(self):
  with self.assertRaises(ValueError):subject.InitialEqualWeight(TradingCalendar(['2024-01-02','2024-01-03']))
  p=bars();del p['2023-12-29'][CODES[0]]
  with self.assertRaises(ValueError):run(p)
if __name__=='__main__':unittest.main()
