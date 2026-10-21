"""One fixed long-only capital combination, with point-in-time interface guards."""
import math
from decimal import Decimal
from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile, choose_development_lead
from stock_rsi.szse_monthly import month_shift

FAMILIES=('szse_value_momentum_equal',)
CONTROLS=('value_leg_control','momentum_leg_control')
START,END='2024-01-02','2025-12-31'


def momentum_12_2(closes):
    if len(closes)!=13:raise ValueError('13 consecutive month-end closes required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in closes):return None
    value=closes[-2]/closes[0]-1
    return value if math.isfinite(value) else None


def merge_equal_sleeves(value_names,momentum_names):
    if any(not names or len(set(names))!=len(names) for names in (value_names,momentum_names)):
        raise ValueError('two nonempty unique sleeves required')
    return {code:math.fsum((.475/len(value_names) if code in value_names else 0.,
                           .475/len(momentum_names) if code in momentum_names else 0.))
            for code in sorted(set(value_names)|set(momentum_names))}


def build_targets(snapshot,memberships,reports,start=START,end=END,*,permitted_end=END):
    if start<START or start>end or end>permitted_end:raise ValueError('value/momentum exceeds explicit date permission')
    targets={name:{} for name in (*FAMILIES,*CONTROLS)};receipts=[]
    for index,day in enumerate(snapshot.calendar):
        if not start<=day.isoformat()<=end:continue
        if index==0:raise ValueError('prior explicit session required')
        previous=snapshot.calendar[index-1]
        if day.strftime('%Y-%m')==previous.strftime('%Y-%m'):continue
        endpoints=complete_month_ends(snapshot.calendar,previous,count=13)
        if previous.strftime('%Y-%m')!=month_shift(day.strftime('%Y-%m'),-1):
            raise ValueError('preceding complete calendar month required')
        source_month=month_shift(day.strftime('%Y-%m'),-2);report=reports[source_month]
        if (report['month']!=source_month or max(report['article_build_day'],report['table_build_day'])>previous.isoformat()):
            raise ValueError('source document too late for complete-following-month convention')
        names=sorted(c for c,spans in memberships.items() if c.startswith(('SZ000','SZ001','SZ002','SZ003'))
                     and any(a<=previous.isoformat()<=b for a,b in spans))
        if len(names)<100:raise ValueError('historical Shenzhen mainboard universe below100')
        covered=[c for c in names if c in report['stocks']]
        if len(covered)<.95*len(names):raise ValueError('published historical source coverage below95percent')
        view=AsOfPrices(snapshot,previous);pes={};momentum={};excluded={}
        for code in covered:
            row=report['stocks'][code]
            if row['reported_special_name'] or row['pe'] is None:
                excluded[code]='SPECIAL_PUBLISHED_NAME_OR_MISSING_PE';continue
            pe=Decimal(row['pe'])
            if not pe.is_finite():raise ValueError('finite published PE required')
            if pe<=0:excluded[code]='NONPOSITIVE_PUBLISHED_PE';continue
            current=[view.value(code,f,previous.isoformat()) for f in ('close','factor','volume')]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in current):
                excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
            score=momentum_12_2([view.value(code,'close',at.isoformat()) for at in endpoints])
            if score is None:excluded[code]='INCOMPLETE_13_MONTH_HISTORY';continue
            pes[code]=pe;momentum[code]=score
        if len(pes)<50 or len(pes)<.5*len(names):raise ValueError('common eligible coverage below50 and50percent')
        value_names=tuple(sorted(pes,key=lambda c:(pes[c],c))[:max(1,len(pes)//10)])
        momentum_names=highest_decile(momentum)
        targets[FAMILIES[0]][day.isoformat()]={'as_of':previous.isoformat(),'weights':merge_equal_sleeves(value_names,momentum_names)}
        for name,selected in zip(CONTROLS,(value_names,momentum_names)):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{c:.95/len(selected) for c in selected}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),'source_month':source_month,
            'source_article_build_day':report['article_build_day'],'source_table_build_day':report['table_build_day'],
            'source_table_sha256':report['table_sha256'],'availability_convention':'complete following trading month ends at formation close',
            'historical_arrival_verified':False,'historical_members':len(names),'published_member_rows':len(covered),
            'eligible':len(pes),'excluded':excluded,'published_pe':{c:str(v) for c,v in pes.items()},'momentum_scores':momentum,
            'month_end_price_dates':[d.isoformat() for d in endpoints],
            'ranking_return_months':[d.strftime('%Y-%m') for d in endpoints[1:-1]],'skipped_ranking_month':endpoints[-1].strftime('%Y-%m'),
            'value_selected':list(value_names),'momentum_selected':list(momentum_names),
            'overlap_names':sorted(set(value_names)&set(momentum_names)),
            'sleeve_capital_budgets':{'value':.475,'momentum':.475},'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
