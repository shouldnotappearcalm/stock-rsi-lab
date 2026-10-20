"""Hand-calculated ETF fixtures; no downloaded market data or ROI tuning."""
import unittest
from datetime import date
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import Distribution
from stock_rsi.etf_relative_replay import ETFAccount, Relative12Month, execution_bar, replay

CODES=('SH510300','SH510500','SZ159915')
MONTHS=['2022-12-30','2023-01-31','2023-02-28','2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31','2023-09-28','2023-10-31','2023-11-30','2023-12-29']

def event():
 return Distribution('div','SH510300',date(2023,12,20),date(2024,1,2),date(2024,1,3),date(2024,1,4),None,D('.1'),D(0),True)

def decision(side,q):return Decision(side,CODES[0],q,('synthetic',),'synthetic ETF trade','fixture')

class ETFReplayTests(unittest.TestCase):
 def test_total_return_requires13_monthends_and_includes_cash_and_negative_leader(self):
  cal=TradingCalendar(MONTHS);s=Relative12Month(cal)
  for i,day in enumerate(cal.days):
   values={c:D('2') for c in CODES}
   if i==12:values={CODES[0]:D('1.8'),CODES[1]:D('1.85'),CODES[2]:D('1.7')}
   result=s.observe_close(day,values,{CODES[0]:D('.1')} if i==12 else {})
   if i<12:self.assertIsNone(result)
  self.assertEqual(result['leader'],CODES[0])
  self.assertEqual(D(result['scores'][CODES[0]]),D('-.05'))
  self.assertEqual(result['window_monthends'],MONTHS)
  # Identical index returns use fixed code order, not iteration order.
  t=Relative12Month(cal)
  for day in cal.days:r=t.observe_close(day,{c:D('2') for c in reversed(CODES)},{})
  self.assertEqual(r['leader'],'SH510300')

 def test_mathematically_equal_returns_with_nonconstant_path_use_code_tie(self):
  cal=TradingCalendar(MONTHS);signal=Relative12Month(cal)
  for i,day in enumerate(cal.days):
   values={c:D('2') for c in CODES}
   values[CODES[0]]=D({1:'2.123',2:'1.987'}.get(i,'2'))
   r=signal.observe_close(day,values,{})
  self.assertEqual(r['leader'],'SH510300')
  self.assertEqual(r['scores_exact_ratio']['SH510300'],['0','1'])

 def test_rotation_requires_confirmed_sale_then_next_session_original_buy_qty(self):
  cal=TradingCalendar(MONTHS+['2024-01-02','2024-01-31','2024-02-01','2024-02-02']);bars={}
  for day in cal.days:
   bars[day.isoformat()]={c:{'date':day.isoformat(),'open':'2.000','close':'2.000','volume_provider_raw':'100000'} for c in CODES}
   if day>=date(2024,1,31):bars[day.isoformat()][CODES[1]].update(open='3.000',close='3.000')
  x=replay(cal,bars,[],extra_cost_bps=40)
  self.assertEqual([(f['action'],f['execution_at'][:10]) for f in x['fills']],[('BUY','2024-01-02'),('SELL','2024-02-01'),('BUY','2024-02-02')])
  self.assertEqual(x['days'][2]['cash'],D('991450.00'));self.assertEqual(x['days'][2]['positions'],{})
  self.assertEqual(x['fills'][2]['quantity'],315300)
  self.assertEqual(x['funding_intents'][0]['original_formation_quantity'],315300)
  self.assertEqual(x['funding_intents'][0]['status'],'CONFIRMED_SALE_THEN_NEXT_SESSION_BUY')
  bars['2024-02-02'][CODES[1]]['open']='3.100';y=replay(cal,bars,[],extra_cost_bps=40)
  self.assertEqual(x['funding_intents'],y['funding_intents'])
  shortcal=TradingCalendar([d.isoformat() for d in cal.days[:-1]])
  end=replay(shortcal,{k:v for k,v in bars.items() if k!='2024-02-02'},[],extra_cost_bps=40)
  self.assertEqual(end['funding_intents'][0]['status'],'CANCELLED_CALENDAR_END')
  bars['2024-02-01'][CODES[0]]['open']='1.800';z=replay(cal,bars,[],extra_cost_bps=40)
  self.assertEqual(len(z['fills']),1)
  self.assertEqual(z['funding_intents'][0]['status'],'CANCELLED_SELL_NOT_FULLY_FILLED')

 def test_clock_and_missing_asset_fail_closed(self):
  cal=TradingCalendar(MONTHS);s=Relative12Month(cal)
  with self.assertRaises(ValueError):s.observe_close(cal.days[0],{CODES[0]:D('2')},{})
  s.observe_close(cal.days[0],{c:D('2') for c in CODES},{})
  with self.assertRaises(ValueError):s.observe_close(cal.days[0],{c:D('2') for c in CODES},{})
  with self.assertRaises(ValueError):s.observe_close(cal.days[2],{c:D('2') for c in CODES},{})

 def test_etf_fee_tick_and_record_ex_pay_accounting(self):
  cal=TradingCalendar(['2023-12-29','2024-01-02','2024-01-03','2024-01-04','2024-01-05'])
  a=ETFAccount(cal,'10000',[event()],extra_cost_bps=40)
  a.broker.submit(decision('BUY',100),cal.at(cal.days[0],'15:05:00'))
  a.start_day(cal.days[1]);b=execution_bar(cal.days[1],CODES[0],D('2'),{'open':'2.001','close':'2.000','volume_provider_raw':'1'},D(0));a.broker.on_market_open([b]);a.end_day(cal.days[1])
  self.assertEqual(a.broker.cash,D('9794.10')) # 200.10 gross + 5 min + .80 extra
  a.start_day(cal.days[2]);a.end_day(cal.days[2])
  self.assertEqual(a.wealth({CODES[0]:'1.9'})['cash_receivable'],D('10.00'))
  self.assertEqual(a.wealth({CODES[0]:'1.9'})['equity'],D('9994.10'))
  a.start_day(cal.days[3]);a.end_day(cal.days[3]);self.assertEqual(a.broker.cash,D('9794.10'))
  a.start_day(cal.days[4]);self.assertEqual(a.broker.cash,D('9804.10'))
  self.assertEqual(a.wealth({CODES[0]:'1.9'})['cash_receivable'],0)
  self.assertEqual(a.broker._cost(D('100000'),'BUY'),D('450.00'))
  self.assertEqual(a.broker._cost(D('100000'),'SELL'),D('450.00'))

 def test_band_rounding_and_t1(self):
  day=date(2024,1,2);raw={'open':'2.001','close':'2','volume_provider_raw':'1'}
  sse=execution_bar(day,CODES[0],D('2.006'),raw,D('.1'))
  self.assertEqual(sse['limit_up'],'2.097');self.assertEqual(sse['limit_down'],'1.715')
  sz=execution_bar(day,CODES[2],D('2.006'),raw,D(0));self.assertEqual(sz['limit_up'],'2.407')
  with self.assertRaises(ValueError):execution_bar(day,CODES[0],D('2'),{**raw,'open':'2.0011'},D(0))
  with self.assertRaises(ValueError):execution_bar(day,CODES[0],D('2'),{**raw,'volume_provider_raw':'0'},D(0))
  cal=TradingCalendar(['2023-12-29','2024-01-02','2024-01-03']);a=ETFAccount(cal,'10000',[],extra_cost_bps=20)
  a.broker.submit(decision('BUY',100),cal.at(cal.days[0],'15:05:00'))
  a.broker.on_market_open([execution_bar(day,CODES[0],D('2'),raw,D(0))])
  a.broker.submit(decision('SELL',100),cal.at(day,'09:00:00'))
  a.broker._processed.clear() # independent same-session T+1 rejection fixture
  a.broker.on_market_open([execution_bar(day,CODES[0],D('2'),raw,D(0))])
  self.assertEqual(a.broker.orders[-1]['status'],'UNFILLED_CASH_OR_T1')

 def test_future_gap_cannot_change_formation_qty_and_ledger_conserves(self):
  cal=TradingCalendar(MONTHS+['2024-01-02','2024-01-03']);bars={}
  for day in cal.days:bars[day.isoformat()]={c:{'date':day.isoformat(),'open':'2.000','close':'2.000','volume_provider_raw':'100000'} for c in CODES}
  x=replay(cal,bars,[],extra_cost_bps=40)
  bars['2024-01-02'][CODES[0]]['open']='2.100'
  y=replay(cal,bars,[],extra_cost_bps=40)
  self.assertEqual(x['intents'][0],y['intents'][0]);self.assertEqual(x['intents'][0]['decisions'][0]['quantity'],475000)
  self.assertEqual(x['days'][0]['equity'],D('995725.00')) # 950000*.0045 fees
  self.assertEqual(x['days'][0]['positions'],{CODES[0]:475000})
  self.assertEqual(x['days'][0]['cash'],D('45725.00'))
  self.assertEqual(x['days'][0]['cash_receivable'],0)
  self.assertEqual(x['ledger_checks'],'ALL_SESSIONS_CASH_UNITS_EQUITY_RECONCILED')
  # Daily close after formation cannot change that earlier snapshot either.
  bars['2024-01-03'][CODES[0]]['close']='2.150'
  z=replay(cal,bars,[],extra_cost_bps=40);self.assertEqual(x['intents'][0],z['intents'][0])

if __name__=='__main__':unittest.main()
