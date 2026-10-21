"""One pre-2026 size hypothesis using delayed published A-row capitalization."""
import math
from decimal import Decimal

from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import choose_development_lead
from stock_rsi.szse_monthly import month_shift

FAMILIES=('szse_monthly_small_issued_cap',)
START,END='2024-01-02','2025-12-31'


def build_targets(snapshot,memberships,reports,start=START,end=END):
    if start<START or start>end or end>END:raise ValueError('published-size development ends in2025')
    targets={name:{} for name in (*FAMILIES,'eligible_equal_weight')};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end:continue
        if index==0:raise ValueError('prior explicit session required')
        previous=snapshot.calendar[index-1]
        if day.strftime('%Y-%m')==previous.strftime('%Y-%m'):continue
        source_month=month_shift(day.strftime('%Y-%m'),-2)
        report=reports[source_month]
        if (report['month']!=source_month or previous.strftime('%Y-%m')!=month_shift(source_month,1)
                or max(report['article_build_day'],report['table_build_day'])>previous.isoformat()):
            raise ValueError('source document is too late for full-next-trading-month lag')
        names=sorted(c for c,spans in memberships.items() if c.startswith(('SZ000','SZ001','SZ002','SZ003'))
                     and any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<100:raise ValueError('historical Shenzhen main-board universe unexpectedly small')
        covered=[c for c in names if c in report['stocks']]
        if len(covered)<.95*len(names):raise ValueError('published monthly membership coverage below95%')
        view=AsOfPrices(snapshot,previous);scores={}
        for code in covered:
            r=report['stocks'][code]
            if any(r.get(k) is None for k in ('issued_10k_shares','listed_10k_shares','close')):continue
            issued,listed,close=(Decimal(r[k]) for k in ('issued_10k_shares','listed_10k_shares','close'))
            if any(not v.is_finite() or v < 0 for v in (issued,listed,close)) or listed > issued:
                raise ValueError('invalid published share/price fields or listed exceeds issued')
            if r['reported_special_name'] or issued <= 0 or close <= 0:continue
            cap=issued*10000*close
            volume=view.value(code,'volume',previous.isoformat());factor=view.value(code,'factor',previous.isoformat())
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (volume,factor,view.value(code,'close',previous.isoformat()))):continue
            scores[code]=cap
        if len(scores)<50 or len(scores)<.5*len(names):raise ValueError('rankable published-size coverage below registered level')
        chosen=tuple(sorted(scores,key=lambda c:(scores[c],c))[:max(1,len(scores)//10)])
        for name,selected in ((FAMILIES[0],chosen),('eligible_equal_weight',sorted(scores))):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(selected) for code in selected}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),'source_month':source_month,
            'source_article_build_day':report['article_build_day'],'source_table_build_day':report['table_build_day'],
            'source_table_sha256':report['table_sha256'],'availability_convention':'complete following trading month ends at formation close',
            'historical_arrival_verified':False,'historical_members':len(names),'published_member_rows':len(covered),
            'eligible':len(scores),'selected':list(chosen),'published_A_cap_CNY':{c:str(v) for c,v in scores.items()},
            'scores':{c:str(-v) for c,v in scores.items()},'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
