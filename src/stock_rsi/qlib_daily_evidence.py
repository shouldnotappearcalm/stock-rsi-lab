"""Reconcile Qlib daily simulation evidence, without claiming intraday/PIT data.

Qlib amounts/prices use normalized units. Do not present them as raw shares
or exchange executions. A signal date is the previous explicit session;
15:00 is a daily-bar convention, not a measured vendor arrival timestamp.
"""
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("finite evidence amounts required")
    return value


def _same(actual, expected, label):
    if not math.isclose(_number(actual), _number(expected), rel_tol=1e-9, abs_tol=1e-5):
        raise ValueError(label + " does not reconcile")


def reconcile_daily_evidence(report, positions, order_history, calendar, *, initial_cash, signal_days):
    import pandas as pd

    calendar = tuple(calendar)
    if tuple(sorted(set(calendar))) != calendar:
        raise ValueError("explicit sorted unique exchange sessions required")
    indices = {day: number for number, day in enumerate(calendar)}
    if list(positions) != list(report.index) or list(order_history) != list(report.index):
        raise ValueError("positions/order evidence must cover every account session")
    days, orders, holdings = [], [], []
    prior_cash, prior_cost, prior_turnover = float(initial_cash), 0., 0.
    for at, row in report.iterrows():
        day = at.date()
        number = indices[day]
        if number < 1:
            raise ValueError("prior exchange session required")
        signal_date = calendar[number - 1]
        frame = pd.DataFrame(order_history[at].to_series())
        day_orders = []
        for symbol, order in frame.iterrows():
            if signal_date not in signal_days:
                raise ValueError("order has no prior-session signal")
            values = {key: _number(order[key]) for key in (
                "amount", "deal_amount", "trade_price", "trade_value", "trade_cost", "trade_dir")}
            if values["trade_dir"] not in (0., 1.) or values["trade_cost"] < 0:
                raise ValueError("invalid simulated order direction or cost")
            side = "BUY" if values["trade_dir"] == 1 else "SELL"
            signed_value = values["trade_value"]
            if ((side == "BUY" and signed_value < 0) or (side == "SELL" and signed_value > 0)):
                raise ValueError("signed trade value disagrees with direction")
            day_orders.append({"session": day.isoformat(), "signal_date": signal_date.isoformat(),
                               "instrument": str(symbol), "side": side,
                               "requested_normalized_units": values["amount"],
                               "filled_normalized_units": values["deal_amount"],
                               "normalized_price": values["trade_price"],
                               "signed_trade_value": signed_value, "cost": values["trade_cost"]})
        cost = sum(item["cost"] for item in day_orders)
        turnover = sum(abs(item["signed_trade_value"]) for item in day_orders)
        position = positions[at]
        cash = _number(position.get_cash(include_settle=True))
        stock_value = 0.
        for symbol in sorted(position.get_stock_list()):
            units = _number(position.get_stock_amount(symbol))
            price = _number(position.get_stock_price(symbol))
            value = units * price
            stock_value += value
            holdings.append({"session": day.isoformat(), "instrument": str(symbol),
                             "normalized_units": units, "normalized_price": price,
                             "value": value, "weight": value / _number(row["account"])})
        _same(stock_value, row["value"], "holdings value")
        _same(cash + stock_value, row["account"], "account value")
        _same(cash, prior_cash - sum(item["signed_trade_value"] for item in day_orders) - cost, "cash flow")
        _same(cost, row["total_cost"] - prior_cost, "daily costs")
        _same(turnover, row["total_turnover"] - prior_turnover, "daily turnover")
        orders.extend(day_orders)
        days.append({"session": day.isoformat(), "signal_date": signal_date.isoformat(),
                     "signal_bar_close_convention": datetime.combine(signal_date, time(15), ZoneInfo("Asia/Shanghai")).isoformat(),
                     "signal_present": signal_date in signal_days, "cash": cash,
                     "stock_value": stock_value, "account_value": _number(row["account"]),
                     "cost": cost, "turnover": turnover, "orders": len(day_orders)})
        prior_cash, prior_cost, prior_turnover = cash, _number(row["total_cost"]), _number(row["total_turnover"])
    return {"days": days, "orders": orders, "holdings": holdings,
            "total_cost": prior_cost, "total_turnover": prior_turnover}
