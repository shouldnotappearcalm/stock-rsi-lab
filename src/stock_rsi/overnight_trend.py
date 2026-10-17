"""Past-only overnight-trend evidence for a fixed monthly avoidance probe."""
import calendar
import math
from datetime import date


def shift_month(year, month, offset):
    value = year * 12 + month - 1 + offset
    return divmod(value, 12)[0], divmod(value, 12)[1] + 1


def formation_window(execution_month):
    """12-2 convention: eleven complete months, skipping the latest month."""
    year, month = map(int, execution_month.split("-"))
    sy, sm = shift_month(year, month, -12)
    ey, em = shift_month(year, month, -2)
    return date(sy, sm, 1), date(ey, em, calendar.monthrange(ey, em)[1])


class PastOnlyPrices:
    def __init__(self, snapshot, as_of):
        self.snapshot = snapshot
        self.as_of = as_of
        self.calendar = tuple(day for day in snapshot.calendar if day <= as_of)
        self.latest_read = None

    def value(self, symbol, field, day):
        target = date.fromisoformat(day)
        if target > self.as_of:
            raise ValueError("overnight factor attempted to read a future price")
        self.latest_read = max(target, self.latest_read or target)
        return self.snapshot.value(symbol, field, day)


def overnight_trend(view, symbol, execution_month, minimum_month_coverage=0.8):
    start, end = formation_window(execution_month)
    if view.as_of != end:
        raise ValueError("factor view must end at the registered formation cutoff")
    calendar_index = {day: i for i, day in enumerate(view.calendar)}
    monthly = {}
    for day in view.calendar:
        if start <= day <= end:
            monthly.setdefault(day.strftime("%Y-%m"), []).append(day)
    if len(monthly) != 11:
        return None
    total_log = 0.0
    for days in monthly.values():
        valid = 0
        month_log = 0.0
        for day in days:
            index = calendar_index[day]
            if index == 0:
                continue
            previous = view.calendar[index - 1]
            values = [view.value(symbol, field, target.isoformat()) for field, target in (
                ("adjclose", day), ("adjclose", previous), ("close", day), ("open", day)
            )]
            if any(value is None or not math.isfinite(value) or value <= 0 for value in values):
                continue
            # Total adjusted return / intraday raw return allocates actions overnight.
            gross = (values[0] / values[1]) / (values[2] / values[3])
            month_log += math.log(gross)
            valid += 1
        if valid / len(days) < minimum_month_coverage:
            return None
        total_log += month_log
    return math.expm1(total_log) / 11


def weakest_decile(scores):
    if not scores or any(not math.isfinite(value) for value in scores.values()):
        raise ValueError("finite monthly overnight scores required")
    count = max(1, len(scores) // 10)
    return tuple(sorted(scores, key=lambda symbol: (scores[symbol], symbol))[:count])
