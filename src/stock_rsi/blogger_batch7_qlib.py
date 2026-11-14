"""Monthly frozen share targets, sell first and observe proceeds before buying."""
from datetime import datetime, time
import math
from zoneinfo import ZoneInfo

from qlib.backtest.decision import Order, TradeDecisionWO
from qlib.strategy.base import BaseStrategy

from stock_rsi.blogger_batch7 import LOOKBACK, SYMBOLS, allocation, lot, orders_for
from stock_rsi.data import digest
from stock_rsi.prior_close_orders import AsOfPrices


class Batch7Strategy(BaseStrategy):
    def __init__(self, *, config, snapshot, extra, **kwargs):
        super().__init__(**kwargs)
        self.config, self.snapshot, self.extra = config, snapshot, extra
        self.intents = []
        self.formed_at = None
        self.weights, self.target = {}, {}
        self.active = False

    def generate_trade_decision(self, execute_result=None):
        start, end = self.trade_calendar.get_step_time()
        day = start.date()
        i = self.snapshot.calendar.index(day)
        if i < 1:
            raise ValueError('prior actual session required')
        prev = self.snapshot.calendar[i-1]
        datestr = prev.isoformat()
        view = AsOfPrices(self.snapshot, prev)
        p = self.trade_position
        equity, cash = float(p.calculate_value()), float(p.get_cash(include_settle=True))
        owned = {c:float(q) for c,q in p.get_stock_amount_dict().items()}
        if set(owned)-set(SYMBOLS) or any(not math.isfinite(q) or q<=0 for q in owned.values()):
            raise ValueError('actual declared long inventory only')
        prices = {c:view.value(c,'close',datestr) for c in SYMBOLS}
        factors = {c:view.value(c,'factor',datestr) for c in SYMBOLS}
        if any(x is None or not math.isfinite(x) or x <= 0 for x in [equity,*prices.values(),*factors.values()]):
            raise ValueError('positive known account and marks required')
        formation = (prev.year,prev.month)!=(day.year,day.month)
        histories, volatility = {}, {}
        if formation:
            if self.config['id']=='invvol60':
                dates = [d.isoformat() for d in self.snapshot.calendar[max(0,i-LOOKBACK-1):i]]
                histories = {c:[[d,view.value(c,'close',d)] for d in dates] for c in SYMBOLS}
            self.weights,volatility = allocation(self.config['id'],{c:[p for _,p in h] for c,h in histories.items()})
            self.target = {c:lot(equity*self.weights[c]/prices[c],factors[c]) for c in SYMBOLS}
            self.formed_at = datestr
            self.active = True
        if self.formed_at is None:
            raise ValueError('initial month boundary required')
        active_before = self.active
        orders = orders_for(self.target,owned,prices,factors,cash,equity,self.extra) if self.active else []
        self.active = bool(orders)
        intent = {
            'execution_session':day.isoformat(), 'as_of':datetime.combine(prev,time(15,5),ZoneInfo('Asia/Shanghai')).isoformat(),
            'formation':formation, 'formed_at':self.formed_at, 'histories':histories, 'volatility':volatility,
            'weights':self.weights, 'target_normalized_units':self.target, 'active_before':active_before,
            'active_after':self.active, 'equity_at_decision':equity, 'cash_at_decision':cash,
            'holdings_at_decision':owned, 'known_closes':prices, 'known_factors':factors, 'orders':orders,
            'latest_decision_price_read':view.latest_read.isoformat(), 'execution_exchange_queried_for_decision':False,
        }
        intent['snapshot_sha256'] = digest(intent)
        self.intents.append(intent)
        return TradeDecisionWO([
            Order(stock_id=o['instrument'],amount=o['normalized_units'],
                  direction=Order.BUY if o['side']=='BUY' else Order.SELL,start_time=start,end_time=end)
            for o in orders],self)
