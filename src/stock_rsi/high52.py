"""One trailing-year price-to-high hypothesis, long-only monthly adaptation.

Twelve complete calendar months of adjusted daily highs are required. This is
not a reproduction of the original six-cohort long/short paper portfolios.
"""
import math
from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile,choose_development_lead

FAMILIES=('near_52w_high',)
START,END='2024-01-02','2025-12-31'


def high52_score(closes,highs):
    if not closes or len(closes)!=len(highs):raise ValueError('complete paired daily closes and highs required')
    if (any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in (*closes,*highs))
            or any(c>h for c,h in zip(closes,highs))):return None
    value=closes[-1]/max(highs)
    return value if math.isfinite(value) and 0<value<=1 else None


def build_targets(snapshot,memberships,start=START,end=END):
    if start<START or start>end or end>END:raise ValueError('52-week high development cannot read beyond2025')
    targets={n:{} for n in (*FAMILIES,'eligible_equal_weight')};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end:continue
        if index==0:raise ValueError('preceding explicit exchange session required')
        previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==day.strftime('%Y-%m'):continue
        endpoints=complete_month_ends(snapshot.calendar,previous,count=13)
        days=tuple(d for d in snapshot.calendar if endpoints[0]<d<=previous)
        names=sorted(c for c,spans in memberships.items() if any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<200:raise ValueError('historical CSI500 main-board universe unexpectedly small')
        scores={};excluded={};view=AsOfPrices(snapshot,previous)
        for code in names:
            factor=view.value(code,'factor',previous.isoformat());volume=view.value(code,'volume',previous.isoformat())
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (factor,volume)):
                excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
            closes=[view.value(code,'close',d.isoformat()) for d in days]
            highs=[view.value(code,'high',d.isoformat()) for d in days]
            score=high52_score(closes,highs)
            if score is None:excluded[code]='MISSING_OR_INCONSISTENT_COMPLETE_WINDOW'
            else:scores[code]=score
        if len(scores)<100 or len(scores)<.8*len(names):raise ValueError('complete trailing-year coverage below registered80% admission')
        selected=highest_decile(scores)
        for name,chosen in ((FAMILIES[0],selected),('eligible_equal_weight',sorted(scores))):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(chosen) for code in chosen}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),
            'window_preceding_month_end':endpoints[0].isoformat(),'window_begin':days[0].isoformat(),
            'window_end':previous.isoformat(),'complete_calendar_months':12,'explicit_window_sessions':len(days),
            'historical_members':len(names),'eligible':len(scores),'excluded':excluded,
            'selected':list(selected),'scores':scores,'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
