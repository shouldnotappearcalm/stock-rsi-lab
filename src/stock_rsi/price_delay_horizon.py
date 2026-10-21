"""Unchanged price-delay formation rule, separately registered interim extension.

No candidate selection or 2026 outcome-based modification is permitted here.
The original pre-2026 module and its date guard remain unchanged.
"""
from datetime import date, timedelta
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.price_delay import START, FAMILIES, CONTROL, positive, measurement_design, stock_measure

HORIZON_END = '2026-10-20'


def build_targets(snapshot, memberships, start=START, end=HORIZON_END):
    if start < START or start > end or end > HORIZON_END: raise ValueError('price-delay diagnostic is capped at2026-10-20')
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
