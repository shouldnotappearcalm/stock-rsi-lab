"""Actual filled-holding age stays outside the editable blogger skill."""
from datetime import datetime,time
from zoneinfo import ZoneInfo
from qlib.strategy.base import BaseStrategy
from qlib.backtest.decision import Order,TradeDecisionWO
from stock_rsi.blogger_batch2 import evaluate,CODE
from stock_rsi.blogger_qlib_strategy import plan
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.data import digest

class Batch2PriorCloseStrategy(BaseStrategy):
    def __init__(self,*,config,snapshot,**kwargs):
        super().__init__(**kwargs);self.config,self.snapshot=config,snapshot;self.intents=[];self.entry_index=None;self.exit_latched=False

    def generate_trade_decision(self,execute_result=None):
        start,end=self.trade_calendar.get_step_time();day=start.date();i=self.snapshot.calendar.index(day)
        if i<1:raise ValueError('actual prior session required')
        previous=self.snapshot.calendar[i-1];view=AsOfPrices(self.snapshot,previous)
        dates=self.snapshot.calendar[:i] if self.config['id']=='rayner10' else self.snapshot.calendar[i-20:i]
        if self.config['id']=='rayner10' and dates[0].isoformat()!='2022-12-01':raise ValueError('fixed RSI seed origin required')
        history=[]
        for d in dates:
            value=view.value(CODE,'close',d.isoformat());volume=view.value(CODE,'volume',d.isoformat())
            if value is None or value<=0 or volume is None or volume<=0:raise ValueError('complete source history; no gap skipping')
            history.append([d.isoformat(),value])
        p=self.trade_position;owned={c:float(q) for c,q in p.get_stock_amount_dict().items()}
        if any(c!=CODE or q<=0 for c,q in owned.items()):raise ValueError('one declared positive inventory only')
        if owned:
            if self.entry_index is None:self.entry_index=i-1
        else:self.entry_index=None;self.exit_latched=False
        age=i-self.entry_index if self.entry_index is not None else 0;before=self.exit_latched
        observation=evaluate(self.config['id'],[v for _,v in history],bool(owned),age,before)
        if self.config['id']=='rayner10' and owned and observation['action']=='SELL':self.exit_latched=True
        equity=float(p.calculate_value());cash=float(p.get_cash(include_settle=True));closes={CODE:view.value(CODE,'close',previous.isoformat())};factors={CODE:view.value(CODE,'factor',previous.isoformat())}
        orders=plan(observation['leader'],equity,cash,owned,closes,factors)
        intent={'execution_session':day.isoformat(),'as_of':datetime.combine(previous,time(15,5),ZoneInfo('Asia/Shanghai')).isoformat(),
                'history':history,'observation':observation,'equity_at_decision':equity,'cash_at_decision':cash,'holdings_at_decision':owned,
                'known_closes':closes,'known_factors':factors,'holding_sessions':age,'entry_session':self.snapshot.calendar[self.entry_index].isoformat() if self.entry_index is not None else None,
                'exit_latched_before':before,'exit_latched_after':self.exit_latched,'orders':orders,'latest_decision_price_read':view.latest_read.isoformat(),
                'execution_exchange_queried_for_decision':False}
        intent['snapshot_sha256']=digest(intent);self.intents.append(intent)
        return TradeDecisionWO([Order(stock_id=o['instrument'],amount=o['normalized_units'],direction=Order.BUY if o['side']=='BUY' else Order.SELL,start_time=start,end_time=end) for o in orders],self)
