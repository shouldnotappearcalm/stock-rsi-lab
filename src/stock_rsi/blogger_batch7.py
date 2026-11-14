"""Monthly four-ETF allocation; execution only uses the completed account."""
import math
import statistics

SYMBOLS = ('SH510300', 'SH510500', 'SH518880', 'SZ159915')
NAMES = ('equal4', 'invvol60')
LOOKBACK = 60


def allocation(name, histories):
    if name == 'equal4' and not histories:
        return dict.fromkeys(SYMBOLS, .95/len(SYMBOLS)), {}
    if name != 'invvol60' or set(histories) != set(SYMBOLS):
        raise ValueError('declared allocation and history required')
    sigma = {}
    for c in SYMBOLS:
        p = histories[c]
        if len(p) != LOOKBACK+1 or any(not math.isfinite(x) or x <= 0 for x in p):
            raise ValueError('complete 61 positive closes required')
        sigma[c] = statistics.stdev(b/a-1 for a,b in zip(p,p[1:]))
        if not math.isfinite(sigma[c]) or sigma[c] <= 0:
            raise ValueError('positive finite volatility required')
    normalizer = math.fsum(1/s for s in sigma.values())
    return {c:.95*(1/sigma[c])/normalizer for c in SYMBOLS}, sigma


def lot(q, factor):
    n = math.floor(q*factor/100)
    rounded = 100*n/factor
    return rounded if rounded <= q else 100*max(0,n-1)/factor


def orders_for(target, owned, prices, factors, cash, equity, extra):
    if (set(target)!=set(SYMBOLS) or set(prices)!=set(SYMBOLS) or set(factors)!=set(SYMBOLS)
            or set(owned)-set(SYMBOLS) or extra not in (20,40)
            or any(not math.isfinite(v) or v < 0 for v in [cash,*target.values(),*owned.values()])
            or any(not math.isfinite(v) or v <= 0 for v in [equity,*prices.values(),*factors.values()])):
        raise ValueError('finite declared account, targets and marks required')
    sells = []
    for c in SYMBOLS:
        q = lot(max(0,owned.get(c,0)-target[c]),factors[c])
        if q:
            sells.append({'instrument':c,'side':'SELL','normalized_units':q})
    if sells:
        return sells
    remaining = max(0,cash-.05*equity)
    buys = []
    rate = (5+extra)/10000
    for c in SYMBOLS:
        gap = max(0,target[c]-owned.get(c,0))*prices[c]
        budget = max(0,min(gap,remaining/(1+rate),remaining-5))
        q = lot(budget/prices[c],factors[c])
        if q:
            value = q*prices[c]
            remaining -= value+max(5,value*rate)
            if remaining < -1e-8:
                raise ValueError('planned buys and fees exceed available budget')
            buys.append({'instrument':c,'side':'BUY','normalized_units':q})
    return buys
