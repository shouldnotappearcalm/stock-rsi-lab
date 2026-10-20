"""Initial rational equal weights; no estimates, ranking or later rebalancing."""
from datetime import date
from fractions import Fraction as F
from stock_rsi.broker import money
from stock_rsi.etf_relative_replay import CODES


def plan_rational_targets(equity,positions,ratios,prices):
    equity=money(equity)
    if equity<=0 or not ratios or any(type(q) is not int or q<0 for q in positions.values()):raise ValueError('positive equity and integer inventory required')
    weights={c:F(int(pair[0]),int(pair[1])) for c,pair in ratios.items()}
    if any(w<0 for w in weights.values()) or sum(weights.values())>1:raise ValueError('long-only rational weights required')
    orders=[]
    for c in sorted(set(positions)|set(weights)):
        held=positions.get(c,0);w=weights.get(c,F(0))
        if not w:
            if held:orders.append(('SELL',c,held))
            continue
        price=money(prices[c])
        if price<=0:raise ValueError('positive visible close required')
        lots=F(equity)*w/F(price)/100;desired=(lots.numerator//lots.denominator)*100
        if desired>held:
            q=(desired-held)//100*100
            if q:orders.append(('BUY',c,q))
        elif held>desired:orders.append(('SELL',c,held-desired))
    return tuple(sorted(orders,key=lambda r:(r[0]!='SELL',r[1])))


class InitialEqualWeight:
    def __init__(self,calendar):
        self.calendar=calendar;self.position=0
        entry=date(2023,12,29)
        if entry not in calendar.days or calendar.days[calendar.days.index(entry)+1:calendar.days.index(entry)+2]!=(date(2024,1,2),):raise ValueError('fixed prior-close entry and first2024 session required')
    def observe_close(self,day,closes,cashflows):
        if self.position>=len(self.calendar.days) or day!=self.calendar.days[self.position]:raise ValueError('ordered explicit sessions required')
        if set(closes)!=set(CODES) or any(money(x)<=0 for x in closes.values()):raise ValueError('three positive visible closes required')
        self.position+=1
        if day!=date(2023,12,29):return None
        return {'as_of':day.isoformat(),'signal':'INITIAL_EQUAL_WEIGHT_BUY_HOLD','target_weight_ratios':{c:['19','60'] for c in CODES},
            'allocation_basis':'equal initial capital; total19/20; no subsequent orders or reinvestment'}
