"""One pre-2026 value candidate using delayed exchange-published PE ranks."""
import math

from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import highest_decile, choose_development_lead
from stock_rsi.szse_monthly import month_shift

FAMILIES=('szse_monthly_low_pe',)
START,END='2024-01-02','2025-12-31'


def build_targets(snapshot,memberships,reports,start=START,end=END,*,permitted_end=END):
    if start<START or start>end or end>permitted_end:raise ValueError('published-value exceeds explicit date permission')
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
            if r['reported_special_name'] or r['pe'] is None:continue
            pe=float(r['pe'])
            if not math.isfinite(pe):raise ValueError('finite published PE required')
            if pe<=0:continue
            volume=view.value(code,'volume',previous.isoformat());factor=view.value(code,'factor',previous.isoformat())
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (volume,factor)):continue
            scores[code]=1/pe
        if len(scores)<50 or len(scores)<.5*len(names):raise ValueError('rankable positive-PE coverage below registered level')
        chosen=highest_decile(scores)
        for name,selected in ((FAMILIES[0],chosen),('eligible_equal_weight',sorted(scores))):
            targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{code:.95/len(selected) for code in selected}}
        receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),'source_month':source_month,
            'source_article_build_day':report['article_build_day'],'source_table_build_day':report['table_build_day'],
            'source_table_sha256':report['table_sha256'],'availability_convention':'complete following trading month ends at formation close',
            'historical_arrival_verified':False,'historical_members':len(names),'published_member_rows':len(covered),
            'eligible':len(scores),'selected':list(chosen),'scores':scores,'latest_factor_price_read':view.latest_read.isoformat()})
    return targets,receipts
