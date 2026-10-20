"""Exact hand-calculated lag endpoints and unchanged physical-account behavior."""
import copy
import unittest
from datetime import date
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from stock_rsi.etf_relative_replay import CODES, Relative12Month, replay
from stock_rsi.etf_prior2_12 import Prior2To12
from stock_rsi.etf_replay_v2 import replay_with_signal
from tests.test_etf_relative_replay import MONTHS,event

ORIGINAL_REASON='fixed three domestic ETF relative12m, prior-close 95% target'

class ETFLaggedTests(unittest.TestCase):
 def test_actual11month_endpoint_excludes_latest_complete_month(self):
  cal=TradingCalendar(MONTHS);old=Relative12Month(cal);lag=Prior2To12(cal)
  for i,day in enumerate(cal.days):
   values={c:D('2') for c in CODES}
   if i==11:values[CODES[1]]=D('2.4')
   if i==12:values.update({CODES[0]:D('4'),CODES[1]:D('2.4')})
   a=old.observe_close(day,values,{});b=lag.observe_close(day,values,{})
   if i<12:self.assertIsNone(b)
  self.assertEqual(a['leader'],'SH510300');self.assertEqual(b['leader'],'SH510500')
  self.assertEqual(b['scores_exact_ratio']['SH510500'],['1','5'])
  self.assertEqual(b['signal_start_monthend'],'2022-12-30')
  self.assertEqual(b['signal_end_monthend'],'2023-11-30')
  self.assertEqual(b['excluded_monthend'],'2023-12-29');self.assertEqual(b['return_month_count'],11)

 def test_recent_month_price_and_cash_cannot_change_signal_rank(self):
  cal=TradingCalendar(MONTHS);a=Prior2To12(cal);b=Prior2To12(cal)
  for i,day in enumerate(cal.days):
   first={c:D('2') for c in CODES};second=first.copy()
   if i==11:first[CODES[1]]=second[CODES[1]]=D('2.4')
   if i==12:second.update({CODES[0]:D('6'),CODES[1]:D('1.2')})
   x=a.observe_close(day,first,{});y=b.observe_close(day,second,{CODES[2]:D('2')} if i==12 else {})
  self.assertEqual(x['scores_exact_ratio'],y['scores_exact_ratio']);self.assertEqual(x['leader'],y['leader'])

 def test_cash_is_included_before_excluded_month_and_ties_remain_exact(self):
  cal=TradingCalendar(MONTHS);cash=Prior2To12(cal);tie=Prior2To12(cal)
  for i,day in enumerate(cal.days):
   prices={c:D('2') for c in CODES};path=prices.copy();flow={}
   if i==11:prices[CODES[0]]=D('1.9');flow[CODES[0]]=D('.2')
   path[CODES[0]]=D({1:'2.123',2:'1.987'}.get(i,'2'))
   if i==12:path[CODES[0]]=D('3')
   x=cash.observe_close(day,prices,flow);y=tie.observe_close(day,path,{})
  self.assertEqual(x['scores_exact_ratio']['SH510300'],['1','20'])
  self.assertEqual(y['scores_exact_ratio']['SH510300'],['0','1']);self.assertEqual(y['leader'],'SH510300')

 def test_new_engine_preserves_frozen_baseline_ledger_including_dividends_and_staged_rotation(self):
  cal=TradingCalendar(MONTHS+['2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-31','2024-02-01','2024-02-02'])
  bars={}
  for day in cal.days:
   bars[day.isoformat()]={c:{'date':day.isoformat(),'open':'2.000','close':'2.000','volume_provider_raw':'100000'} for c in CODES}
   if day>=date(2024,1,3):bars[day.isoformat()][CODES[0]].update(open='1.900',close='1.900')
   if day>=date(2024,1,31):bars[day.isoformat()][CODES[1]].update(open='3.000',close='3.000')
  for extra in (20,40):
   expected=replay(cal,bars,[event()],extra_cost_bps=extra)
   actual=replay_with_signal(cal,bars,[event()],signal_factory=Relative12Month,decision_reason=ORIGINAL_REASON,extra_cost_bps=extra)
   self.assertEqual(actual,expected)
   self.assertEqual(actual['days'][1]['cash_receivable'],D('47500.00'))
   self.assertEqual(actual['days'][2]['dividend_cash_available'],0)
   self.assertEqual(actual['days'][3]['dividend_cash_available'],D('47500.00'))
   self.assertEqual(len(actual['funding_intents']),1)

 def test_next_open_is_not_available_to_lagged_policy(self):
  cal=TradingCalendar(MONTHS+['2024-01-02','2024-01-03']);bars={d:{c:{'date':d,'open':'2.000','close':'2.000','volume_provider_raw':'100000'} for c in CODES} for d in MONTHS+['2024-01-02','2024-01-03']}
  first=replay_with_signal(cal,bars,[],signal_factory=Prior2To12,decision_reason='prior2-12',extra_cost_bps=40)
  changed=copy.deepcopy(bars);changed['2024-01-02'][CODES[0]]['open']='2.100';changed['2024-01-03'][CODES[1]]['close']='3.000'
  second=replay_with_signal(cal,changed,[],signal_factory=Prior2To12,decision_reason='prior2-12',extra_cost_bps=40)
  self.assertEqual(first['intents'][0],second['intents'][0]);self.assertEqual(first['intents'][0]['decisions'][0]['quantity'],475000)

if __name__=='__main__':unittest.main()
