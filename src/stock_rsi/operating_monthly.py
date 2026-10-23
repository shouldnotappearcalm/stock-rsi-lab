"""One current operating-profitability candidate with complete source admissions."""
from collections import Counter
from datetime import datetime,time
from fractions import Fraction
import math
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_operating as op, operating_factor as factor, operating_source_bridge as bridge
from stock_rsi.gross_profitability_monthly import minimum_fiscal_year,rank_decile
from stock_rsi.prior_close_orders import AsOfPrices

PRIMARY='operating_profit_prior_assets_top_decile_conditional'
LOW_CONTROL='operating_profit_prior_assets_bottom_decile_control'
NAMES=(PRIMARY,'eligible_equal_weight',LOW_CONTROL)
START,END='2024-01-02','2025-12-31'


def build_targets(snapshot,memberships,cohort,source_views,documents,case_reader,legacy_reader,approved_ids,start=START,end=END,*,on_formation=None):
    op.need(START<=start<=end<=END,'operating development ends in2025')
    op.need(type(cohort) in (list,tuple) and len(set(cohort))==len(cohort) and cohort
        and all(type(c) is str and re.fullmatch(r'(?:SH60|SZ00)[0-9]{4}',c) for c in cohort),'unique complete mainboard source cohort')
    targets={name:{} for name in NAMES};receipts=[]
    for index,execution in enumerate(snapshot.calendar):
        if not start<=execution.isoformat()<=end:continue
        op.need(index>0,'preceding actual exchange session required');previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==execution.strftime('%Y-%m'):continue
        clock=datetime.combine(previous,time(15,5),ZoneInfo('Asia/Shanghai'));view=source_views[execution.isoformat()]
        op.need(op.aware(view['as_of'])==clock and view['visibility_mode']==op.RECONSTRUCTED and view['cohort_count']==len(cohort),'exact formation metadata clock/mode/cohort')
        rows=view['classifications'];op.need(len(rows)==len(cohort) and sorted(r['instrument'] for r in rows)==sorted(cohort),'complete original issuer rows')
        active={c for c in cohort if any(a<=previous.isoformat()<=b for a,b in memberships.get(c,()))}
        prices=AsOfPrices(snapshot,previous);scores={};evidence={};admission=[]
        for row in rows:
            code=row['instrument'];reason=None
            if code not in active:reason='NOT_IN_FORMATION_MEMBERSHIP'
            elif row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif 'selected_capture_key' not in row:
                op.need(row['annual_status'] in ('NO_VISIBLE_ANNUAL_REPORT','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'),'explicit unresolved latest source');reason=row['annual_status']
            elif row['latest_fiscal_year']<minimum_fiscal_year(previous.isoformat()):reason='STALE_ANNUAL_SOURCE'
            elif row['effective_source_status']==bridge.STILL_UNSUPPORTED:reason='LATEST_STILL_UNSUPPORTED'
            if reason is not None:admission.append({'instrument':code,'reason':reason});continue
            key=row['selected_capture_key'];doc=documents[key]
            # Check visibility from metadata before source readers can touch a payload.
            observation=factor.source_observation(doc,case_reader,legacy_reader,approved_ids,clock.isoformat(),mode=op.RECONSTRUCTED)
            op.need(observation is not None and doc['instrument']==code and doc['effective_fiscal_year']==row['latest_fiscal_year']
                and doc['source_sha256']==row['selected_source_sha256'] and doc['day']==row['latest_publication_day']
                and observation['record_id']==row['effective_record_id'],'selected visible latest approved operating source')
            quotes=[prices.value(code,f,previous.isoformat()) for f in ('close','volume','factor')]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in quotes):
                admission.append({'instrument':code,'reason':'NO_POSITIVE_FORMATION_QUOTE'});continue
            scores[code]=Fraction(observation['score_fraction']);evidence[code]=observation
            admission.append({'instrument':code,'reason':'CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'})
        op.need(len(scores)>=100,'operating/price coverage below fixed100-name diversification guard')
        choices={PRIMARY:rank_decile(scores),'eligible_equal_weight':tuple(sorted(scores)),LOW_CONTROL:rank_decile(scores,lowest=True)}
        for name,selected in choices.items():targets[name][execution.isoformat()]={'as_of':previous.isoformat(),'weights':{c:.95/len(selected) for c in selected}}
        receipt={'execution_session':execution.isoformat(),'formation_asof':previous.isoformat(),'source_as_of':view['as_of'],
            'initial_source_cohort':len(cohort),'formation_members':len(active),'eligible':len(scores),
            'eligible_fraction_of_active_initial_cohort':len(scores)/len(active),'minimum_fiscal_year':minimum_fiscal_year(previous.isoformat()),
            'cohort_admission':admission,'admission_counts':dict(Counter(r['reason'] for r in admission)),
            'ranked_source':evidence,'selections':choices,'latest_factor_price_read':prices.latest_read.isoformat(),
            'source_availability':op.RECONSTRUCTED,'classification_vintage':'2021Q3','historical_arrival_verified':False,
            'current_business_identity_verified':False,'financial_reporting_compatibility_verified':False,'investment_factor_admitted':False}
        receipts.append(receipt)
        if on_formation is not None:on_formation(execution.isoformat(),{n:targets[n][execution.isoformat()] for n in NAMES},receipt)
    return targets,receipts
