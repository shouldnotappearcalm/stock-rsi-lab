"""Fixed monthly long-only low-volatility factor from mature month-end prices."""
import math
import statistics


def complete_month_ends(calendar, as_of, count=37):
    calendar = tuple(calendar)
    if tuple(sorted(set(calendar))) != calendar or count < 3:
        raise ValueError("explicit sorted unique calendar and at least three endpoints required")
    index = calendar.index(as_of)
    if index + 1 >= len(calendar) or calendar[index + 1].strftime("%Y-%m") == as_of.strftime("%Y-%m"):
        raise ValueError("formation requires a complete month with a known next session")
    by_month = {}
    for day in calendar[:index + 1]:
        by_month[(day.year, day.month)] = day
    values = tuple(by_month.values())[-count:]
    ordinals = [day.year * 12 + day.month for day in values]
    if len(values) != count or any(right - left != 1 for left, right in zip(ordinals, ordinals[1:])):
        raise ValueError("complete consecutive monthly price history required")
    return values


def monthly_volatility(view, symbol, endpoints):
    if len(endpoints) < 3 or endpoints[-1] != view.as_of or tuple(sorted(set(endpoints))) != tuple(endpoints):
        raise ValueError("monthly factor endpoints must end at formation time")
    prices = [view.value(symbol, "close", day.isoformat()) for day in endpoints]
    if any(value is None or not math.isfinite(value) or value <= 0 for value in prices):
        return None
    returns = [last / first - 1 for first, last in zip(prices, prices[1:])]
    value = statistics.stdev(returns) * math.sqrt(12)
    return value if math.isfinite(value) and value > 0 else None


def lowest_decile(scores):
    if not scores or any(not math.isfinite(value) or value < 0 for value in scores.values()):
        raise ValueError("finite nonnegative volatility scores required")
    count = max(1, len(scores) // 10)
    return tuple(sorted(scores, key=lambda symbol: (scores[symbol], symbol))[:count])
