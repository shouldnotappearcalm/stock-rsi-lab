"""The unchanged expansion policy, with a bounded2026 formation window."""
from collections import Counter
from datetime import datetime,time
from fractions import Fraction
import math
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_assets as assets
from stock_rsi.annual_profitability import amount_CNY,aware
from stock_rsi.data import digest
from stock_rsi.gross_profitability_monthly import minimum_fiscal_year,rank_decile
from stock_rsi.prior_close_orders import AsOfPrices

PRIMARY='low_asset_expansion_decile_conditional'
HIGH_CONTROL='high_asset_expansion_decile_control'
NAMES=(PRIMARY,'eligible_equal_weight',HIGH_CONTROL)
START,END='2024-01-02','2026-10-21'


def need(ok,why):
    if not ok:raise ValueError(why)


def build_targets(snapshot,memberships,cohort,source_views,case_reader,start=START,end=END,*,on_formation=None):
    need(START<=start<=end<=END,'asset-expansion horizon ends at fixed2026 source cutoff')
    need(type(cohort) in (list,tuple) and len(cohort)==len(set(cohort)) and cohort
         and all(type(c) is str and re.fullmatch(r'(?:SH60|SZ00)[0-9]{4}',c) for c in cohort),'unique full initial mainboard source cohort')
    targets={name:{} for name in NAMES};receipts=[]
    for index,execution in enumerate(snapshot.calendar):
        if not start<=execution.isoformat()<=end:continue
        need(index>0,'preceding actual exchange session required')
        previous=snapshot.calendar[index-1]
        if previous.strftime('%Y-%m')==execution.strftime('%Y-%m'):continue
        clock=datetime.combine(previous,time(15,5),ZoneInfo('Asia/Shanghai'))
        view=source_views[execution.isoformat()]
        need(aware(view['as_of'])==clock and view['visibility_mode']==assets.RECONSTRUCTED
             and view['cohort_count']==len(cohort),'exact formation metadata clock/mode/cohort')
        rows=view['classifications']
        need(len(rows)==len(cohort) and sorted(r['instrument'] for r in rows)==sorted(cohort),'every source issuer exactly once')
        active={c for c in cohort if any(a<=previous.isoformat()<=b for a,b in memberships.get(c,()))}
        prices=AsOfPrices(snapshot,previous);scores={};evidence={};admission=[]
        for row in rows:
            code=row['instrument'];reason=None
            if code not in active:reason='NOT_IN_FORMATION_MEMBERSHIP'
            elif row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif 'selected_capture_key' not in row:
                need(row['annual_status'] in ('NO_VISIBLE_ANNUAL_REPORT','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'),'explicit unresolved latest metadata state')
                reason=row['annual_status']
            elif row['latest_fiscal_year']<minimum_fiscal_year(previous.isoformat()):reason='STALE_ANNUAL_ASSETS'
            if reason is not None:
                admission.append({'instrument':code,'reason':reason});continue
            case=case_reader(row['selected_capture_key'])
            need(case['capture_key']==row['selected_capture_key'] and case['instrument']==code
                 and case['fiscal_year']==row['latest_fiscal_year'] and case['source_sha256']==row['selected_source_sha256'],
                 'selected latest asset-case identity')
            if case['status']!='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA':
                need(case['status'] in ('ASSET_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED')
                     and case['asset_report'] is None,'failed latest asset source cannot supply numeric values')
                admission.append({'instrument':code,'reason':'LATEST_'+case['status']});continue
            need(case['asset_report'] is not None,'supported current asset report required')
            visible=assets.visible_reports([case['asset_report']],clock.isoformat(),mode=assets.RECONSTRUCTED)['reports']
            need(len(visible)==1,'selected asset report must be visible before payload use')
            report=visible[0];year=row['latest_fiscal_year'];current=f'{year}-12-31';prior=f'{year-1}-12-31'
            need(report['instrument']==code and report['report_year']==year and report['publication_day']==row['latest_publication_day']
                 and report['payload']['document_sha256']==row['selected_source_sha256']
                 and report['payload']['scope']=='CONSOLIDATED','one coherent latest annual edition')
            balances=report['payload']['balances']
            need(current in balances and set(balances)<={current,prior},'bounded current/explicit prior asset dates')
            if prior not in balances:
                admission.append({'instrument':code,'reason':'LATEST_HAS_NO_EXPLICIT_PRIOR_YEAR_END'});continue
            values={}
            for column,period in enumerate((current,prior)):
                cell=balances[period]
                need(cell['fiscal_end']==period and cell['column_index']==column and cell['statement']=='合并资产负债表'
                     and cell['row_text_sha256']==digest(cell['row_text']),'current/prior literal asset-column identity')
                value=Fraction(amount_CNY(cell['literal'],cell['unit']))
                need(value>0 and value==Fraction(cell['value_CNY']),'positive exact source asset amounts')
                values[period]=value
            quotes=[prices.value(code,f,previous.isoformat()) for f in ('close','volume','factor')]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in quotes):
                admission.append({'instrument':code,'reason':'NO_POSITIVE_FORMATION_QUOTE'});continue
            expansion=values[current]/values[prior]-1;scores[code]=expansion
            evidence[code]={'record_id':report['record_id'],'source_sha256':row['selected_source_sha256'],
                'capture_key':row['selected_capture_key'],'report_year':year,'current_fiscal_end':current,'prior_fiscal_end':prior,
                'publication_day':report['publication_day'],'expansion_fraction':str(expansion)}
            admission.append({'instrument':code,'reason':'CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'})
        need(len(scores)>=100,'paired-assets/price coverage below fixed100-name diversification guard')
        choices={PRIMARY:rank_decile(scores,lowest=True),'eligible_equal_weight':tuple(sorted(scores)),
                 HIGH_CONTROL:rank_decile(scores)}
        for name,selected in choices.items():
            targets[name][execution.isoformat()]={'as_of':previous.isoformat(),'weights':{c:.95/len(selected) for c in selected}}
        receipt={'execution_session':execution.isoformat(),'formation_asof':previous.isoformat(),'source_as_of':view['as_of'],
            'initial_source_cohort':len(cohort),'formation_members':len(active),'eligible':len(scores),
            'eligible_fraction_of_active_initial_cohort':len(scores)/len(active),'minimum_fiscal_year':minimum_fiscal_year(previous.isoformat()),
            'cohort_admission':admission,'admission_counts':dict(Counter(r['reason'] for r in admission)),
            'ranked_source':evidence,'selections':choices,'latest_factor_price_read':prices.latest_read.isoformat(),
            'metadata_selection_precedes_GP_numeric_status_filter':True,'source_availability':assets.RECONSTRUCTED,
            'classification_vintage':'2021Q3','historical_arrival_verified':False,'current_business_identity_verified':False,
            'financial_reporting_compatibility_verified':False,'investment_factor_admitted':False}
        receipts.append(receipt)
        if on_formation is not None:on_formation(execution.isoformat(),{n:targets[n][execution.isoformat()] for n in NAMES},receipt)
    return targets,receipts
