"""Budgeted lot allocator in the unchanged prior-close/monthly Qlib clock.

Daily-open engineering screen; not an intraday/PIT execution claim.
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from qlib.backtest.decision import Order, TradeDecisionWO
from qlib.strategy.base import BaseStrategy

from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.budgeted_lot_orders import plan_budgeted_lot_orders


class BudgetedMonthlyPriorCloseStrategy(BaseStrategy):
    def __init__(self, *, targets, snapshot, **kwargs):
        super().__init__(**kwargs)
        self.targets, self.snapshot = targets, snapshot
        self.intents = []
        self.decision_days = []

    def generate_trade_decision(self, execute_result=None):
        start, end = self.trade_calendar.get_step_time()
        execution_day = start.date()
        self.decision_days.append(execution_day.isoformat())
        index = self.snapshot.calendar.index(execution_day)
        if index < 1:
            raise ValueError("prior session required for order generation")
        previous = self.snapshot.calendar[index - 1]
        first_in_month = previous.strftime("%Y-%m") != execution_day.strftime("%Y-%m")
        payload = self.targets.get(execution_day.isoformat())
        if not first_in_month:
            if payload is not None:
                raise ValueError("monthly target appeared outside first exchange session")
            return TradeDecisionWO([], self)
        if payload is None or date.fromisoformat(payload["as_of"]) != previous:
            raise ValueError("target must be frozen at the prior session close")
        position = self.trade_position
        view = AsOfPrices(self.snapshot, previous)
        equity = float(position.calculate_value())
        holdings = {symbol: float(amount) for symbol, amount in position.get_stock_amount_dict().items()}
        intentions, allocation = plan_budgeted_lot_orders(equity, holdings, payload["weights"], view)
        self.intents.append({
            "execution_session": execution_day.isoformat(),
            "as_of_close_convention": datetime.combine(previous, time(15, 5), ZoneInfo("Asia/Shanghai")).isoformat(),
            "equity_at_decision": equity, "holdings_at_decision": holdings,
            "target_weights": payload["weights"], "orders": intentions,
            "allocation_receipt": allocation,
            "latest_decision_price_read": view.latest_read.isoformat() if view.latest_read else None,
            "execution_exchange_queried_for_decision": False,
        })
        orders = [Order(stock_id=row["instrument"], amount=row["normalized_units"],
                        direction=Order.BUY if row["side"] == "BUY" else Order.SELL,
                        start_time=start, end_time=end) for row in intentions]
        return TradeDecisionWO(orders, self)
