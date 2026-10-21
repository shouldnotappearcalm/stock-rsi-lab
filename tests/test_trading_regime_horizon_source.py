"""Synthetic SSE epoch tests; no provider, document, network or account replay."""
import copy
import importlib
import unittest
from datetime import date
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.models import Decision
from tests.test_trading_regime_source import TradingRegimeSourceTests as Base

class TradingRegimeHorizonTests(Base):
    def api(self):return importlib.import_module('stock_rsi.trading_regime_horizon_source')

    def evidence(self,permission=False,interval=True):
        original=super().evidence(permission,interval)
        original['contract']='SSE_MAINBOARD_RISK_WARNING_HORIZON_V1'
        original.pop('rule_document')
        original['rule_epochs']=[
            {'source_file':'sse2023.docx','sha256':'a'*64,'published_on':'2023-02-17',
             'engineering_available_at':'2023-02-18T00:00:00+08:00','actual_arrival_verified':False,
             'valid_from':'2023-12-29','valid_through':'2026-07-05','limit_ratio':'0.05'},
            {'source_file':'sse2026.docx','sha256':'c'*64,'published_on':'2026-04-24',
             'engineering_available_at':'2026-04-25T00:00:00+08:00','actual_arrival_verified':False,
             'valid_from':'2026-07-06','valid_through':'2026-10-20','limit_ratio':'0.10'}]
        for s in original['state_intervals']:s['effective_through']='2026-10-20'
        return original

    def day_case(self,day,price='10',permission=False,side='SELL',q=100):
        m=self.api();cal=TradingCalendar(['2026-07-02','2026-07-03','2026-07-06','2026-07-07'])
        b=ExecutionCostBroker(cal,'10000000',extra_cost_bps=20,buy_cost_bps=5,sell_cost_bps=15,min_cost=5)
        previous=cal.days[cal.days.index(day)-1]
        b.submit(Decision(side,'SH600079',q,('synthetic',),'test','snapshot'),cal.at(previous,'15:05:00'),cal.at(day,'09:30:00'))
        b.positions={'SH600079':[{'quantity':100,'price':D('10'),'bought_on':date(2026,7,2)}]}
        row=self.row(price=price);row['date']=day.isoformat()
        rows,exc,regimes=m.regime_source_rows_on({'SH600079':{str(day):row}},day,{'SH600079'},{},evidence=self.evidence(permission),as_of=str(day)+'T09:25:00+08:00')
        return b,rows,regimes

    def test_missing_late_overlapping_rule_issuer_or_claimed_arrival_fails_closed(self):
        m=self.api()
        for change in ('missing','late','overlap','exchange','board','issuer','hash','contract','arrival','time_naive','epoch_overlap','gap','ratio','pub','epoch_late','epoch_arrival','same_doc'):
            e=self.evidence()
            if change=='missing':e['state_intervals']=[]
            if change=='late':e['state_intervals'][0]['engineering_available_at']='2024-12-16T15:00:00+08:00'
            if change=='overlap':e['state_intervals'].append(copy.deepcopy(e['state_intervals'][0]))
            if change=='exchange':e['state_intervals'][0]['exchange']='SZSE'
            if change=='board':e['state_intervals'][0]['board']='STAR'
            if change=='issuer':e['state_intervals'][0]['instrument']='SZ000001'
            if change=='hash':e['rule_epochs'][0]['sha256']='bad'
            if change=='contract':e['contract']='OTHER'
            if change=='arrival':e['state_intervals'][0]['actual_arrival_verified']=True
            if change=='time_naive':e['state_intervals'][0]['engineering_available_at']='2024-12-14T00:00:00'
            if change=='epoch_overlap':e['rule_epochs'][0]['valid_through']='2026-07-06'
            if change=='gap':e['rule_epochs'][1]['valid_from']='2026-07-07'
            if change=='ratio':e['rule_epochs'][0]['limit_ratio']='0.10'
            if change=='pub':e['rule_epochs'][1]['published_on']='2026-04-23'
            if change=='epoch_late':e['rule_epochs'][1]['engineering_available_at']='2026-07-06T10:00:00+08:00'
            if change=='epoch_arrival':e['rule_epochs'][1]['actual_arrival_verified']=True
            if change=='same_doc':e['rule_epochs'][1]['sha256']=e['rule_epochs'][0]['sha256']
            with self.subTest(change=change),self.assertRaises(ValueError):self.rows(m,{'SH600079':self.row()},e)

    def test_hard_july_epoch_switch_does_not_apply_future_rule_early(self):
        m=self.api()
        for day,upper,lower in [(date(2026,7,3),'10.50','9.50'),(date(2026,7,6),'11.00','9.00')]:
            b,rows,regimes=self.day_case(day)
            result=m.execute_regime_open(b,day,rows,regimes)
            self.assertEqual(result[0]['limit_up'],upper);self.assertEqual(result[0]['limit_down'],lower)
            self.assertEqual(b.orders[0]['limit_price'],lower);self.assertEqual(b.orders[0]['status'],'FILLED')
        b,rows,regimes=self.day_case(date(2026,7,3),price='10.60');before=self.state(b)
        with self.assertRaises(ValueError):m.execute_regime_open(b,date(2026,7,3),rows,regimes)
        self.assertEqual(self.state(b),before)
        b,rows,regimes=self.day_case(date(2026,7,6),price='10.60')
        m.execute_regime_open(b,date(2026,7,6),rows,regimes);self.assertEqual(b.orders[0]['status'],'FILLED')

    def test_delisting_state_crosses_epoch_but_all_states_global_nonoverlap(self):
        m=self.api();e=self.evidence();e['state_intervals'][0]['risk_status']='DELISTING_RISK_WARNING'
        for d in (date(2026,7,3),date(2026,7,6)):
            meta=m.validate_regime_evidence(e,d,str(d)+'T09:25:00+08:00')
            self.assertEqual(meta['active_states']['SH600079']['risk_status'],'DELISTING_RISK_WARNING')
        extra=copy.deepcopy(e['state_intervals'][0]);extra['risk_status']='OTHER_RISK_WARNING';extra['effective_from']='2026-07-06'
        e['state_intervals'].append(extra)
        with self.assertRaises(ValueError):m.validate_regime_evidence(e,date(2026,7,3),'2026-07-03T09:25:00+08:00')

    def test_ten_percent_low_price_rounding_tick_and_band_touches(self):
        m=self.api()
        for ref,up,down in [('10','11.00','9.00'),('.15','.17','.14'),('.01','.02','.01')]:
            self.assertEqual(m.risk_warning_limits(ref,'0.10'),(D(up),D(down)))
        for ratio in ('0.2',D('.1'),True):
            with self.assertRaises(ValueError):m.risk_warning_limits('10',ratio)
        for side,price in [('BUY','11'),('SELL','9')]:
            b,rows,regimes=self.day_case(date(2026,7,6),price,True,side)
            m.execute_regime_open(b,date(2026,7,6),rows,regimes)
            self.assertEqual(b.orders[0]['status'],'UNFILLED_MARKET_CONSTRAINT')
        b,rows,regimes=self.day_case(date(2026,7,6),'10.001');before=self.state(b)
        with self.assertRaises(ValueError):m.execute_regime_open(b,date(2026,7,6),rows,regimes)
        self.assertEqual(self.state(b),before)

    def test_new_epoch_permission_cap_and_tampered_selection_remain_atomic(self):
        m=self.api();day=date(2026,7,6)
        for permission,q,status in [(False,100,'UNFILLED_RISK_WARNING_PERMISSION'),(True,500100,'UNFILLED_RISK_WARNING_BUY_CAP')]:
            b,rows,regimes=self.day_case(day,permission=permission,side='BUY',q=q)
            m.execute_regime_open(b,day,rows,regimes);self.assertEqual(b.orders[0]['status'],status);self.assertEqual(b.orders[0]['quantity'],q)
        b,rows,regimes=self.day_case(day);regimes['SH600079']['rule_epoch_sha256']='0'*64;before=self.state(b)
        with self.assertRaises(ValueError):m.execute_regime_open(b,day,rows,regimes)
        self.assertEqual(self.state(b),before)

    def test_unused_global_proof_outside_visible_subset_and_ordinary_exception_parity(self):
        m=self.api();e=self.evidence();day=date(2024,12,16)
        row=self.row('SZ000001','1')
        visible={'SZ000001':{str(day):row}}
        from stock_rsi.ordinary_source_scope import ordinary_source_rows_on
        accepted,exceptions,regimes=m.regime_source_rows_on(visible,day,set(),{},evidence=e,as_of=str(day)+'T09:25:00+08:00')
        old,old_ex=ordinary_source_rows_on(visible,day,set(),{})
        self.assertEqual((accepted,exceptions),(old,old_ex));self.assertEqual(regimes,{})
        for required in ({'SH600079'},{'SZ000001'}):
            with self.subTest(required=required),self.assertRaises(ValueError):
                m.regime_source_rows_on(visible,day,required,{},evidence=e,as_of=str(day)+'T09:25:00+08:00')

    def test_second_sorted_security_failure_never_mutates_first_buy(self):
        m=self.api();day=date(2026,7,6);b,rows,regimes=self.day_case(day)
        b.submit(Decision('BUY','SH600004',100,('synthetic',),'test','snapshot'),b.calendar.at(date(2026,7,3),'15:05:00'),b.calendar.at(day,'09:30:00'))
        first=self.row('SH600004','0');first['date']=str(day)
        rows['SH600004']=first;regimes['SH600004']={'kind':'ORDINARY_DAILY_OPEN_PROXY','instrument':'SH600004','source_isST':'0','statutory_band_verified':False}
        self.assertEqual(sorted(rows),['SH600004','SH600079'])
        rows['SH600079']['open']='11.01';before=self.state(b)
        with self.assertRaises(ValueError):m.execute_regime_open(b,day,rows,regimes)
        self.assertEqual(self.state(b),before)

    def test_immutable_phase_traps_and_outside_horizon(self):
        m=self.api()
        class Trap(dict):
            def __getitem__(self,k):
                if k in ('close','high','low','volume','amount'):raise AssertionError('future field accessed')
                return super().__getitem__(k)
        day=date(2026,7,6);b,rows,regimes=self.day_case(day);rows['SH600079']=Trap(rows['SH600079'])
        self.assertNotIn('open',m.phase_market_view(rows['SH600079'],'PREOPEN'))
        m.execute_regime_open(b,day,rows,regimes);self.assertEqual(b.orders[0]['status'],'FILLED')
        for d in (date(2023,12,28),date(2026,10,21)):
            with self.assertRaises(ValueError):m.validate_regime_evidence(self.evidence(),d,str(d)+'T09:25:00+08:00')

# Imported base class is fixture reuse; prevent unittest collecting its old suite twice.
del Base
if __name__=='__main__':unittest.main()
