"""One fixed old-six-month cumulative-return hypothesis; no recent-return input."""
import math
from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile,choose_development_lead

FAMILIES=('intermediate_mom12_7',)
START,END='2024-01-02','2025-12-31'


def intermediate_score(closes):
    if len(closes)!=7:raise ValueError('seven consecutive month-end closes for six old returns required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in closes):return None
    value=closes[-1]/closes[0]-1
    return value if math.isfinite(value) else None


def build_targets(snapshot,memberships,start=START,end=END):
    if start<START or start>end or end>END:raise ValueError('intermediate momentum development cannot read beyond2025')
    targets={n:{} for n in (*FAMILIES,'eligible_equal_weight')};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end:continue
        if index==0:raise ValueError('preceding explicit exchange session required')
        previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==day.strftime('%Y-%m'):continue
        endpoints=complete_month_ends(snapshot.calendar,previous,count=13)
        signal_endpoints=endpoints[:7]
        names=sorted(c for c,spans in memberships.items() if any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<200:raise ValueError('historical CSI500 main-board universe unexpectedly small')
        view=AsOfPrices(snapshot,previous);scores={};excluded={}
        for code in names:
            current=[view.value(code,f,previous.isoformat()) for f in ('factor','volume','close')]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in current):
                excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
            score=intermediate_score([view.value(code,'close',d.isoformat()) for d in signal_endpoints])
            if score is None:excluded[code]='MISSING_OLD_MONTH_END_HISTORY'
            else:scores[code]=score
        if len(scores)<100 or len(scores)<.8*len(names):raise ValueError('old-month price coverage below registered80% admission')
        selected=highest_decile(scores)
        for name,chosen in ((FAMILIES[0],selected),('eligible_equal_weight',sorted(scores))):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(chosen) for code in chosen}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),
            'signal_begin_close':signal_endpoints[0].isoformat(),'signal_end_close':signal_endpoints[-1].isoformat(),
            'signal_return_months':[d.strftime('%Y-%m') for d in endpoints[1:7]],
            'skipped_recent_return_months':[d.strftime('%Y-%m') for d in endpoints[7:]],
            'historical_members':len(names),'eligible':len(scores),'excluded':excluded,'selected':list(selected),
            'scores':scores,'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
