"""Explicit period formation and pending execution, separate from skill files."""
from datetime import datetime,time
from zoneinfo import ZoneInfo
from qlib.strategy.base import BaseStrategy
from qlib.backtest.decision import Order,TradeDecisionWO
from stock_rsi.blogger_batch3 import STOCK,BOND,month_ends,monthly_regime,annual_targets,annual_orders
from stock_rsi.blogger_qlib_strategy import plan
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.data import digest

class Batch3Strategy(BaseStrategy):
    def __init__(self,*,config,snapshot,extra,**kwargs):
        super().__init__(**kwargs);self.config,self.snapshot,self.extra=config,snapshot,extra;self.intents=[];self.regime=None;self.signal_rows=[];self.signal_detail={};self.targets={};self.active=False;self.formed_at=None

    def generate_trade_decision(self,execute_result=None):
        start,end=self.trade_calendar.get_step_time();day=start.date();i=self.snapshot.calendar.index(day)
        if i<1:raise ValueError('actual prior session required')
        previous=self.snapshot.calendar[i-1];view=AsOfPrices(self.snapshot,previous);p=self.trade_position
        equity=float(p.calculate_value());cash=float(p.get_cash(include_settle=True));owned={c:float(q) for c,q in p.get_stock_amount_dict().items()}
        if set(owned)-set(self.config['symbols']) or any(q<=0 for q in owned.values()):raise ValueError('declared actual inventory only')
        closes={c:view.value(c,'close',previous.isoformat()) for c in self.config['symbols']};factors={c:view.value(c,'factor',previous.isoformat()) for c in self.config['symbols']}
        if any(v is None or v<=0 for v in [*closes.values(),*factors.values()]):raise ValueError('complete current known marks required')
        regime_before=self.regime;active_before=self.active
        formation=(previous.strftime('%Y-%m')!=day.strftime('%Y-%m')) if self.config['id']=='faber10' else previous.year!=day.year
        if formation:
            self.formed_at=previous.isoformat()
            if self.config['id']=='faber10':
                history=[]
                for d in self.snapshot.calendar[:i]:
                    price=view.value(STOCK,'close',d.isoformat())
                    if price is None or price<=0:raise ValueError('complete month-end sampling source required')
                    history.append([d.isoformat(),price])
                self.signal_rows=month_ends(history);self.regime,self.signal_detail=monthly_regime(self.signal_rows,self.regime)
            else:self.targets=annual_targets(equity,closes,factors);self.active=True
        if self.formed_at is None:raise ValueError('initial actual month/year boundary required')
        if self.config['id']=='faber10':orders=plan(STOCK if self.regime else None,equity,cash,owned,closes,factors)
        else:
            orders=annual_orders(self.targets,equity,cash,owned,closes,factors,self.extra) if self.active else []
            if self.active and not orders:self.active=False
        receipt={'execution_session':day.isoformat(),'as_of':datetime.combine(previous,time(15,5),ZoneInfo('Asia/Shanghai')).isoformat(),
            'formation':formation,'formed_at':self.formed_at,'signal_rows':self.signal_rows,'signal_detail':self.signal_detail,
            'regime_before':regime_before,'regime_after':self.regime,'target_normalized_units':self.targets,
            'execution_active_before':active_before,'execution_active_after':self.active,'equity_at_decision':equity,'cash_at_decision':cash,
            'holdings_at_decision':owned,'known_closes':closes,'known_factors':factors,'orders':orders,
            'latest_decision_price_read':view.latest_read.isoformat(),'execution_exchange_queried_for_decision':False}
        receipt['snapshot_sha256']=digest(receipt);self.intents.append(receipt)
        return TradeDecisionWO([Order(stock_id=o['instrument'],amount=o['normalized_units'],direction=Order.BUY if o['side']=='BUY' else Order.SELL,start_time=start,end_time=end) for o in orders],self)
