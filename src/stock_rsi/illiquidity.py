"""One fixed22-session Amihud signal; CNY amount conversion is explicit."""
import math
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile,choose_development_lead

FAMILIES=('amihud22',)
START,END='2024-01-02','2025-12-31'
WINDOW=22
AMOUNT_CNY_PER_UNIT=1000


def illiquidity_score(closes,amounts,volumes):
    if len(closes)!=WINDOW+1 or len(amounts)!=WINDOW or len(volumes)!=WINDOW:
        raise ValueError('22 explicit daily returns and one preceding close required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for values in (closes,amounts,volumes) for v in values):
        return None
    ratios=[abs(b/a-1)/(amount*AMOUNT_CNY_PER_UNIT) for a,b,amount in zip(closes,closes[1:],amounts)]
    if any(not math.isfinite(v) for v in ratios):return None
    return math.fsum(ratios)/WINDOW


def build_targets(snapshot,memberships,start=START,end=END):
    if start<START or start>end or end>END:raise ValueError('illiquidity development cannot read beyond2025')
    if tuple(sorted(set(snapshot.calendar)))!=tuple(snapshot.calendar):raise ValueError('explicit sorted unique sessions required')
    targets={n:{} for n in (*FAMILIES,'eligible_equal_weight')};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end:continue
        if index==0:raise ValueError('preceding explicit exchange session required')
        previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==day.strftime('%Y-%m'):continue
        expected_month=(day.year,day.month-1) if day.month>1 else (day.year-1,12)
        if (previous.year,previous.month)!=expected_month:raise ValueError('preceding exchange month missing')
        if index<WINDOW+1:raise ValueError('22-session window and preceding close missing')
        close_days=snapshot.calendar[index-WINDOW-1:index];days=close_days[1:]
        names=sorted(c for c,spans in memberships.items() if any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<200:raise ValueError('historical CSI500 main-board universe unexpectedly small')
        view=AsOfPrices(snapshot,previous);scores={};excluded={}
        for code in names:
            factor=view.value(code,'factor',previous.isoformat())
            if type(factor) not in (int,float) or not math.isfinite(factor) or factor<=0:
                excluded[code]='MISSING_FORMATION_FACTOR';continue
            score=illiquidity_score([view.value(code,'close',d.isoformat()) for d in close_days],
                [view.value(code,'amount',d.isoformat()) for d in days],
                [view.value(code,'volume',d.isoformat()) for d in days])
            if score is None:excluded[code]='INCOMPLETE_OR_INACTIVE_22_SESSION_WINDOW'
            else:scores[code]=score
        if len(scores)<100 or len(scores)<.8*len(names):raise ValueError('22-session amount/price coverage below registered80% admission')
        selected=highest_decile(scores)
        for name,chosen in ((FAMILIES[0],selected),('eligible_equal_weight',sorted(scores))):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(chosen) for code in chosen}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),
            'baseline_close_day':close_days[0].isoformat(),'return_begin':days[0].isoformat(),
            'daily_return_observations':len(days),'amount_CNY_per_source_unit':AMOUNT_CNY_PER_UNIT,
            'historical_members':len(names),'eligible':len(scores),'excluded':excluded,'selected':list(selected),
            'scores':scores,'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
