from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from stock_rsi.calendar import TradingCalendar
from stock_rsi.models import Decision
from stock_rsi.execution_cost import ExecutionCostBroker
try:
    from stock_rsi.mainboard_daily_proxy import execution_rows
    from scripts.replay_low_operating_proxy_targets import simulate_low_operating_proxy
    from scripts import run_low_operating_proxy_pre2026 as runner
except ImportError:execution_rows=simulate_low_operating_proxy=runner=None

POLICY={'simulated_warning_buy_agreement':True,'warning_daily_buy_cap':500000,'warnings':{'SZ002092':{'start':'2024-05-21','end':'2025-05-19','published_on':'2024-05-18','rate':'0.05','source_sha256':'a'*64}}}
def bar(day,code='SZ002092',st='1',price='4.16'):
    return {'date':day.isoformat(),'code':code[:2].lower()+'.'+code[2:],'open':price,'close':price,'high':price,'low':price,'preclose':'4.16','volume':'1000000','amount':'','isST':st,'tradestatus':'1'}
def order(day,quantity=100,action='BUY',code='SZ002092'):
    return {'security_id':code,'status':'PENDING','action':action,'quantity':quantity,'eligible_at':day.isoformat()+'T09:30:00+08:00','expires_at':day.isoformat()+'T09:30:00+08:00'}
def sample():
    ss=['2023-12-29','2024-01-02','2024-12-31','2025-01-02','2025-12-31'];cal=TradingCalendar(ss);bars={'SZ000001':{d:{**bar(date.fromisoformat(d),'SZ000001','0','10.00'),'preclose':'10.00'} for d in ss}}
    targets={'2024-01-02':{'as_of':'2023-12-29','weights':{'SZ000001':.95}},'2025-01-02':{'as_of':'2024-12-31','weights':{'SZ000001':.95}}}
    return cal,bars,targets

class LowOperatingProxyTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(execution_rows,'ST-aware daily proxy missing');self.assertIsNotNone(runner)
    def test_cent_rounded_warning_and_ordinary_bands(self):
        d=date(2024,6,3)
        for st,want in [('1',('4.37','3.95')),('0',('4.58','3.74'))]:
            v=execution_rows(d,{'SZ002092':bar(d,st=st)},[order(d)],POLICY)[0];self.assertEqual((v['limit_up'],v['limit_down']),want)
    def test_unknown_warning_date_permission_and_cumulative_cap_fail(self):
        d=date(2024,6,3)
        cases=[(d,'SZ002092',False,100),(d,'SZ002092',True,500001),(d,'SZ002093',True,100),(date(2025,6,3),'SZ002092',True,100)]
        for at,code,agree,quantity in cases:
            p=deepcopy(POLICY);p['simulated_warning_buy_agreement']=agree
            with self.subTest(code=code,at=at,quantity=quantity),self.assertRaises(ValueError):execution_rows(at,{code:bar(at,code)},[order(at,quantity,code=code)],p)
        with self.assertRaises(ValueError):execution_rows(d,{'SZ002092':bar(d)},[order(d,300000),order(d,300000)],POLICY)
    def test_suspension_does_not_invent_price_or_require_buy_permission(self):
        d=date(2024,6,3);v=bar(d);v.update(tradestatus='0',open='',preclose='');p=deepcopy(POLICY);p['simulated_warning_buy_agreement']=False
        out=execution_rows(d,{'SZ002092':v},[order(d)],p)[0];self.assertTrue(out['suspended']);self.assertNotIn('open',out)
    def test_limit_open_prevents_fill_and_valid_open_preserves_t1(self):
        ds=['2024-06-03','2024-06-04'];cal=TradingCalendar(ds);d=cal.days[0]
        for price,count in [('4.37',0),('4.16',1)]:
            b=ExecutionCostBroker(cal,'10000',extra_cost_bps=40);at=cal.at(d,'09:00:00');b.submit(Decision('BUY','SZ002092',100,('e',),'fixture','s'),at)
            b.on_market_open(execution_rows(d,{'SZ002092':bar(d,price=price)},b.orders,POLICY));self.assertEqual(len(b.fills),count)
            if count:
                b.submit(Decision('SELL','SZ002092',100,('e',),'fixture','t'),cal.at(d,'09:00:01'));b.on_market_open(execution_rows(d,{'SZ002092':bar(d)},b.orders,POLICY));self.assertEqual(len(b.fills),1)
    def test_continuous_replay_keeps_integer_cash_and_original_boundary_guards(self):
        cal,bars,targets=sample();case=simulate_low_operating_proxy(cal,bars,(),targets,'10000',lifecycles={},policy=POLICY)
        self.assertEqual(len(case['intents']),2);self.assertTrue(all(type(v['quantity']) is int and v['quantity']%100==0 for v in case['fills']));self.assertTrue(all(v['cash']>=0 for v in case['days']))
        life={'SZ000001':{'kind':'DELISTING_END','effective_date':'2024-12-31','verified_primary_boundary':True,'primary_document_sha256':'a'*64}}
        with self.assertRaises(ValueError) as cm:simulate_low_operating_proxy(cal,bars,(),targets,'10000',lifecycles=life,policy=POLICY)
        self.assertTrue(cm.exception.account_failure_state['owned_shares'])
    def auth(self,p):
        cal,bars,targets=sample();return {'calendar':cal,'bars':bars,'events':(),'targets':targets,'lifecycles':{},'policy':POLICY,'initial_CNY':'10000','extra_bps':[20,40],'known':{str(p):runner.sha(p)},'request_sha256':'synthetic','formation_receipts':[],'event_receipts':[]}
    def test_both_complete_cost_cases_precede_successful_summary(self):
        with TemporaryDirectory() as t:
            root=Path(t);p=root/'input';p.write_text('fixed');auth=self.auth(p);events=[];real=simulate_low_operating_proxy;summary=runner.summarize_case
            def simulate(*a,**kw):events.append('case');return real(*a,**kw)
            def summarize(*a,**kw):self.assertEqual(events[:2],['case','case']);events.append('summary');return summary(*a,**kw)
            with patch.object(runner,'simulate_low_operating_proxy',side_effect=simulate),patch.object(runner,'summarize_case',side_effect=summarize):value=runner.execute(auth,root/'out')
            self.assertTrue(value['complete']);self.assertEqual(set(value['results_by_extra_bps']),{'20','40'});self.assertFalse(value['objective_achieved']);self.assertEqual(events,['case','case','summary','summary'])
    def test_failed_second_case_publishes_no_annual_returns(self):
        with TemporaryDirectory() as t:
            root=Path(t);p=root/'input';p.write_text('fixed');auth=self.auth(p);real=simulate_low_operating_proxy;count=[]
            def simulate(*a,**kw):
                count.append(1)
                if len(count)==2:raise ValueError('native second-case failure')
                return real(*a,**kw)
            with patch.object(runner,'simulate_low_operating_proxy',side_effect=simulate),patch.object(runner,'summarize_case',side_effect=AssertionError('ROI before both cases')),self.assertRaises(ValueError):runner.execute(auth,root/'out')
            terminal=runner.read(root/'out/terminal.json');self.assertFalse(terminal['complete']);self.assertNotIn('results_by_extra_bps',terminal)
    def test_changed_input_after_first_case_stops_before_second_and_roi(self):
        with TemporaryDirectory() as t:
            root=Path(t);p=root/'input';p.write_text('fixed');auth=self.auth(p);real=simulate_low_operating_proxy;seen=[]
            def simulate(*a,**kw):
                seen.append(True);v=real(*a,**kw);p.write_text('changed');return v
            with patch.object(runner,'simulate_low_operating_proxy',side_effect=simulate),patch.object(runner,'summarize_case',side_effect=AssertionError('ROI on changed input')),self.assertRaises(ValueError):runner.execute(auth,root/'out')
            self.assertEqual(len(seen),1)
