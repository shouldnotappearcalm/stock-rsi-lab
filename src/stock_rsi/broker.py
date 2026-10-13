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
        if self.cash <= 0 or self.cash != self.cash.quantize(Decimal("0.01")) or not 0 <= self.rate <= 1:
            raise ValueError("invalid account configuration")
        self.positions = {}
        self.orders = []
        self.fills = []
        self._processed = set()

    def submit(self, decision: Decision, at, expires_at=None):
        at = parse_time(at)
        if decision.action in ("HOLD", "ABSTAIN"):
            return None
        if decision.action == "BUY" and decision.quantity % 100:
            raise ValueError("A-share buys require 100-share lots")
        expiry = parse_time(expires_at) if expires_at is not None else None
        if expiry is not None and expiry <= at:
            raise ValueError("order expiry must follow submission")
        order_id = digest({"decision_id": decision.decision_id, "at": iso(at),
                           "expires_at": iso(expiry) if expiry else None})
        if any(order["order_id"] == order_id for order in self.orders):
            return next(order for order in self.orders if order["order_id"] == order_id).copy()
        try:
            eligible = self.calendar.next_day_open(at)
            status = "EXPIRED_BEFORE_EXECUTION" if expiry is not None and eligible > expiry else "PENDING"
        except ValueError:
            eligible, status = None, "UNFILLED_CALENDAR_END"
        order = {"order_id": order_id, "decision_id": decision.decision_id,
                 "security_id": decision.security_id, "action": decision.action,
                 "quantity": decision.quantity, "submitted_at": iso(at),
                 "eligible_at": iso(eligible) if eligible else None,
                 "expires_at": iso(expiry) if expiry else None, "status": status}
        if status == "PENDING":
            for previous in self.orders:
                if previous["status"] == "PENDING" and previous["security_id"] == decision.security_id:
                    previous["status"] = "SUPERSEDED_BY_NEW_INTENT"
        self.orders.append(order)
        return order.copy()

    def replace_pending_intent(self, decisions, at, expires_at):
        if not isinstance(decisions, (tuple, list)) or not all(isinstance(row, Decision) for row in decisions):
            raise ValueError("portfolio intent requires Decision objects")
        securities = [row.security_id for row in decisions]
        if len(securities) != len(set(securities)):
            raise ValueError("portfolio intent has duplicate securities")
        at = parse_time(at)
        expiry = parse_time(expires_at)
        if expiry <= at:
            raise ValueError("portfolio intent expiry must follow submission")
        for order in self.orders:
            if order["status"] == "PENDING":
                order["status"] = "CANCELLED_BY_PORTFOLIO_REPLACEMENT"
        return [self.submit(row, at, expiry) for row in decisions]

    def _validate_bar(self, bar):
        if not isinstance(bar, dict):
            raise ValueError("execution bar must be an object")
        security = bar["security_id"]
        if not isinstance(security, str) or not security:
            raise ValueError("execution security required")
        day = date.fromisoformat(bar["trade_date"])
        at = self.calendar.at(day, "09:30:00")
        if day not in self.calendar.days:
            raise ValueError("execution day absent from exchange calendar")
        if type(bar.get("suspended")) is not bool:
            raise ValueError("explicit suspension status required")
        price = money(bar.get("open"))
        upper, lower = money(bar.get("limit_up")), money(bar.get("limit_down"))
        if price <= 0 or not lower < upper or lower <= 0:
            raise ValueError("invalid execution price/limits")
        return {"security": security, "day": day, "at": at, "bar": bar,
                "price": price, "upper": upper, "lower": lower}

    def _process_security(self, validated, action):
        security, day, at = validated["security"], validated["day"], validated["at"]
        bar, price = validated["bar"], validated["price"]
        upper, lower = validated["upper"], validated["lower"]
        new_fills = []
        for order in self.orders:
            if (order["status"] != "PENDING" or order["security_id"] != security or
                    order["action"] != action):
                continue
            eligible = parse_time(order["eligible_at"])
            if order.get("expires_at") and at > parse_time(order["expires_at"]):
                order["status"] = "EXPIRED"
                continue
            if eligible > at:
                continue
            if eligible < at:
                order["status"] = "EXPIRED"
                continue
            blocked = bar["suspended"] or (action == "BUY" and price >= upper) or (action == "SELL" and price <= lower)
            if blocked:
                order["status"] = "UNFILLED_MARKET_CONSTRAINT"
                continue
            quantity = order["quantity"]
            lots = self.positions.setdefault(security, [])
            if action == "BUY":
                affordable = int((self.cash / (price * (1 + self.rate))).to_integral_value(rounding=ROUND_DOWN)) // 100 * 100
                quantity = min(quantity, affordable)
                while quantity > 0 and price * quantity + (price * quantity * self.rate).quantize(Decimal("0.01")) > self.cash:
                    quantity -= 100
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

    def _open_batch(self, bars, require_complete):
        if not isinstance(bars, list) or not bars:
            raise ValueError("nonempty execution bar batch required")
        validated = [self._validate_bar(bar) for bar in bars]
        securities = [row["security"] for row in validated]
        days = {row["day"] for row in validated}
        if len(securities) != len(set(securities)):
            raise ValueError("duplicate security in execution batch")
        if len(days) != 1:
            raise ValueError("execution batch must share one session date")
        day = validated[0]["day"]
        at = validated[0]["at"]
        rows = {row["security"]: row for row in validated}
        if require_complete:
            for order in self.orders:
                if order["status"] != "PENDING":
                    continue
                eligible = parse_time(order["eligible_at"])
                if order.get("expires_at") and at > parse_time(order["expires_at"]):
                    order["status"] = "EXPIRED"
                elif eligible < at:
                    order["status"] = "EXPIRED"
                elif eligible == at and order["security_id"] not in rows:
                    order["status"] = "INVALID_MISSING_DATA"
        fills = []
        for action in ("SELL", "BUY"):
            for security in sorted(rows):
                if (security, day) not in self._processed:
                    fills.extend(self._process_security(rows[security], action))
        self._processed.update((security, day) for security in rows)
        return fills

    def on_market_open(self, bars):
        return self._open_batch(bars, require_complete=True)

    def on_open(self, bar):
        return self._open_batch([bar], require_complete=False)

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
