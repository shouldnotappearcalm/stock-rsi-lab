"""Fixed 2017 A-share recipe indicators. No account, calendar, or future API."""
from __future__ import annotations

import math


NAMES = ('golden_cross', 'macd', 'rsi')
SYMBOLS = ('SZ000001', 'SH601988', 'SZ000068')


def prices(values, count):
    values = tuple(values)
    if len(values) != count or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError('exact finite positive source history required')
    return values


def cross(previous, current):
    if not all(math.isfinite(x) for x in (previous, current)):
        raise ValueError('finite crossing values required')
    return 'BUY' if previous < 0 < current else 'SELL' if previous > 0 > current else 'HOLD'


def golden_cross(values):
    p = prices(values, 121)
    before = sum(p[-21:-1]) / 20 - sum(p[:-1]) / 120
    now = sum(p[-20:]) / 20 - sum(p[-120:]) / 120
    return {'action': cross(before, now), 'previous_difference': before, 'difference': now}


def macd_histogram(values):
    """TA-Lib default compatibility: EMA seeds aligned at slow-1, then signal SMA.

    Each call intentionally restarts from the source's fixed 100-close window.
    An infinite-history EMA would define a different strategy.
    """
    p = prices(values, 100)
    fast = sum(p[14:26]) / 12
    slow = sum(p[:26]) / 26
    diffs = [fast - slow]
    for value in p[26:]:
        fast += (value - fast) * (2. / 13.)
        slow += (value - slow) * (2. / 27.)
        diffs.append(fast - slow)
    signal = sum(diffs[:9]) / 9
    hist = [diffs[8] - signal]
    for value in diffs[9:]:
        signal += (value - signal) * .2
        hist.append(value - signal)
    return tuple(hist)


def macd(values):
    hist = macd_histogram(values)
    return {'action': cross(hist[-2], hist[-1]), 'previous_histogram': hist[-2], 'histogram': hist[-1]}


def rsi(values):
    # Original history_bars requests only period+1=15 observations. Therefore
    # TA-Lib emits only its seeded RSI, not a Wilder recursion over older bars.
    p = prices(values, 15)
    changes = [b - a for a, b in zip(p, p[1:])]
    up = sum(max(x, 0) for x in changes)
    down = sum(max(-x, 0) for x in changes)
    value = 100 * up / (up + down) if up + down else 0.
    return {'action': 'BUY' if value < 30 else 'SELL' if value > 85 else 'HOLD', 'rsi': value}


def evaluate(name, values):
    if name not in NAMES:
        raise ValueError('unregistered published strategy')
    return {'golden_cross': golden_cross, 'macd': macd, 'rsi': rsi}[name](values)


def admission(metrics):
    fields = ('2024_return_pct', '2025_return_pct', 'average_exposure_pct')
    if any(type(metrics.get(k)) not in (int, float) or not math.isfinite(metrics[k]) for k in fields):
        raise ValueError('finite complete two-year metrics required')
    return (metrics['2024_return_pct'] > 0 and metrics['2025_return_pct'] > 0
            and metrics['average_exposure_pct'] >= 90 and metrics.get('unverified_held_marks') == 0)
