"""One fixed market-only adaptation of residual momentum, not FF3 replication.

Fit beta with an intercept on36complete monthly returns through formation.
Rank mean(R-beta*M)/sample_sd over the11prior months, skipping the latest.
The fitted intercept is diagnostic only and is not subtracted from that rank.
"""
import math
import statistics
from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile,choose_development_lead

FAMILIES=('market_residual_mom36_12_2',)
CONTROL='total_mom12_2_control'
START,END='2024-01-02','2025-12-31'
MARKET='SH000905'


def residual_score(stock_closes,market_closes):
    if len(stock_closes)!=37 or len(market_closes)!=37:
        raise ValueError('37consecutive monthly closes for36regression returns required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (*stock_closes,*market_closes)):
        return None
    ys=[b/a-1 for a,b in zip(stock_closes,stock_closes[1:])]
    xs=[b/a-1 for a,b in zip(market_closes,market_closes[1:])]
    if any(not math.isfinite(v) for v in (*xs,*ys)):return None
    xbar=statistics.mean(xs);ybar=statistics.mean(ys)
    denominator=math.fsum((x-xbar)**2 for x in xs)
    if not math.isfinite(denominator) or denominator<=1e-24:return None
    beta=math.fsum((x-xbar)*(y-ybar) for x,y in zip(xs,ys))/denominator
    alpha=ybar-beta*xbar
    adjusted=[y-beta*x for x,y in zip(xs[-12:-1],ys[-12:-1])]
    if any(not math.isfinite(v) for v in (beta,alpha,*adjusted)):return None
    deviation=statistics.stdev(adjusted)
    if not math.isfinite(deviation) or deviation<=1e-12:return None
    score=statistics.mean(adjusted)/deviation
    if not math.isfinite(score):return None
    return {'score':score,'beta':beta,'alpha':alpha,'rank_adjusted_returns':adjusted,
        'control_total_return_score':stock_closes[-2]/stock_closes[-13]-1}


def build_targets(snapshot,memberships,start=START,end=END):
    if start<START or start>end or end>END:raise ValueError('residual momentum development cannot read beyond2025')
    targets={name:{} for name in (*FAMILIES,'eligible_equal_weight',CONTROL)};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end:continue
        if index==0:raise ValueError('preceding explicit exchange session required')
        previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==day.strftime('%Y-%m'):continue
        endpoints=complete_month_ends(snapshot.calendar,previous,count=37)
        expected_month=(day.year,day.month-1) if day.month>1 else (day.year-1,12)
        if (previous.year,previous.month)!=expected_month:raise ValueError('preceding exchange month missing')
        view=AsOfPrices(snapshot,previous)
        market=[view.value(MARKET,'close',d.isoformat()) for d in endpoints]
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in market):
            raise ValueError('complete observed market month-end history required')
        names=sorted(c for c,spans in memberships.items() if any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<200:raise ValueError('historical CSI500 main-board universe unexpectedly small')
        scores={};total_scores={};coefficients={};excluded={}
        for code in names:
            current=[view.value(code,f,previous.isoformat()) for f in ('factor','volume','close')]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in current):
                excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
            value=residual_score([view.value(code,'close',d.isoformat()) for d in endpoints],market)
            if value is None:excluded[code]='INCOMPLETE_OR_DEGENERATE_36_MONTH_HISTORY'
            else:
                scores[code]=value['score'];total_scores[code]=value['control_total_return_score'];coefficients[code]={'beta':value['beta'],'alpha':value['alpha']}
        if len(scores)<100 or len(scores)<.8*len(names):raise ValueError('36month factor coverage below registered80% admission')
        selected=highest_decile(scores);control_selected=highest_decile(total_scores)
        for name,chosen in ((FAMILIES[0],selected),('eligible_equal_weight',sorted(scores)),(CONTROL,control_selected)):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(chosen) for code in chosen}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),
            'market_instrument':MARKET,'regression_begin_close':endpoints[0].isoformat(),
            'regression_return_months':[d.strftime('%Y-%m') for d in endpoints[1:]],
            'ranking_return_months':[d.strftime('%Y-%m') for d in endpoints[-12:-1]],
            'skipped_ranking_month':endpoints[-1].strftime('%Y-%m'),'regression_includes_skipped_ranking_month':True,
            'alpha_subtracted_from_ranking_return':False,'historical_members':len(names),'eligible':len(scores),
            'excluded':excluded,'selected':list(selected),'scores':scores,'regression_coefficients':coefficients,
            'control_total_return_scores':total_scores,'control_selected':list(control_selected),
            'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
