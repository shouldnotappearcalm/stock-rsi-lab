"""One frozen pre2026 low-risk-family trial; CSI500-only CAPM residual proxy.

This module reads only through AsOfPrices. It is not an FF3 replication and
computes no portfolio performance. n>=15 is a local full-calendar admission
rule. SS epsilon 1e-24 is a fixed numerical-degeneracy guard, not a fitted
parameter. The supplied calendar must be an authenticated exchange calendar.
"""
from datetime import date
from math import fsum, isfinite, sqrt
import re

from stock_rsi.prior_close_orders import AsOfPrices

START = '2024-01-02'
END = '2025-12-31'
MARKET = 'SH000905'
FAMILIES = ('low_market_residual_vol_1m',)
CONTROL = 'low_total_vol_1m_control'
MIN_OBSERVATIONS = 15
NUMERIC_SS_EPSILON = 1e-24
_MAINBOARD = re.compile(r'^(?:SH(?:600|601|603|605)|SZ(?:000|001|002|003))\d{3}$')


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _positive(value):
    return _finite(value) and value > 0


def fit_residual_volatility(stock_returns, market_returns):
    """OLS with intercept; unannualized residual sigma has n-2 degrees freedom."""
    if len(stock_returns) != len(market_returns):
        raise ValueError('stock and market return shapes differ')
    n = len(stock_returns)
    if n < MIN_OBSERVATIONS or not all(_finite(v) for v in (*stock_returns, *market_returns)):
        return None
    try:
        mx, my = fsum(market_returns) / n, fsum(stock_returns) / n
        dx = [v - mx for v in market_returns]
        dy = [v - my for v in stock_returns]
        xx = fsum(v * v for v in dx)
        if not isfinite(xx) or xx <= NUMERIC_SS_EPSILON:
            return None
        beta = fsum(x * y for x, y in zip(dx, dy)) / xx
        alpha = my - beta * mx
        sse = fsum((y - beta * x) ** 2 for x, y in zip(dx, dy))
        if not isfinite(sse) or sse <= NUMERIC_SS_EPSILON:
            return None
        sigma = sqrt(sse / (n - 2))
        total = sqrt(fsum(v * v for v in dy) / (n - 1))
        if not all(_finite(v) for v in (alpha, beta, sigma, total)) or sigma <= 0 or total <= 0:
            return None
        return dict(n=n, alpha=alpha, beta=beta, sigma=sigma, sse=sse,
                    total_volatility=total, market_centered_ss=xx)
    except (OverflowError, ValueError, ZeroDivisionError):
        return None


def _simple_returns(closes):
    if not all(_positive(v) for v in closes):
        return None
    result = [b / a - 1 for a, b in zip(closes, closes[1:])]
    return result if all(_finite(v) for v in result) else None


def residual_volatility_1m(stock_closes, market_closes):
    if len(stock_closes) != len(market_closes):
        raise ValueError('stock and market close shapes differ')
    if len(stock_closes) < MIN_OBSERVATIONS + 1:
        return None
    y, x = _simple_returns(stock_closes), _simple_returns(market_closes)
    return None if y is None or x is None else fit_residual_volatility(y, x)


