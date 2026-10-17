"""Integer-share account and separately timed distribution entitlements.

No price-adjustment factor changes inventory. The flat dividend reserve is
an explicit stress assumption, not a reproduction of FIFO dividend taxation.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from stock_rsi.broker import Broker, money


CENT = Decimal(".01")


@dataclass(frozen=True)
class Distribution:
    event_id: str
    instrument: str
    announced: date
    recorded: date
    ex_date: date
    pay_date: date | None
    listed: date | None
    cash_per_share: Decimal
    capital_per_share: Decimal
    capital_tax_exempt_verified: bool


def plan_integer_targets(equity, positions, weights, prices):
    equity = money(equity)
    weights = {code:money(value) for code,value in weights.items()}
    if (equity <= 0 or not weights or any(value < 0 for value in weights.values())
            or sum(weights.values()) > 1 or any(type(q) is not int or q < 0 for q in positions.values())):
        raise ValueError("finite long-only targets and integer inventory required")
    orders = []
    for code in sorted(set(positions)|set(weights)):
        held, weight = positions.get(code,0), weights.get(code,Decimal(0))
        if weight == 0:
            if held: orders.append(("SELL",code,held))
            continue
        if code not in prices or money(prices[code]) <= 0:
            raise ValueError("known positive raw close required")
        desired = int((equity*weight/money(prices[code])/100).to_integral_value(rounding=ROUND_DOWN))*100
        if desired > held:
            quantity = (desired-held)//100*100
            if quantity: orders.append(("BUY",code,quantity))
        elif held > desired:
            orders.append(("SELL",code,held-desired))
    return tuple(sorted(orders,key=lambda row:(row[0] != "SELL",row[1])))


class RawShareAccount:
    def __init__(self, calendar, initial_cash, distributions=(), *, tax_reserve_rate=".2", broker_factory=Broker):
        self.calendar = calendar
        self.broker = broker_factory(calendar,initial_cash,buy_cost_bps="5",sell_cost_bps="15",min_cost="5")
        self.tax_reserve_rate = money(tax_reserve_rate)
        if not 0 <= self.tax_reserve_rate <= 1:
            raise ValueError("invalid dividend stress reserve")
        self.events = tuple(distributions)
        if len(self.events) != len({event.event_id for event in self.events}):
            raise ValueError("duplicate corporate event identity")
        for event in self.events:
            if (not event.announced < event.recorded < event.ex_date
                    or not event.cash_per_share.is_finite() or not event.capital_per_share.is_finite()
                    or min(event.cash_per_share,event.capital_per_share) < 0
                    or event.cash_per_share > 0 and (event.pay_date is None or event.pay_date < event.ex_date)
                    or event.capital_per_share > 0 and (event.listed is None or event.listed < event.ex_date)):
                raise ValueError("invalid distribution amounts or timing")
        self.entitlements = {}
        self.cash_claims, self.stock_claims, self.corporate_ledger = [], [], []
        self._processed = set()
        self._last_clock = None

    def _check_clock(self, day, phase):
        key = (day,phase)
        if key in self._processed: return False
        if day not in self.calendar.days or self._last_clock is not None and key < self._last_clock:
            raise ValueError("corporate account clock must advance on explicit sessions")
        return True

    def _finish(self, day, phase):
        self._processed.add((day,phase))
        self._last_clock = (day,phase)
        self.check_inventory()

    def check_inventory(self):
        if self.broker.cash < 0 or self.broker.cash != self.broker.cash.quantize(CENT):
            raise ValueError("raw cash must be nonnegative whole cents")
        for lots in self.broker.positions.values():
            if any(type(lot["quantity"]) is not int or lot["quantity"] <= 0 for lot in lots):
                raise ValueError("raw inventory must contain positive integer shares")

    def owned_quantities(self):
        values = {code:sum(lot["quantity"] for lot in lots) for code,lots in self.broker.positions.items()}
        for claim in self.stock_claims:
            if not claim["credited"]:
                code = claim["instrument"]
                values[code] = values.get(code,0)+claim["quantity"]
        return values

    def start_day(self, day):
        if not self._check_clock(day,0): return
        actions = []
        for event in self.events:
            if event.ex_date != day: continue
            if event.event_id not in self.entitlements and event.recorded >= self.calendar.days[0]:
                raise ValueError("record-date ownership was not observed")
            quantity = self.entitlements.get(event.event_id,0)
            exact_bonus = event.capital_per_share*quantity
            if quantity and event.capital_per_share > 0 and not event.capital_tax_exempt_verified:
                raise ValueError("applicable capital transfer tax treatment is unverified")
            if exact_bonus != exact_bonus.to_integral_value():
                raise ValueError("fractional capital entitlement needs registry allocation evidence")
            gross = (event.cash_per_share*quantity).quantize(CENT,rounding=ROUND_HALF_UP)
            reserve = (gross*self.tax_reserve_rate).quantize(CENT,rounding=ROUND_HALF_UP)
            actions.append((event,quantity,int(exact_bonus),gross,reserve))
        # Apply only after validating all corporate actions for this session.
        for claim in self.cash_claims:
            if not claim["paid"] and claim["available_on"] == day:
                self.broker.cash += claim["net"]
                claim["paid"] = True
                self.corporate_ledger.append({"day":day,"kind":"NET_DIVIDEND_CASH_AVAILABLE",
                                              "event_id":claim["event_id"],"cash_delta":claim["net"]})
        for event,quantity,bonus,gross,reserve in actions:
            if gross:
                available = next((at for at in self.calendar.days if at > event.pay_date),None)
                self.cash_claims.append({"event_id":event.event_id,"instrument":event.instrument,
                                         "gross":gross,"reserve":reserve,"net":gross-reserve,
                                         "available_on":available,"paid":False})
            if bonus:
                self.stock_claims.append({"event_id":event.event_id,"instrument":event.instrument,
                                          "quantity":bonus,"listed":event.listed,"recorded":event.recorded,
                                          "credited":False})
            self.corporate_ledger.append({"day":day,"kind":"EX_DATE_ENTITLEMENT",
                                          "event_id":event.event_id,"instrument":event.instrument,
                                          "registered_quantity":quantity,"cash_gross":gross,
                                          "stress_tax_reserve":reserve,"capital_shares":bonus})
        for claim in self.stock_claims:
            if not claim["credited"] and claim["listed"] <= day:
                self.broker.positions.setdefault(claim["instrument"],[]).append({
                    "quantity":claim["quantity"],"bought_on":claim["recorded"],"price":Decimal(0)})
                claim["credited"] = True
                self.corporate_ledger.append({"day":day,"kind":"CAPITAL_SHARES_LISTED",
                                              "event_id":claim["event_id"],"quantity":claim["quantity"]})
        self._finish(day,0)

    def end_day(self, day):
        if not self._check_clock(day,1): return
        additions = []
        for event in self.events:
            if event.recorded != day: continue
            if any(not claim["credited"] and claim["instrument"] == event.instrument for claim in self.stock_claims):
                raise ValueError("overlapping unlisted distribution needs entitlement evidence")
            quantity = sum(lot["quantity"] for lot in self.broker.positions.get(event.instrument,[]))
            additions.append((event,quantity))
        for event,quantity in additions:
            self.entitlements[event.event_id] = quantity
            self.corporate_ledger.append({"day":day,"kind":"RECORD_DATE_OWNERSHIP",
                                          "event_id":event.event_id,"instrument":event.instrument,"quantity":quantity})
        self._finish(day,1)

    def wealth(self, prices):
        self.check_inventory()
        if any(code not in prices or money(prices[code]) <= 0 for code in self.owned_quantities()):
            raise ValueError("every owned share needs a visible raw mark")
        base = self.broker.snapshot(prices)
        cash_receivable = sum((claim["net"] for claim in self.cash_claims if not claim["paid"]),Decimal(0))
        pending_stock = sum((claim["quantity"]*money(prices[claim["instrument"]])
                             for claim in self.stock_claims if not claim["credited"]),Decimal(0))
        market = money(base["market_value"])
        return {"cash":self.broker.cash,"positions":base["positions"],"market_value":market,
                "cash_receivable":cash_receivable,"pending_stock_value":pending_stock,
                "equity":self.broker.cash+market+cash_receivable+pending_stock}
