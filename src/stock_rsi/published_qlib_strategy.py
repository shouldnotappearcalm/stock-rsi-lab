"""Daily prior-close decisions for immutable published recipes; optional Qlib."""
from datetime import datetime, time
from zoneinfo import ZoneInfo
import math

from qlib.backtest.decision import Order, TradeDecisionWO
from qlib.strategy.base import BaseStrategy
from stock_rsi.data import digest
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.published_signals import evaluate


def plan_orders(config, observations, equity, cash, holdings, closes, factors):
    """Reserve only prior-close cash; never budget execution-session proceeds."""
    if not all(math.isfinite(x) and x >= 0 for x in (equity, cash)) or equity <= 0 or cash > equity + .01:
        raise ValueError('finite solvent prior-close account required')
    if any(not math.isfinite(q) or q < 0 for q in holdings.values()):
        raise ValueError('long-only prior-close holdings required')
    orders = []
    # 5% cash floor is a harness adaptation, not an upstream parameter.
    remaining = max(0., cash - .05 * equity)
    for symbol in config['symbols']:
        action = observations[symbol]['action']
        held = holdings.get(symbol, 0.)
        if action == 'SELL' and held > 0:
            orders.append({'instrument': symbol, 'side': 'SELL', 'normalized_units': held})
        elif action == 'BUY':
            price, factor = closes[symbol], factors[symbol]
            if any(not math.isfinite(x) or x <= 0 for x in (price, factor)):
                raise ValueError('positive known close and factor required')
            if config['id'] == 'rsi':
                # Original stock order preserved, with explicit reservation
                # instead of pretending that next-open fills already happened.
                budget = min(cash * .3, remaining)
            else:
                budget = min(remaining, max(0., .95 * equity - held * price))
            units = math.floor(budget / price * factor / 100) * 100 / factor
            if units > 0:
                remaining -= units * price
                cash -= units * price
                orders.append({'instrument': symbol, 'side': 'BUY', 'normalized_units': units})
    return sorted(orders, key=lambda x: x['side'] != 'SELL')


class PublishedPriorCloseStrategy(BaseStrategy):
    def __init__(self, *, config, snapshot, **kwargs):
        super().__init__(**kwargs)
        self.config, self.snapshot = config, snapshot
        self.intents = []
        self.decision_days = []

    def generate_trade_decision(self, execute_result=None):
        start, end = self.trade_calendar.get_step_time()
        day = start.date()
        index = self.snapshot.calendar.index(day)
        if index < 1:
            raise ValueError('prior explicit exchange session required')
        previous = self.snapshot.calendar[index - 1]
        view = AsOfPrices(self.snapshot, previous)
        observations, closes, factors, histories = {}, {}, {}, {}
        for symbol in self.config['symbols']:
            # Read backward only from as_of; skip provider's nontrading bars.
            history = []
            for at in reversed(self.snapshot.calendar[:index]):
                volume = view.value(symbol, 'volume', at.isoformat())
                close = view.value(symbol, 'close', at.isoformat())
                if volume is not None and volume > 0 and close is not None and close > 0:
                    history.append((at.isoformat(), close))
                    if len(history) == self.config['history']:
                        break
            history.reverse()
            if len(history) != self.config['history']:
                raise ValueError('incomplete original recipe history: ' + symbol)
            current_volume = view.value(symbol, 'volume', previous.isoformat())
            current_close = view.value(symbol, 'close', previous.isoformat())
            factor = view.value(symbol, 'factor', previous.isoformat())
            if current_volume is None or current_close is None or factor is None:
                raise ValueError('unknown current daily market state: ' + symbol)
            if factor <= 0:
                raise ValueError('invalid source factor')
            observations[symbol] = evaluate(self.config['id'], [p for _, p in history]) if current_volume > 0 else {'action': 'HOLD', 'reason': 'NO_POSITIVE_VOLUME'}
            closes[symbol], factors[symbol], histories[symbol] = current_close, factor, history
        position = self.trade_position
        equity = float(position.calculate_value())
        cash = float(position.get_cash(include_settle=True))
        holdings = {s: float(q) for s, q in position.get_stock_amount_dict().items()}
        intentions = plan_orders(self.config, observations, equity, cash, holdings, closes, factors)
        receipt = {'execution_session': day.isoformat(),
            'as_of': datetime.combine(previous, time(15, 5), ZoneInfo('Asia/Shanghai')).isoformat(),
            'equity_at_decision': equity, 'cash_at_decision': cash, 'holdings_at_decision': holdings,
            'observations': observations, 'histories': histories, 'known_closes': closes, 'known_factors': factors,
            'latest_decision_price_read': view.latest_read.isoformat(), 'orders': intentions,
            'execution_exchange_queried_for_decision': False}
        receipt['snapshot_sha256'] = digest(receipt)
        self.intents.append(receipt)
        self.decision_days.append(day.isoformat())
        orders = [Order(stock_id=x['instrument'], amount=x['normalized_units'],
                        direction=Order.BUY if x['side'] == 'BUY' else Order.SELL,
                        start_time=start, end_time=end) for x in intentions]
        return TradeDecisionWO(orders, self)
