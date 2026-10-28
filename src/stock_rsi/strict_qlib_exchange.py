"""Optional Qlib exchange that never rounds a requested quantity upward."""
import math
from qlib.backtest.exchange import Exchange


def strict_floor_units(amount, factor, unit):
    if any(not math.isfinite(x) or x <= 0 for x in (factor, unit)) or not math.isfinite(amount) or amount < 0:
        raise ValueError('finite nonnegative request, positive factor and trade unit required')
    lots = math.floor(amount * factor / unit)
    result = lots * unit / factor
    # A binary division at an exact boundary may round one ULP upward. Reduce
    # by a complete unit instead of permitting a fill larger than requested.
    if result > amount:
        result = max(0, lots - 1) * unit / factor
    return result


class StrictRequestedQuantityExchange(Exchange):
    def round_amount_by_trade_unit(self, deal_amount, factor=None, stock_id=None, start_time=None, end_time=None):
        if self.trade_w_adj_price or self.trade_unit is None:
            return deal_amount
        actual_factor = self._get_factor_or_raise_error(factor=factor, stock_id=stock_id, start_time=start_time, end_time=end_time)
        return strict_floor_units(deal_amount, actual_factor, self.trade_unit)
