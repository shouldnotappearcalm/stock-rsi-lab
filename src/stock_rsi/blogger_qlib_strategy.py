"""Daily blogger-rule adapter: source signals and prior-close cash only."""
from datetime import datetime,time
from zoneinfo import ZoneInfo
import math
from qlib.strategy.base import BaseStrategy
from qlib.backtest.decision import Order,TradeDecisionWO
from stock_rsi.blogger_rotation import evaluate
from stock_rsi.data import digest
from stock_rsi.prior_close_orders import AsOfPrices


def plan(leader,equity,cash,owned,closes,factors):
    if not all(math.isfinite(x) and x>=0 for x in (equity,cash)) or equity<=0:raise ValueError('finite solvent prior account required')
    held={c:q for c,q in owned.items() if q>0}
    if any(not math.isfinite(q) or q<0 for q in owned.values()):raise ValueError('long-only actual inventory required')
    exits=[{'instrument':c,'side':'SELL','normalized_units':q} for c,q in sorted(held.items()) if c!=leader]
    if exits:return exits  # No yet-unfilled sale can fund a new buy.
    if leader is None or leader in held:return []
    price,factor=closes[leader],factors[leader]
    if not all(math.isfinite(x) and x>0 for x in (price,factor)):raise ValueError('positive known mark and factor required')
    budget=max(0.,min(.95*equity,cash-.05*equity))
    units=math.floor(budget/price*factor/100)*100/factor
    return [{'instrument':leader,'side':'BUY','normalized_units':units}] if units>0 else []


class BloggerPriorCloseStrategy(BaseStrategy):
    def __init__(self,*,config,snapshot,**kwargs):
        super().__init__(**kwargs);self.config,self.snapshot=config,snapshot;self.intents=[];self.decision_days=[]

    def generate_trade_decision(self,execute_result=None):
        start,end=self.trade_calendar.get_step_time();day=start.date();i=self.snapshot.calendar.index(day)
        if i<1:raise ValueError('actual prior session required')
        previous=self.snapshot.calendar[i-1];view=AsOfPrices(self.snapshot,previous);histories={}
        for c in self.config['signal_symbols']:
            history=[]
            for at in reversed(self.snapshot.calendar[:i]):
                close=view.value(c,'close',at.isoformat());volume=view.value(c,'volume',at.isoformat())
                if close is not None and close>0 and volume is not None and volume>0:
                    history.append((at.isoformat(),close))
                    if len(history)==self.config['history']:break
            history.reverse();histories[c]=history
        position=self.trade_position;equity=float(position.calculate_value());cash=float(position.get_cash(include_settle=True))
        owned={c:float(q) for c,q in position.get_stock_amount_dict().items()};closes={};factors={}
        for c in self.config['symbols']:
            closes[c]=view.value(c,'close',previous.isoformat());factors[c]=view.value(c,'factor',previous.isoformat())
            if any(x is None or x<=0 for x in (closes[c],factors[c])):raise ValueError('complete current fund close/factor required')
        observation=evaluate(self.config,{c:[p for _,p in h] for c,h in histories.items()},owned)
        orders=plan(observation['leader'],equity,cash,owned,closes,factors)
        receipt={'execution_session':day.isoformat(),'as_of':datetime.combine(previous,time(15,5),ZoneInfo('Asia/Shanghai')).isoformat(),
                 'histories':histories,'observation':observation,'equity_at_decision':equity,'cash_at_decision':cash,
                 'holdings_at_decision':owned,'known_closes':closes,'known_factors':factors,'orders':orders,
                 'latest_decision_price_read':view.latest_read.isoformat(),'execution_exchange_queried_for_decision':False}
        receipt['snapshot_sha256']=digest(receipt);self.intents.append(receipt);self.decision_days.append(day.isoformat())
        native=[Order(stock_id=o['instrument'],amount=o['normalized_units'],direction=Order.BUY if o['side']=='BUY' else Order.SELL,start_time=start,end_time=end) for o in orders]
        return TradeDecisionWO(native,self)
