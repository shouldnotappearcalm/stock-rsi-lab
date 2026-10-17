import copy
import unittest
from decimal import Decimal
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import Snapshot, canonical
from stock_rsi.models import Decision
from stock_rsi.time import parse_time
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.intraday_tape import aggregate_minutes
from scripts.tdx_history_checks import minute_labels


def decision(action,qty,code='A'):
    snap=Snapshot(canonical({'as_of':'2024-01-02T07:05:00+00:00','records':[{'record_id':'e'}]}))
    return Decision.from_dict({'action':action,'security_id':code,'quantity':qty,'evidence_ids':['e'],'reason':'literal'},snap)


def bar(start,end,volume=10000,buy='10',sell='10',code='A'):
    return {'security_id':code,'start':start,'end':end,'available_at':end,'volume_lower_shares':volume,
            'buy_price':buy,'sell_price':sell,'evidence_id':start+'/'+end}


class IntradayBrokerTests(unittest.TestCase):
    def setUp(self):
        self.calendar=TradingCalendar(['2024-01-02','2024-01-03'])
        self.at=parse_time('2024-01-02T15:05:00+08:00')
        self.refs={'A':{'limit_up':'11','limit_down':'9','suspended':False}}
        self.prev=bar('2024-01-03T09:30:00+08:00','2024-01-03T09:35:00+08:00')
        self.curr=bar('2024-01-03T09:35:00+08:00','2024-01-03T09:40:00+08:00')

    def broker(self,cash='20000'):
        return IntradayBroker(self.calendar,cash,participation_bps=1000,extra_cost_bps=0)

    def submit(self,broker,decisions):
        return broker.replace_pending_intent(decisions,self.at,parse_time('2024-01-03T09:30:00+08:00'))

    def test_child_plan_uses_past_capacity_and_matching_cannot_overspend_or_duplicate(self):
        broker=self.broker();self.submit(broker,[decision('BUY',2000)])
        children=broker.plan_window(self.curr['start'],self.curr['end'],{'A':self.prev},self.refs)
        self.assertEqual(children[0]['quantity'],1000)
        self.assertEqual(children[0]['submitted_at'],'2024-01-03T01:35:00+00:00')
        changed=copy.deepcopy(self.curr);changed.update(volume_lower_shares=5000,buy_price='10.5',sell_price='10.5')
        fills=broker.on_window(self.curr['start'],self.curr['end'],{'A':self.prev},{'A':changed},self.refs)
        self.assertEqual(fills[0]['quantity'],500)
        self.assertEqual(fills[0]['price'],'10.5')
        self.assertEqual(broker.cash,Decimal('14745'))
        self.assertEqual(broker.orders[0]['remaining'],1500)
        self.assertEqual(broker.on_window(self.curr['start'],self.curr['end'],{'A':self.prev},{'A':changed},self.refs),[])
        with self.assertRaises(ValueError):broker.on_window(self.curr['start'],self.curr['end'],{'A':self.prev},{'A':self.curr},self.refs)

    def test_sale_cash_cannot_fund_buy_within_same_window_and_t_plus_one_remains(self):
        broker=self.broker('100');broker.positions={'A':[{'quantity':1000,'price':Decimal('10'),'bought_on':self.calendar.days[0]}]}
        self.submit(broker,[decision('SELL',1000),decision('BUY',1000,'B')])
        refs={**self.refs,'B':self.refs['A']};prev={'A':self.prev,'B':self.prev|{'security_id':'B'}};curr={'A':self.curr,'B':self.curr|{'security_id':'B'}}
        first=broker.on_window(self.curr['start'],self.curr['end'],prev,curr,refs)
        self.assertEqual([f['action'] for f in first],['SELL'])
        following=bar('2024-01-03T09:40:00+08:00','2024-01-03T09:45:00+08:00')
        second=broker.on_window(following['start'],following['end'],curr,{'A':following,'B':following|{'security_id':'B'}},refs)
        self.assertEqual([f['action'] for f in second],['BUY'])
        self.assertGreaterEqual(broker.cash,0)
        self.assertTrue(all(lot['bought_on']==self.calendar.days[1] for lot in broker.positions['B']))

    def test_explicit_children_respect_order_maximum_and_each_pays_minimum_fee(self):
        broker=self.broker('50000000');self.submit(broker,[decision('BUY',1200000)])
        prev=copy.deepcopy(self.prev);prev['volume_lower_shares']=20000000
        curr=copy.deepcopy(self.curr);curr['volume_lower_shares']=20000000
        fill=broker.on_window(curr['start'],curr['end'],{'A':prev},{'A':curr},self.refs)[0]
        self.assertEqual(fill['quantity'],1000000)
        self.assertEqual(broker.orders[0]['remaining'],200000)
        self.assertEqual(len(broker.child_orders),1)
        self.assertEqual(broker.child_orders[0]['order_role'],'EXPLICIT_CHILD_ORDER')
        small=self.broker('10000');self.submit(small,[decision('BUY',200)])
        for p,c in [(self.prev,self.curr),(self.curr,bar('2024-01-03T09:40:00+08:00','2024-01-03T09:45:00+08:00'))]:
            p=copy.deepcopy(p);c=copy.deepcopy(c);p['volume_lower_shares']=c['volume_lower_shares']=1000
            small.on_window(c['start'],c['end'],{'A':p},{'A':c},self.refs)
        self.assertEqual([f['cost'] for f in small.fills],['5.00','5.00'])

    def test_bad_batch_is_atomic_and_lunch_is_not_a_trading_window(self):
        broker=self.broker();self.submit(broker,[decision('BUY',1000)])
        before=copy.deepcopy(broker.orders)
        bad=copy.deepcopy(self.curr);bad['volume_lower_shares']=True
        with self.assertRaises(ValueError):broker.on_window(self.curr['start'],self.curr['end'],{'A':self.prev},{'A':bad},self.refs)
        self.assertEqual(broker.orders,before);self.assertEqual(broker.fills,[])
        with self.assertRaises(ValueError):broker.plan_window('2024-01-03T11:30:00+08:00','2024-01-03T11:35:00+08:00',{'A':self.prev},self.refs)
        with self.assertRaises(ValueError):self.submit(broker,[decision('BUY',101)])
        self.assertEqual(broker.orders,before)

    def test_t_plus_one_odd_tail_and_day_expiry_are_explicit(self):
        broker=self.broker();broker.positions={'A':[{'quantity':1250,'price':Decimal('10'),'bought_on':self.calendar.days[0]}]}
        self.submit(broker,[decision('SELL',103)])
        p=self.prev|{'volume_lower_shares':1000};c=self.curr|{'volume_lower_shares':1000}
        broker.on_window(c['start'],c['end'],{'A':p},{'A':c},self.refs)
        following=bar('2024-01-03T09:40:00+08:00','2024-01-03T09:45:00+08:00',volume=1000)
        broker.on_window(following['start'],following['end'],{'A':c},{'A':following},self.refs)
        self.assertEqual([f['quantity'] for f in broker.fills],[100,3])
        same_day=self.broker();same_day.positions={'A':[{'quantity':100,'price':Decimal('10'),'bought_on':self.calendar.days[1]}]}
        self.submit(same_day,[decision('SELL',100)])
        self.assertEqual(same_day.on_window(c['start'],c['end'],{'A':p},{'A':c},self.refs),[])
        same_day.expire_day(self.calendar.days[1])
        self.assertEqual(same_day.orders[0]['status'],'UNFILLED_DAY_EXPIRED')

    def test_nested_adapter_ignores_daily_open_price_and_admits_whole_tape_before_fills(self):
        points=[{'time':'2024-01-03T'+label+':00+08:00','volume':10000,'price_milli':10000} for label in minute_labels()]
        windows=aggregate_minutes('A',self.calendar.days[1],points)
        broker=IntradayBroker(self.calendar,'100000',participation_bps=500,tape_provider=lambda code,day:windows)
        self.submit(broker,[decision('BUY',2000)])
        market={'security_id':'A','trade_date':'2024-01-03','suspended':False,'open':'999999','limit_up':'11','limit_down':'9'}
        fill=broker.on_market_open([market])[0]
        self.assertEqual(fill['price'],'10');self.assertEqual(fill['execution_at'],'2024-01-03T01:40:00+00:00')
        self.assertEqual(broker.cash,Decimal('79990'))
        bad=copy.deepcopy(windows);bad[20]['volume_lower_shares']=True
        failed=IntradayBroker(self.calendar,'100000',participation_bps=500,tape_provider=lambda code,day:bad)
        self.submit(failed,[decision('BUY',2000)]);before=copy.deepcopy(failed.orders)
        with self.assertRaises(ValueError):failed.on_market_open([market])
        self.assertEqual(failed.orders,before);self.assertEqual(failed.child_orders,[]);self.assertEqual(failed.cash,Decimal('100000'))

    def test_missing_evidence_is_atomic_and_retry_preserves_complete_ledger(self):
        broker=self.broker('30000');self.submit(broker,[decision('BUY',2000)])
        before=copy.deepcopy(broker.__dict__);bad=copy.deepcopy(self.curr);bad.pop('evidence_id')
        with self.assertRaises(ValueError):broker.on_window(bad['start'],bad['end'],{'A':self.prev},{'A':bad},self.refs)
        for field in ('orders','child_orders','fills','cash','positions','_windows','_last_end'):
            self.assertEqual(getattr(broker,field),before[field])
        broker.on_window(self.curr['start'],self.curr['end'],{'A':self.prev},{'A':self.curr},self.refs)
        self.assertEqual(sum(f['quantity'] for f in broker.fills),1000)
        self.assertEqual(sum(lot['quantity'] for lot in broker.positions['A']),1000)
        self.assertEqual(len(broker.child_orders),1)

    def test_legacy_single_open_cannot_bypass_execution_or_backdate_parent(self):
        broker=self.broker();parents=self.submit(broker,[decision('BUY',2000)])
        with self.assertRaises(ValueError):broker.on_open({'security_id':'A','open':'10'})
        self.assertEqual(broker.fills,[])
        broker.expire_day(self.calendar.days[1])
        # An identical retry remains idempotent; a different batch cannot travel back.
        self.assertEqual(self.submit(broker,[decision('BUY',2000)])[0]['order_id'],parents[0]['order_id'])
        with self.assertRaises(ValueError):self.submit(broker,[decision('BUY',1000)])
