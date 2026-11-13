"""Observe completed bars and prior holdings; send bounded next-open orders."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from qlib.backtest.decision import Order, TradeDecisionWO
from qlib.strategy.base import BaseStrategy

from stock_rsi.blogger_batch5 import CODE, evaluate
from stock_rsi.blogger_qlib_strategy import plan
from stock_rsi.data import digest
from stock_rsi.prior_close_orders import AsOfPrices


class Batch5Strategy(BaseStrategy):
    def __init__(self, *, config, snapshot, **kwargs):
        super().__init__(**kwargs)
        self.config, self.snapshot = config, snapshot
        self.intents = []
        self.state = False

    def generate_trade_decision(self, execute_result=None):
        start, end = self.trade_calendar.get_step_time()
        day = start.date()
        i = self.snapshot.calendar.index(day)
        if i < 200:
            raise ValueError('200 actual completed sessions required')
        dates = [d.isoformat() for d in self.snapshot.calendar[i-200:i]]
        previous = self.snapshot.calendar[i-1]
        view = AsOfPrices(self.snapshot, previous)
        closes = [view.value(CODE, 'close', d) for d in dates]
        opens = [view.value(CODE, 'open', d) for d in dates[-3:]]
        p = self.trade_position
        owned = {c: float(q) for c, q in p.get_stock_amount_dict().items()}
        if any(c != CODE or q <= 0 for c, q in owned.items()):
            raise ValueError('one positive declared inventory only')
        observation = evaluate(self.config['id'], closes, opens, bool(owned), self.state)
        equity = float(p.calculate_value())
        cash = float(p.get_cash(include_settle=True))
        close = {CODE: closes[-1]}
        factor = {CODE: view.value(CODE, 'factor', dates[-1])}
        orders = plan(observation['leader'], equity, cash, owned, close, factor)
        intent = {
            'execution_session': day.isoformat(),
            'as_of': datetime.combine(previous, time(15, 5), ZoneInfo('Asia/Shanghai')).isoformat(),
            'history': list(zip(dates, closes)), 'completed_opens': list(zip(dates[-3:], opens)),
            'state_before': self.state, 'observation': observation,
            'equity_at_decision': equity, 'cash_at_decision': cash, 'holdings_at_decision': owned,
            'known_closes': close, 'known_factors': factor, 'orders': orders,
            'latest_decision_price_read': view.latest_read.isoformat(),
            'execution_exchange_queried_for_decision': False,
        }
        self.state = observation['state_after']
        intent['snapshot_sha256'] = digest(intent)
        self.intents.append(intent)
        return TradeDecisionWO([
            Order(stock_id=o['instrument'], amount=o['normalized_units'],
                  direction=Order.BUY if o['side'] == 'BUY' else Order.SELL,
                  start_time=start, end_time=end)
            for o in orders
        ], self)
