"""Prior-close order sizing; the execution-day exchange is not an input."""
import math
from datetime import date


class AsOfPrices:
    def __init__(self, snapshot, as_of):
        self.snapshot, self.as_of = snapshot, as_of
        self.latest_read = None

    def value(self, symbol, field, day):
        target = date.fromisoformat(day)
        if target > self.as_of:
            raise ValueError("decision price view attempted a future read")
        self.latest_read = max(target, self.latest_read or target)
        return self.snapshot.value(symbol, field, day)


def plan_prior_close_orders(equity, positions, weights, view):
    if (not math.isfinite(equity) or equity <= 0
            or any(not math.isfinite(value) or value < 0 for value in positions.values())):
        raise ValueError("finite positive account equity and nonnegative holdings required")
    if (not weights or any(not math.isfinite(value) or value < 0 for value in weights.values())
            or math.fsum(weights.values()) > 1 + 1e-10):
        raise ValueError("finite long-only weights totaling at most one required")
    orders = []
    for symbol in sorted(set(positions) | set(weights)):
        held = positions.get(symbol, 0.)
        if held > 0 and weights.get(symbol, 0.) == 0:
            orders.append({"instrument":symbol, "side":"SELL", "normalized_units":held,
                           "known_normalized_close":None, "known_factor":None,
                           "as_of":view.as_of.isoformat(), "quantity_basis":"KNOWN_INVENTORY_FULL_EXIT"})
            continue
        price = view.value(symbol, "close", view.as_of.isoformat())
        factor = view.value(symbol, "factor", view.as_of.isoformat())
        if any(value is None or not math.isfinite(value) or value <= 0 for value in (price, factor)):
            raise ValueError("positive visible close and factor required for order sizing")
        target_shares = math.floor(equity * weights.get(symbol, 0.) / price * factor / 100 + 1e-10) * 100
        desired = target_shares / factor
        difference = desired - held
        if difference > 1e-8 * max(1., held, desired):
            units = math.floor(difference * factor / 100 + 1e-10) * 100 / factor
            side = "BUY"
        elif difference < -1e-8 * max(1., held, desired):
            units, side = held - desired, "SELL"
        else:
            continue
        if units > 0:
            orders.append({"instrument": symbol, "side": side, "normalized_units": units,
                           "known_normalized_close": price, "known_factor": factor,
                           "as_of": view.as_of.isoformat(), "quantity_basis":"PRIOR_CLOSE_TARGET"})
    return tuple(sorted(orders, key=lambda row: (row["side"] != "SELL", row["instrument"])))
