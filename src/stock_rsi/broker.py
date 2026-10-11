from datetime import date
from decimal import Decimal, ROUND_DOWN

from .calendar import SHANGHAI, TradingCalendar
from .data import digest
from .models import Decision
from .time import iso, parse_time


def money(value):
    try:
        if isinstance(value, bool):
            raise ValueError("boolean is not money")
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("finite monetary value required")
        return result
    except Exception as exc:
        raise ValueError("invalid monetary value") from exc


class Broker:
    def __init__(self, calendar: TradingCalendar, initial_cash="100000", cost_bps="20"):
        self.calendar = calendar
        self.initial_cash = self.cash = money(initial_cash)
        self.rate = money(cost_bps) / 10000
        if self.cash <= 0 or not 0 <= self.rate <= 1:
            raise ValueError("invalid account configuration")
        self.positions = {}
        self.orders = []
        self.fills = []
        self._processed = set()

    def submit(self, decision: Decision, at):
        at = parse_time(at)
        if decision.action in ("HOLD", "ABSTAIN"):
            return None
        if decision.action == "BUY" and decision.quantity % 100:
            raise ValueError("A-share buys require 100-share lots")
        order_id = digest({"decision_id": decision.decision_id, "at": iso(at)})
        if any(order["order_id"] == order_id for order in self.orders):
            return next(order for order in self.orders if order["order_id"] == order_id).copy()
        try:
            eligible = self.calendar.next_day_open(at)
            status = "PENDING"
        except ValueError:
            eligible, status = None, "UNFILLED_CALENDAR_END"
        order = {"order_id": order_id, "decision_id": decision.decision_id,
                 "security_id": decision.security_id, "action": decision.action,
                 "quantity": decision.quantity, "submitted_at": iso(at),
                 "eligible_at": iso(eligible) if eligible else None, "status": status}
        if status == "PENDING":
            for previous in self.orders:
                if previous["status"] == "PENDING" and previous["security_id"] == decision.security_id:
                    previous["status"] = "SUPERSEDED_BY_NEW_INTENT"
        self.orders.append(order)
        return order.copy()

    def on_open(self, bar):
        security = bar["security_id"]
        day = date.fromisoformat(bar["trade_date"])
        at = self.calendar.at(day, "09:30:00")
        if day not in self.calendar.days:
            raise ValueError("execution day absent from exchange calendar")
        key = (security, day)
        if key in self._processed:
            return []
        if type(bar.get("suspended")) is not bool:
            raise ValueError("explicit suspension status required")
        price = money(bar.get("open"))
        upper, lower = money(bar.get("limit_up")), money(bar.get("limit_down"))
        if price <= 0 or not lower < upper or lower <= 0:
            raise ValueError("invalid execution price/limits")
        self._processed.add(key)
        new_fills = []
        for order in self.orders:
            if order["status"] != "PENDING" or order["security_id"] != security:
                continue
            eligible = parse_time(order["eligible_at"])
            if eligible > at:
                continue
            if eligible < at:
                order["status"] = "EXPIRED"
                continue
            action = order["action"]
            blocked = bar["suspended"] or (action == "BUY" and price >= upper) or (action == "SELL" and price <= lower)
            if blocked:
                order["status"] = "UNFILLED_MARKET_CONSTRAINT"
                continue
            quantity = order["quantity"]
            lots = self.positions.setdefault(security, [])
            if action == "BUY":
                affordable = int((self.cash / (price * (1 + self.rate))).to_integral_value(rounding=ROUND_DOWN)) // 100 * 100
                quantity = min(quantity, affordable)
            else:
                quantity = min(quantity, sum(lot["quantity"] for lot in lots if lot["bought_on"] < day))
            if quantity <= 0:
                order["status"] = "UNFILLED_CASH_OR_T1"
                if not lots:
                    self.positions.pop(security, None)
                continue
            gross = price * quantity
            cost = (gross * self.rate).quantize(Decimal("0.01"))
            if action == "BUY":
                self.cash -= gross + cost
                lots.append({"quantity": quantity, "bought_on": day, "price": price})
            else:
                self.cash += gross - cost
                remaining = quantity
                for lot in lots:
                    if lot["bought_on"] >= day:
                        continue
                    removed = min(remaining, lot["quantity"])
                    lot["quantity"] -= removed
                    remaining -= removed
                self.positions[security] = [lot for lot in lots if lot["quantity"]]
                if not self.positions[security]:
                    self.positions.pop(security)
            assert self.cash >= 0
            order["status"] = "FILLED" if quantity == order["quantity"] else "PARTIAL_DAY_EXPIRED"
            fill = {"order_id": order["order_id"], "execution_at": iso(at), "security_id": security,
                    "action": action, "quantity": quantity, "price": str(price), "cost": str(cost), "cash_after": str(self.cash)}
            self.fills.append(fill)
            new_fills.append(fill.copy())
        return new_fills

    def snapshot(self, prices=None):
        prices = prices or {}
        holdings, value = {}, Decimal("0")
        for security, lots in self.positions.items():
            quantity = sum(lot["quantity"] for lot in lots)
            basis = sum(lot["price"] * lot["quantity"] for lot in lots) / quantity
            price = money(prices[security]) if security in prices else basis
            if price <= 0:
                raise ValueError("invalid mark price")
            value += quantity * price
            holdings[security] = {"quantity": quantity, "average_price": str(basis),
                                  "mark_price": str(price), "mark_source": "VISIBLE_PRICE" if security in prices else "COST_UNMARKED"}
        return {"cash": str(self.cash), "positions": holdings, "market_value": str(value),
                "equity": str(self.cash + value)}
