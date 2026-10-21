"""One preregistered weekly D1 adaptation; development data stop in2025."""
from bisect import bisect_left, bisect_right
from datetime import date, timedelta
import math

from stock_rsi.prior_close_orders import AsOfPrices

START, END = '2024-01-02', '2025-12-31'
MARKET = 'SH000905'
FAMILIES = ('price_delay_d1',)
CONTROL = 'low_delay_control'


def positive(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0


def fit_delay(ys, xs):
    if len(ys) != len(xs) or any(len(row) != 5 for row in xs):
        raise ValueError('same paired sample and five market regressors required')
    n = len(ys)
    if n < 40 or any(not math.isfinite(v) for v in (*ys, *(v for row in xs for v in row))): return None
    ym = math.fsum(ys)/n; means = [math.fsum(row[j] for row in xs)/n for j in range(5)]
    y = [v-ym for v in ys]; columns = [[row[j]-means[j] for row in xs] for j in range(5)]
    yy = math.fsum(v*v for v in y); norms = [math.sqrt(math.fsum(v*v for v in col)) for col in columns]
    if yy <= 1e-24 or min(norms) <= 1e-12: return None
    # Twice-reorthogonalized modified Gram-Schmidt; no regularization or fit
    # fallback. Rank-deficient observations are excluded, not assigned a score.
    q = []; r = [[0.]*5 for _ in range(5)]
    for j, col in enumerate(columns):
        v = list(col)
        for _ in range(2):
            for i, qi in enumerate(q):
                projection = math.fsum(a*b for a, b in zip(qi, v)); r[i][j] += projection
                v = [a-projection*b for a, b in zip(v, qi)]
        length = math.sqrt(math.fsum(a*a for a in v))
        if length <= 1e-12*max(norms): return None
        r[j][j] = length; q.append([a/length for a in v])
    qty = [math.fsum(a*b for a, b in zip(qi, y)) for qi in q]
    coefficients = [0.]*5
    for j in range(4, -1, -1):
        coefficients[j] = (qty[j]-math.fsum(r[j][k]*coefficients[k] for k in range(j+1, 5)))/r[j][j]
    xy = math.fsum(a*b for a, b in zip(columns[0], y))
    restricted = xy*xy/(norms[0]**2*yy); full = math.fsum(v*v for v in qty)/yy
    if full <= 1e-12: return None
    delay = 1-restricted/full
    if not (-1e-9 <= delay <= 1+1e-9 and 0 <= restricted <= 1+1e-9 and 0 <= full <= 1+1e-9):
        raise ValueError('nested OLS R-squared arithmetic failed')
    return {'delay': min(1., max(0., delay)), 'r2_restricted': min(1., restricted), 'r2_full': min(1., full),
        'alpha': ym-math.fsum(a*b for a, b in zip(coefficients, means)), 'coefficients': coefficients, 'observations': n}


def weekly_endpoints(calendar, cap):
    if not calendar or list(calendar) != sorted(set(calendar)): raise ValueError('explicit ordered unique calendar required')
    last = cap-timedelta(days=(cap.weekday()-2)%7)
    result = []
    for k in range(56, -1, -1):
        marker = last-timedelta(days=7*k); i = bisect_right(calendar, marker)-1
        if i < 0: raise ValueError('market history shorter than registered weekly grid')
        result.append({'marker': marker, 'session': calendar[i]})
    return result


def measurement_design(snapshot, cap):
    ends = weekly_endpoints(snapshot.calendar, cap); view = AsOfPrices(snapshot, cap)
    closes = [view.value(MARKET, 'close', row['session'].isoformat()) for row in ends]
    if not all(positive(v) for v in closes): raise ValueError('missing market endpoint; no forward fill')
    returns = [closes[i+1]/closes[i]-1 if ends[i+1]['session'] > ends[i]['session'] else None for i in range(56)]
    rows = []
    for k in range(4, 56):
        values = [returns[k-i] for i in range(5)]
        if all(v is not None for v in values): rows.append((k, values))
    if len(rows) < 40 or fit_delay([v[0] for _, v in rows], [v for _, v in rows]) is None:
        raise ValueError('market weekly design has insufficient paired coverage or rank')
    return ends, rows, view


def stock_measure(snapshot, code, cap, ends, market_rows):
    view = AsOfPrices(snapshot, cap); first = bisect_left(snapshot.calendar, ends[4]['session'])
    last = bisect_right(snapshot.calendar, ends[-1]['session']); sessions = snapshot.calendar[first:last]
    observations = {d: [view.value(code, f, d.isoformat()) for f in ('close', 'factor', 'volume')] for d in sessions}
    valid = {d: all(positive(v) for v in row) for d, row in observations.items()}
    ys = []; xs = []; missing = []
    for k, market in market_rows:
        left, right = ends[k]['session'], ends[k+1]['session']
        needed = snapshot.calendar[bisect_left(snapshot.calendar, left):bisect_right(snapshot.calendar, right)]
        if right <= left or not all(valid.get(d, False) for d in needed):
            missing.append(ends[k+1]['marker'].isoformat()); continue
        ys.append(observations[right][0]/observations[left][0]-1); xs.append(market)
    result = fit_delay(ys, xs)
    return result, missing, view.latest_read


def build_targets(snapshot, memberships, start=START, end=END):
    if start < START or start > end or end > END: raise ValueError('price-delay development is capped at2025')
    targets = {name: {} for name in (*FAMILIES, 'eligible_equal_weight', CONTROL)}; receipts = []
    for i, day in enumerate(snapshot.calendar):
        if not start <= day.isoformat() <= end: continue
        if i < 1: raise ValueError('prior session required')
        prior = snapshot.calendar[i-1]
        if (prior.year, prior.month) == (day.year, day.month): continue
        cap = date(prior.year, prior.month, 1)-timedelta(days=1)
        ends, design, market_view = measurement_design(snapshot, cap)
        eligible_view = AsOfPrices(snapshot, prior)
        names = sorted(c for c, spans in memberships.items() if any(a <= prior.isoformat() <= b for a, b in spans))
        if len(names) < 200: raise ValueError('historical ordinary mainboard membership unexpectedly small')
        fits = {}; excluded = {}; missing_weeks = {}; latest = market_view.latest_read
        for code in names:
            if not all(positive(eligible_view.value(code, f, prior.isoformat())) for f in ('close', 'factor', 'volume')):
                excluded[code] = 'MISSING_OR_INACTIVE_FORMATION'; continue
            fit, missing, read_at = stock_measure(snapshot, code, cap, ends, design)
            if read_at is not None: latest = max(latest, read_at)
            if fit is None: excluded[code] = 'INSUFFICIENT_40_PAIRED_WEEKS_OR_DEGENERATE'; continue
            fits[code] = fit
            if missing: missing_weeks[code] = missing
        if len(fits) < 100 or len(fits) < .5*len(names):
            raise ValueError(f'registered factor coverage below100 or50percent: {day} eligible={len(fits)} members={len(names)}')
        count = max(1, len(fits)//10)
        high = sorted(fits, key=lambda c: (-fits[c]['delay'], c))[:count]
        low = sorted(fits, key=lambda c: (fits[c]['delay'], c))[:count]
        for name, chosen in ((FAMILIES[0], high), ('eligible_equal_weight', sorted(fits)), (CONTROL, low)):
            targets[name][day.isoformat()] = {'as_of': prior.isoformat(), 'weights': {c: .95/len(chosen) for c in chosen}}
        receipts.append({'execution_session': day.isoformat(), 'formation_asof': prior.isoformat(),
            'measurement_cap': cap.isoformat(), 'latest_measurement_price_read': latest.isoformat(),
            'latest_formation_price_read': eligible_view.latest_read.isoformat(), 'historical_members': len(names),
            'eligible': len(fits), 'market_paired_weeks': len(design), 'excluded': excluded, 'missing_stock_weeks': missing_weeks,
            'weekly_endpoints': [{k: v.isoformat() for k, v in row.items()} for row in ends],
            'fits': fits, 'selected': high, 'low_delay_control': low})
    return targets, receipts