def lowest_quintile(scores):
    if not scores or not all(_positive(v) for v in scores.values()):
        raise ValueError('quintile scores must be finite and positive')
    ranked = sorted(scores, key=lambda symbol: (scores[symbol], symbol))
    return tuple(ranked[:max(1, len(ranked) // 5)])


def _previous_month(day):
    return (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)


def _active(spans, as_of):
    # Membership and price clocks share the preceding-session date.
    return any(date.fromisoformat(str(a)) <= as_of <= date.fromisoformat(str(b)) for a, b in spans)


def _target(selected, as_of, execution):
    return dict(as_of=as_of, execution_session=execution,
                weights={symbol: .95 / len(selected) for symbol in selected})


def build_targets(snapshot, memberships, start=START, end=END):
    """Apply this one fixed trial to complete source months; no account replay.

    The calendar, not weekday arithmetic, defines the exchange sessions. A
    valid baseline belongs to the immediately preceding natural month; every
    explicit return-month session and baseline must have all required fields.
    """
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first < date.fromisoformat(START) or last > date.fromisoformat(END) or first > last:
        raise ValueError('requested execution range exceeds fixed pre2026 cap')
    calendar = tuple(snapshot.calendar)
    if any(not isinstance(d, date) for d in calendar) or list(calendar) != sorted(set(calendar)):
        raise ValueError('source calendar must contain ordered unique dates')
    targets = {FAMILIES[0]: {}, 'eligible_equal_weight': {}, CONTROL: {}}
    receipts = []
    for i, execution in enumerate(calendar):
        if not first <= execution <= last:
            continue
        if i == 0:
            raise ValueError('missing previous source session')
        prior = calendar[i - 1]
        if (prior.year, prior.month) == (execution.year, execution.month):
            continue
        month = _previous_month(execution)
        if (prior.year, prior.month) != month:
            raise ValueError('missing preceding complete natural month')
        j = i - 1
        while j > 0 and (calendar[j - 1].year, calendar[j - 1].month) == month:
            j -= 1
        if j == 0 or (calendar[j - 1].year, calendar[j - 1].month) != _previous_month(calendar[j]):
            raise ValueError('missing preceding-month baseline close')
        days, close_days = calendar[j:i], calendar[j - 1:i]
        if len(days) < MIN_OBSERVATIONS:
            raise ValueError('complete source month has fewer than 15 return observations')
        view = AsOfPrices(snapshot, prior)
        market_closes = [view.value(MARKET, 'close', d.isoformat()) for d in close_days]
        market_returns = _simple_returns(market_closes)
        if market_returns is None:
            raise ValueError('market close missing or nonpositive')
        market_mean = fsum(market_returns) / len(market_returns)
        market_ss = fsum((v - market_mean) ** 2 for v in market_returns)
        if not isfinite(market_ss) or market_ss <= NUMERIC_SS_EPSILON:
            raise ValueError('market variance is numerically degenerate')
        historical = sorted(symbol for symbol, spans in memberships.items()
                            if _MAINBOARD.fullmatch(symbol) and _active(spans, prior))
        fits, excluded = {}, {}
        for symbol in historical:
            fields = {field: [view.value(symbol, field, d.isoformat()) for d in close_days]
                      for field in ('close', 'factor', 'volume')}
            invalid = {field: [d.isoformat() for d, v in zip(close_days, values) if not _positive(v)]
                       for field, values in fields.items()}
            invalid = {field: bad for field, bad in invalid.items() if bad}
            if invalid:
                excluded[symbol] = dict(reason='incomplete_or_nonpositive_stock_fields', invalid_dates=invalid)
                continue
            fit = residual_volatility_1m(fields['close'], market_closes)
            if fit is None:
                excluded[symbol] = dict(reason='nonfinite_or_numerically_degenerate_residual')
            else:
                fits[symbol] = fit
        if len(fits) < 5:
            raise ValueError('formation requires at least five (5) eligible mainboard members')
        scores = {symbol: fit['sigma'] for symbol, fit in fits.items()}
        total_scores = {symbol: fit['total_volatility'] for symbol, fit in fits.items()}
        selected, control = lowest_quintile(scores), lowest_quintile(total_scores)
        day, as_of = execution.isoformat(), prior.isoformat()
        targets[FAMILIES[0]][day] = _target(selected, as_of, day)
        targets['eligible_equal_weight'][day] = _target(tuple(fits), as_of, day)
        targets[CONTROL][day] = _target(control, as_of, day)
        receipts.append(dict(
            execution_session=day, formation_asof=as_of, formation_at=as_of + 'T15:05:00+08:00',
            return_month=f'{month[0]:04d}-{month[1]:02d}',
            sample_dates=[d.isoformat() for d in days], return_dates=[d.isoformat() for d in days],
            baseline_close_day=close_days[0].isoformat(), close_dates=[d.isoformat() for d in close_days],
            n=len(days), daily_return_observations=len(days), minimum_return_observations=MIN_OBSERVATIONS,
            minimum_n_basis='LOCAL_COMPLETE_MONTH_CALENDAR_SOURCE_ADMISSION_PARAMETER_NOT_PAPER_RULE',
            numeric_ss_epsilon=NUMERIC_SS_EPSILON, market_instrument=MARKET,
            market_centered_ss=market_ss, historical_members=len(historical), eligible=len(fits),
            excluded=excluded, fits=fits, scores=scores, selected=list(selected),
            control_total_volatility_scores=total_scores, control_selected=list(control),
            controls_selectable=False, latest_factor_price_read=view.latest_read.isoformat(),
            primary_trial_id=FAMILIES[0], trial_family='EXISTING_LOW_RISK_LOTTERY_FAMILY_ADDITIONAL_TRIAL',
            model='CSI500_MARKET_ONLY_CAPM_PROXY_NOT_FF3_REPLICATION'))
    return targets, receipts
