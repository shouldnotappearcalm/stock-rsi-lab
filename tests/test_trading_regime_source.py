"""Synthetic regime evidence/execution tests; no primary files or market reads."""
import copy
import importlib
import unittest
from datetime import date
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.models import Decision


class TradingRegimeSourceTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('stock_rsi.trading_regime_source')
        except ModuleNotFoundError:self.fail('trading regime source adapter missing')

    def evidence(self,permission=False,interval=True):
        return {'contract':'SSE_MAINBOARD_RISK_WARNING_PRE2026_V1',
            'rule_document':{'source_file':'sse.docx','sha256':'a'*64,'published_on':'2023-02-17','valid_from':'2023-12-29','valid_through':'2025-12-31'},
            'state_intervals':[{'instrument':'SH600079','exchange':'SSE','board':'MAINBOARD','risk_status':'OTHER_RISK_WARNING',
                'effective_from':'2024-12-16','effective_through':'2025-12-31','published_on':'2024-12-13',
                'engineering_available_at':'2024-12-14T00:00:00+08:00','actual_arrival_verified':False,
                'source_file':'issuer.pdf','source_sha256':'b'*64}] if interval else [],
            'account_capabilities':{'risk_warning_buy_permission':permission}}

    def row(self,code='SH600079',st='1',price='10'):
        return dict(date='2024-12-16',code=code[:2].lower()+'.'+code[2:],preclose='10',open=price,high='11',low='9',close='10.10',volume='1000000',amount='10000000',tradestatus='1',isST=st,adjustflag='3')

    def broker(self,orders,*,cash='10000000'):
        cal=TradingCalendar(['2024-12-13','2024-12-16','2024-12-17']);b=ExecutionCostBroker(cal,cash,extra_cost_bps=20,buy_cost_bps=5,sell_cost_bps=15,min_cost=5)
        for side,code,q in orders:b.submit(Decision(side,code,q,('synthetic',),'test','snapshot'),cal.at(date(2024,12,13),'15:05:00'),cal.at(date(2024,12,16),'09:30:00'))
        return b

    def state(self,broker):
        return copy.deepcopy({k:(v.days if k=='calendar' else v) for k,v in broker.__dict__.items()})

    def rows(self,m,rows,evidence,required=None):
        day=date(2024,12,16);bars={c:{str(day):r} for c,r in rows.items()}
        return m.regime_source_rows_on(bars,day,set(rows) if required is None else required,{},evidence=evidence,as_of='2024-12-16T09:25:00+08:00')

    def test_ordinary_batch_and_order_fill_objects_exactly_match_original_broker(self):
        m=self.api();rows={'SH600079':self.row(st='0'),'SZ000001':self.row('SZ000001','0')}
        actual=self.broker([('BUY','SZ000001',100),('SELL','SH600079',100)],cash='100')
        actual.positions={'SH600079':[{'quantity':100,'price':D('9'),'bought_on':date(2024,12,13)}]};expected=copy.deepcopy(actual)
        ordinary,_,regimes=self.rows(m,rows,self.evidence(interval=False))
        expected.on_market_open([{'security_id':c,'trade_date':'2024-12-16','suspended':False,'open':'10','limit_up':'10.950','limit_down':'9.050'} for c in sorted(rows)])
        before=self.state(actual);m.execute_regime_open(actual,date(2024,12,16),ordinary,regimes,validate_only=True);self.assertEqual(self.state(actual),before)
        m.execute_regime_open(actual,date(2024,12,16),ordinary,regimes)
        for key in ('cash','positions','orders','fills','_processed'):self.assertEqual(getattr(actual,key),getattr(expected,key),key)

    def test_proven_st_held_state_keeps_original_row_and_unknown_unused_is_quarantined(self):
        m=self.api();original={'SH600079':self.row(),'SZ000001':self.row('SZ000001','1')};before=copy.deepcopy(original)
        rows,exceptions,regimes=self.rows(m,original,self.evidence(),{'SH600079'})
        self.assertEqual(rows,{'SH600079':original['SH600079']});self.assertEqual(original,before)
        self.assertEqual(regimes['SH600079']['kind'],'SSE_MAINBOARD_RISK_WARNING')
        self.assertEqual(exceptions[0]['instrument'],'SZ000001');self.assertFalse(exceptions[0]['required_by_account'])
        with self.assertRaises(ValueError):self.rows(m,original,self.evidence(),set(original))
        with self.assertRaises(ValueError):self.rows(m,{'SH600079':self.row(st='0')},self.evidence())

    def test_missing_late_overlapping_rule_issuer_or_claimed_arrival_fails_closed(self):
        m=self.api();row={'SH600079':self.row()}
        for change in ('missing','late','overlap','exchange','board','issuer','hash','contract','arrival','time_naive'):
            e=self.evidence()
            if change=='missing':e['state_intervals']=[]
            if change=='late':e['state_intervals'][0]['engineering_available_at']='2024-12-16T15:00:00+08:00'
            if change=='overlap':e['state_intervals'].append(copy.deepcopy(e['state_intervals'][0]))
            if change=='exchange':e['state_intervals'][0]['exchange']='SZSE'
            if change=='board':e['state_intervals'][0]['board']='STAR'
            if change=='issuer':e['state_intervals'][0]['instrument']='SZ000001'
            if change=='hash':e['rule_document']['sha256']='bad'
            if change=='contract':e['contract']='OTHER'
            if change=='arrival':e['state_intervals'][0]['actual_arrival_verified']=True
            if change=='time_naive':e['state_intervals'][0]['engineering_available_at']='2024-12-14T00:00:00'
            with self.subTest(change=change),self.assertRaises(ValueError):self.rows(m,row,e)

    def test_half_up_one_cent_minimum_and_positive_lower_band(self):
        m=self.api()
        self.assertEqual(m.risk_warning_limits('10'),(D('10.50'),D('9.50')))
        self.assertEqual(m.risk_warning_limits('0.10'),(D('.11'),D('.09')))
        self.assertEqual(m.risk_warning_limits('0.03'),(D('.04'),D('.02')))
        self.assertEqual(m.risk_warning_limits('0.01'),(D('.02'),D('.01')))
        for ref in ('0','-1','NaN','10.001'):
            with self.assertRaises(ValueError):m.risk_warning_limits(ref)

    def test_st_sell_limit_annotation_boundary_rejection_and_t1_preserved(self):
        m=self.api()
        for price,expected in [('9.50','UNFILLED_MARKET_CONSTRAINT'),('9.60','FILLED')]:
            b=self.broker([('SELL','SH600079',100)]);b.positions={'SH600079':[{'quantity':100,'price':D('10'),'bought_on':date(2024,12,13)}]}
            rows,_,regimes=self.rows(m,{'SH600079':self.row(price=price)},self.evidence())
            m.execute_regime_open(b,date(2024,12,16),rows,regimes)
            self.assertEqual(b.orders[0]['status'],expected);self.assertEqual(b.orders[0]['order_type'],'LIMIT');self.assertEqual(b.orders[0]['limit_price'],'9.50')
        b=self.broker([('SELL','SH600079',100)]);b.positions={'SH600079':[{'quantity':100,'price':D('10'),'bought_on':date(2024,12,16)}]}
        rows,_,regimes=self.rows(m,{'SH600079':self.row()},self.evidence());m.execute_regime_open(b,date(2024,12,16),rows,regimes)
        self.assertEqual(b.orders[0]['status'],'UNFILLED_CASH_OR_T1');self.assertFalse(b.fills)

    def test_buy_permission_and_cumulative_cap_reject_without_resizing_or_suspension(self):
        m=self.api()
        for permission,quantity,already,expected in [(False,100,0,'UNFILLED_RISK_WARNING_PERMISSION'),(True,500100,0,'UNFILLED_RISK_WARNING_BUY_CAP'),(True,200,499900,'UNFILLED_RISK_WARNING_BUY_CAP'),(True,500000,0,'FILLED')]:
            b=self.broker([('BUY','SH600079',quantity)]);row=self.row();rows,_,regimes=self.rows(m,{'SH600079':row},self.evidence(permission=permission))
            if already:b.fills.append({'security_id':'SH600079','action':'BUY','quantity':already,'execution_at':'2024-12-16T01:30:00+00:00'})
            before=self.state(b);audit=m.execute_regime_open(b,date(2024,12,16),rows,regimes,validate_only=True);self.assertEqual(self.state(b),before)
            m.execute_regime_open(b,date(2024,12,16),rows,regimes)
            self.assertEqual(b.orders[0]['quantity'],quantity);self.assertEqual(b.orders[0]['status'],expected);self.assertEqual(b.orders[0]['order_type'],'LIMIT');self.assertEqual(b.orders[0]['limit_price'],'10.50')
            self.assertEqual(row['tradestatus'],'1')

    def test_bad_second_open_or_regime_is_atomic_for_entire_batch(self):
        m=self.api()
        for change in ('outside','tick','wrongrule','wrongissuer'):
            b=self.broker([('BUY','SZ000001',100),('SELL','SH600079',100)]);b.positions={'SH600079':[{'quantity':100,'price':D('10'),'bought_on':date(2024,12,13)}]}
            rows,_,regimes=self.rows(m,{'SH600079':self.row(),'SZ000001':self.row('SZ000001','0')},self.evidence())
            if change=='outside':rows['SH600079']['open']='10.51'
            if change=='tick':rows['SH600079']['open']='10.001'
            if change=='wrongrule':regimes['SH600079']['evidence']['contract']='wrong'
            if change=='wrongissuer':rows['SH600079']['code']='sh.600080'
            before=self.state(b)
            with self.subTest(change=change),self.assertRaises(ValueError):m.execute_regime_open(b,date(2024,12,16),rows,regimes)
            self.assertEqual(self.state(b),before)

    def test_buy_upper_touch_and_expiry_keep_existing_broker_rules(self):
        m=self.api();b=self.broker([('BUY','SH600079',100)])
        rows,_,regimes=self.rows(m,{'SH600079':self.row(price='10.50')},self.evidence(permission=True))
        m.execute_regime_open(b,date(2024,12,16),rows,regimes)
        self.assertEqual(b.orders[0]['status'],'UNFILLED_MARKET_CONSTRAINT');self.assertEqual(b.fills,[])
        expired=self.broker([('BUY','SH600079',100)]);day=date(2024,12,17);row=self.row();row['date']=day.isoformat()
        rows,_,regimes=m.regime_source_rows_on({'SH600079':{str(day):row}},day,{'SH600079'},{},evidence=self.evidence(),as_of='2024-12-17T09:25:00+08:00')
        m.execute_regime_open(expired,day,rows,regimes)
        self.assertEqual(expired.orders[0]['status'],'EXPIRED');self.assertNotIn('order_type',expired.orders[0]);self.assertEqual(expired.fills,[])

    def test_close_clock_regime_cannot_be_used_retroactively_at_open(self):
        m=self.api();b=self.broker([('SELL','SH600079',100)]);day=date(2024,12,16);row=self.row()
        rows,_,regimes=m.regime_source_rows_on({'SH600079':{str(day):row}},day,{'SH600079'},{},evidence=self.evidence(),as_of='2024-12-16T15:05:00+08:00')
        before=self.state(b)
        with self.assertRaises(ValueError):m.execute_regime_open(b,day,rows,regimes)
        self.assertEqual(self.state(b),before)

    def test_phase_whitelists_do_not_expose_future_fields_or_parse_them(self):
        m=self.api();row=self.row();row['unregistered_future_signal']='forbidden'
        pre=m.phase_market_view(row,'PREOPEN');opened=m.phase_market_view(row,'OPEN');closed=m.phase_market_view(row,'CLOSE')
        self.assertNotIn('open',pre)
        for k in ('high','low','close','volume','amount'):
            self.assertNotIn(k,pre);self.assertNotIn(k,opened);self.assertIn(k,closed)
        self.assertNotIn('unregistered_future_signal',closed)
        b=self.broker([('SELL','SH600079',100)]);b.positions={'SH600079':[{'quantity':100,'price':D('10'),'bought_on':date(2024,12,13)}]}
        row.update(close='not parsed',high=object(),low=object(),volume='not parsed',amount='not parsed')
        rows,_,regimes=self.rows(m,{'SH600079':row},self.evidence())
        m.execute_regime_open(b,date(2024,12,16),rows,regimes)
        self.assertEqual(b.orders[0]['status'],'FILLED')

if __name__=='__main__':unittest.main()
