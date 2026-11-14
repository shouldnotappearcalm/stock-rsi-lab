"""Use only the scheduled date and prior-close account for a calendar order."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from qlib.backtest.decision import Order, TradeDecisionWO
from qlib.strategy.base import BaseStrategy

from stock_rsi.blogger_batch6 import CODE, evaluate
from stock_rsi.blogger_qlib_strategy import plan
from stock_rsi.data import digest
from stock_rsi.prior_close_orders import AsOfPrices


def execution_calendar(snapshot):
    dates = tuple(date.fromisoformat(d) for d in (snapshot.root/'calendars/day_future.txt').read_text().splitlines())
    if dates[:-1] != snapshot.calendar or not dates or dates[-1] <= dates[-2]:
        raise ValueError('quote calendar plus exactly one following date required')
    return dates


class Batch6Strategy(BaseStrategy):
    def __init__(self, *, config, snapshot, **kwargs):
        super().__init__(**kwargs)
        self.config, self.snapshot = config, snapshot
        self.schedule = execution_calendar(snapshot)
        self.intents = []

    def generate_trade_decision(self, execute_result=None):
        start, end = self.trade_calendar.get_step_time()
        day = start.date()
        i = self.snapshot.calendar.index(day)
        if i < 1:
            raise ValueError('prior completed session required')
        previous = self.snapshot.calendar[i-1]
        view = AsOfPrices(self.snapshot, previous)
        observation = evaluate(self.config['id'], self.schedule, day)
        p = self.trade_position
        owned = {c: float(q) for c, q in p.get_stock_amount_dict().items()}
        if any(c != CODE or q <= 0 for c, q in owned.items()):
            raise ValueError('one positive declared inventory only')
        equity = float(p.calculate_value())
        cash = float(p.get_cash(include_settle=True))
        close = {CODE: view.value(CODE, 'close', previous.isoformat())}
        factor = {CODE: view.value(CODE, 'factor', previous.isoformat())}
        orders = plan(observation['leader'], equity, cash, owned, close, factor)
        intent = {
            'execution_session': day.isoformat(),
            'as_of': datetime.combine(previous, time(15, 5), ZoneInfo('Asia/Shanghai')).isoformat(),
            'next_scheduled_session': self.schedule[i+1].isoformat(), 'observation': observation,
            'equity_at_decision': equity, 'cash_at_decision': cash, 'holdings_at_decision': owned,
            'known_closes': close, 'known_factors': factor, 'orders': orders,
            'latest_decision_price_read': view.latest_read.isoformat(),
            'execution_exchange_queried_for_decision': False,
        }
        intent['snapshot_sha256'] = digest(intent)
        self.intents.append(intent)
        return TradeDecisionWO([
            Order(stock_id=o['instrument'], amount=o['normalized_units'],
                  direction=Order.BUY if o['side'] == 'BUY' else Order.SELL,
                  start_time=start, end_time=end)
            for o in orders
        ], self)
