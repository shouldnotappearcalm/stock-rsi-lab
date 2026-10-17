"""Distinguish independently confirmed suspensions from unexplained data gaps."""
import math
from datetime import date

from stock_rsi.prior_close_orders import AsOfPrices


def verify_suspension_mark(snapshot, symbol, day, mark, states):
    result = {"instrument":symbol, "session":day, "marked_normalized_price":mark, "verified":False}
    state = states.get(day)
    if state is None or state.get("tradestatus") != "0":
        return result | {"reason":"NO_INDEPENDENT_SUSPENDED_STATE"}
    as_of = date.fromisoformat(day)
    view = AsOfPrices(snapshot, as_of)
    for prior in reversed([at for at in snapshot.calendar if at < as_of]):
        value = view.value(symbol,"close",prior.isoformat())
        if value is None or not math.isfinite(value) or value <= 0:
            continue
        factor = view.value(symbol,"factor",prior.isoformat())
        anchor = states.get(prior.isoformat(), {})
        try:
            source_price = float(anchor.get("close", ""))
        except (ValueError, TypeError):
            source_price = float("nan")
        if (factor is None or factor <= 0 or not math.isfinite(source_price)
                or not math.isclose(value/factor, source_price, abs_tol=.005, rel_tol=1e-6)):
            return result | {"reason":"CROSS_SOURCE_LAST_VISIBLE_PRICE_NOT_VERIFIED"}
        if not math.isfinite(mark) or not math.isclose(mark,value,abs_tol=1e-8,rel_tol=1e-8):
            return result | {"reason":"MARK_DIFFERS_FROM_LAST_VISIBLE_CLOSE"}
        return result | {"verified":True, "classification":"INDEPENDENT_HALT_LAST_VISIBLE_MARK",
                         "last_visible_close_date":prior.isoformat(), "last_visible_normalized_close":value,
                         "source_tradestatus":"0", "actual_quote_on_suspended_day_created":False}
    return result | {"reason":"NO_PRIOR_VISIBLE_CLOSE"}
