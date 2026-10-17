"""One fixed calendar-month MAX hypothesis, an A-share engineering adaptation.

This follows the original MAX signal, not the price-limit aggregation variant.
No tuning windows, tail averaging, or future outcome inputs are accepted.
"""
import math

from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile, choose_development_lead

FAMILIES = ('low_max_calendar',)
START, END = '2024-01-02', '2025-12-31'


def calendar_max_score(closes, volumes):
    if not volumes or len(closes) != len(volumes) + 1:
        raise ValueError('full month returns and one preceding close required')
    if (any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in closes)
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in volumes)):
        return None
    returns = [b/a - 1 for a, b, volume in zip(closes, closes[1:], volumes) if volume > 0]
    if not returns or any(not math.isfinite(r) for r in returns):
        return None
    return -max(returns)


def build_targets(snapshot, memberships, start=START, end=END):
    if start < START or start > end or end > END:
        raise ValueError('calendar MAX development cannot read beyond 2025')
    targets = {name: {} for name in (*FAMILIES, 'eligible_equal_weight')}
    receipts = []
    for index, day in enumerate(snapshot.calendar):
        if not start <= day.isoformat() <= end:
            continue
        if index == 0:
            raise ValueError('preceding calendar-month boundary is missing')
        previous = snapshot.calendar[index-1]
        if (previous.year, previous.month) == (day.year, day.month):
            continue
        expected_month = (day.year, day.month-1) if day.month > 1 else (day.year-1, 12)
        if (previous.year, previous.month) != expected_month:
            raise ValueError('preceding exchange month is missing')
        first = index-1
        while first > 0 and (snapshot.calendar[first-1].year, snapshot.calendar[first-1].month) == expected_month:
            first -= 1
        if first == 0:
            raise ValueError('complete month needs its preceding closing price')
        days = snapshot.calendar[first:index]
        close_days = snapshot.calendar[first-1:index]
        names = sorted(code for code, spans in memberships.items()
                       if any(a <= previous.isoformat() <= b for a, b in spans))
        if len(names) < 200:
            raise ValueError('historical main-board CSI500 universe unexpectedly small')
        view = AsOfPrices(snapshot, previous)
        scores, counts = {}, {}
        for code in names:
            factor = view.value(code, 'factor', previous.isoformat())
            volume = view.value(code, 'volume', previous.isoformat())
            if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (factor, volume)):
                continue
            closes = [view.value(code, 'close', d.isoformat()) for d in close_days]
            volumes = [view.value(code, 'volume', d.isoformat()) for d in days]
            score = calendar_max_score(closes, volumes)
            if score is not None:
                scores[code] = score
                counts[code] = sum(v > 0 for v in volumes)
        if len(scores) < 100 or len(scores) < .8 * len(names):
            raise ValueError('complete month coverage below registered admission')
        selected = highest_decile(scores)
        for name, chosen in ((FAMILIES[0], selected), ('eligible_equal_weight', sorted(scores))):
            targets[name][day.isoformat()] = {'as_of': previous.isoformat(),
                'weights': {code: .95/len(chosen) for code in chosen}}
        receipts.append({'execution_session': day.isoformat(), 'formation_asof': previous.isoformat(),
            'return_month': previous.strftime('%Y-%m'), 'baseline_close_day': close_days[0].isoformat(),
            'return_begin': days[0].isoformat(), 'daily_return_observations': len(days),
            'latest_factor_price_read': view.latest_read.isoformat(), 'historical_members': len(names),
            'eligible': len(scores), 'selected': list(selected), 'scores': scores,
            'active_return_observations': counts, 'upper_limit_return_aggregation_implemented': False})
    return targets, receipts
