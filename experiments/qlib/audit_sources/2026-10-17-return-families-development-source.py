"""Three pre-2026 literature hypotheses, sharing complete five-year histories.

This is a long-only CSI500 engineering adaptation, not a paper replication.
Seasonal cross-sectional demeaning is rank-invariant on common exact dates.
"""
import math
import statistics

from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices


FAMILIES=('contrarian20','contrarian60_12','seasonal5')
START,END='2024-01-02','2025-12-31'


def return_scores(monthly,months,daily,target_month):
    if len(monthly)!=61 or len(months)!=61 or len(daily)!=21 or target_month not in range(1,13):
        raise ValueError('complete 60 monthly/20 daily returns and calendar month required')
    if any(type(m) is not int or m not in range(1,13) for m in months):
        raise ValueError('explicit monthly calendar required')
    if any(b!=a%12+1 for a,b in zip(months,months[1:])):
        raise ValueError('consecutive monthly calendar required')
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in (*monthly,*daily)):
        return None
    seasonal=[b/a-1 for a,b,month in zip(monthly,monthly[1:],months[1:]) if month==target_month]
    if len(seasonal)!=5:raise ValueError('exactly five historical same-calendar-month returns required')
    scores={'contrarian20':-(daily[-1]/daily[0]-1),
            'contrarian60_12':-(monthly[-13]/monthly[0]-1),'seasonal5':statistics.mean(seasonal)}
    return scores if all(math.isfinite(x) for x in scores.values()) else None


def highest_decile(scores):
    if not scores or any(not math.isfinite(x) for x in scores.values()):raise ValueError('finite scores required')
    return tuple(sorted(scores,key=lambda code:(-scores[code],code))[:max(1,len(scores)//10)])


def build_targets(snapshot,memberships,start=START,end=END):
    if start> end or start<START or end>END:raise ValueError('target generation exceeds pre-2026 research cap')
    targets={name:{} for name in (*FAMILIES,'eligible_equal_weight')};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end or index<21:continue
        previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==day.strftime('%Y-%m'):continue
        endpoints=complete_month_ends(snapshot.calendar,previous,count=61)
        days=snapshot.calendar[index-21:index];view=AsOfPrices(snapshot,previous)
        names=sorted(code for code,spans in memberships.items() if any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<200:raise ValueError('historical mainland-board membership unexpectedly small')
        scores={}
        for code in names:
            volume=view.value(code,'volume',previous.isoformat());factor=view.value(code,'factor',previous.isoformat())
            if volume is None or factor is None or volume<=0 or factor<=0:continue
            monthly=[view.value(code,'close',at.isoformat()) for at in endpoints]
            daily=[view.value(code,'close',at.isoformat()) for at in days]
            value=return_scores(monthly,[at.month for at in endpoints],daily,day.month)
            if value is not None:scores[code]=value
        if len(scores)<100 or len(scores)<.5*len(names):raise ValueError('complete common history coverage below registered admission')
        selections={name:highest_decile({code:s[name] for code,s in scores.items()}) for name in FAMILIES}
        selections['eligible_equal_weight']=tuple(sorted(scores))
        for name,chosen in selections.items():
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(chosen) for code in chosen}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),
            'monthly_begin':endpoints[0].isoformat(),'monthly_end':endpoints[-1].isoformat(),
            'daily_begin':days[0].isoformat(),'daily_end':days[-1].isoformat(),'seasonal_prediction_month':day.month,
            'historical_members':len(names),'common_eligible':len(scores),'selections':selections,'scores':scores,
            'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts


def choose_development_lead(results):
    eligible=[]
    for name,row in results.items():
        values=[row[key] for key in ('2024_return_pct','2025_return_pct','average_exposure_pct','turnover_x_initial')]
        if (all(math.isfinite(x) for x in values) and min(values[:2])>0 and values[2]>=90
                and row['unverified_held_marks']==0):eligible.append((name,row))
    eligible.sort(key=lambda pair:(-min(pair[1]['2024_return_pct'],pair[1]['2025_return_pct']),
                                    pair[1]['turnover_x_initial'],pair[0]))
    return eligible[0][0] if eligible else None
