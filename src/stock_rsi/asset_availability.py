"""Full-cohort asset-edition visibility; no monetary values, ranks or fallback."""
from collections import defaultdict
from datetime import datetime,time
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_assets as assets
from stock_rsi.annual_profitability import aware,OBSERVED,RECONSTRUCTED
from stock_rsi.industry_catalog import ARCHIVE_RECONSTRUCTED,snapshot_catalog

SUPPORTED='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA'
FAILURES=('ASSET_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED','SOURCE_PDF_EXTRACTION_UNSUPPORTED')
CUTOFF='2026-10-21T15:05:00+08:00'


def need(ok,why):
    if not ok:raise ValueError(why)


def public_end(document):
    day=datetime.strptime(document['day'],'%Y-%m-%d').date()
    need(day.isoformat()==document['day'],'canonical publication day')
    return datetime.combine(day,time.max,ZoneInfo('Asia/Shanghai'))


def snapshot_availability(documents,case_reader,industry,cohort,as_of,*,mode=OBSERVED):
    need(mode in (OBSERVED,RECONSTRUCTED),'explicit asset availability mode')
    need(type(cohort) in (list,tuple) and len(cohort)==len(set(cohort))
        and all(type(c) is str and re.fullmatch(r'(SH|SZ)[0-9]{6}',c) for c in cohort),'unique canonical complete cohort')
    clock=aware(as_of);need(clock<=aware(CUTOFF),'asset availability ends at the fixed2026 source cutoff')
    catalog=snapshot_catalog(industry,cohort,as_of,mode=OBSERVED if mode==OBSERVED else ARCHIVE_RECONSTRUCTED)
    sectors={r['instrument']:r for r in catalog['classifications']};visible=defaultdict(list)
    for doc in documents:
        public,observed=public_end(doc),aware(doc['captured_at_utc'])
        need(public<=observed,'publication/capture chronology')
        if clock<(max(public,observed) if mode==OBSERVED else public):continue
        # No annual identity or case payload is inspected before visibility.
        code=doc['instrument']
        if code not in sectors:continue
        year=doc['effective_fiscal_year']
        need(type(year) is int and 1900<=year<public.year
            and re.fullmatch('[a-f0-9]{64}',doc['source_sha256'])
            and re.fullmatch('[0-9]+',doc['announcement_id']),'visible annual source identity')
        visible[code].append(doc)
    rows=[]
    for code in sorted(cohort):
        row={'instrument':code,'industry_status':sectors[code]['status'],'industry_classification_period':'2021Q3',
            'current_business_identity_verified':False,'financial_version_history_complete':False,
            'financial_reporting_compatibility_verified':False,'investment_factor_admitted':False}
        candidates=visible[code]
        if not candidates:
            rows.append({**row,'annual_status':'NO_VISIBLE_ANNUAL_REPORT'});continue
        latest=max((d['effective_fiscal_year'],d['day']) for d in candidates)
        editions=sorted((d for d in candidates if (d['effective_fiscal_year'],d['day'])==latest),
            key=lambda d:(int(d['announcement_id']),d['capture_key']))
        row.update(latest_fiscal_year=latest[0],latest_publication_day=latest[1],
            selected_edition_capture_keys=[d['capture_key'] for d in editions])
        if len({d['source_sha256'] for d in editions})>1:
            rows.append({**row,'annual_status':'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'});continue
        doc=editions[0];case=case_reader(doc['capture_key'])
        need(case['capture_key']==doc['capture_key'] and case['instrument']==code
            and case['source_sha256']==doc['source_sha256']
            and case.get('fiscal_year',case.get('metadata_fiscal_year'))==latest[0],'selected asset source/case identity')
        status=case['status'];need(status in (SUPPORTED,*FAILURES),'known selected asset source status')
        row.update(selected_source_sha256=doc['source_sha256'],selected_capture_key=doc['capture_key'],selected_source_status=status)
        if status!=SUPPORTED:
            need(case['asset_report'] is None,'failed latest case cannot supply asset values')
            rows.append({**row,'annual_status':'LATEST_'+status});continue
        report=case['asset_report'];need(type(report) is dict,'selected supported asset report')
        need(aware(report['public_day_end_at'])==public_end(doc) and aware(report['observed_at'])==aware(doc['captured_at_utc']),
            'same publication and actual observed clocks')
        source=assets.visible_reports([report],as_of,mode=mode)
        need(len(source['reports'])==1,'selected supported report visible at the same clock')
        report=source['reports'][0]
        need(report['instrument']==code and report['report_year']==latest[0] and report['publication_day']==doc['day']
            and report['payload']['document_sha256']==doc['source_sha256']
            and report['payload']['announcement_id']==doc['announcement_id'] and report['payload']['scope']=='CONSOLIDATED',
            'one coherent selected asset edition')
        current,prior=f'{latest[0]}-12-31',f'{latest[0]-1}-12-31';periods=set(report['payload']['balances'])
        need(current in periods and periods<={current,prior},'current asset and explicit adjacent year ends only')
        rows.append({**row,'annual_status':'LATEST_ASSET_SOURCE_SUPPORTED_NOT_INVESTMENT_ADMITTED',
            'asset_record_id':report['record_id'],'balance_periods':sorted(periods),'has_explicit_prior_year_end':prior in periods})
    return {'as_of':clock.isoformat(),'visibility_mode':mode,'cohort_count':len(cohort),'classifications':rows,
        'historical_arrival_verified':False,'investment_factor_admitted':False,
        'source_only_no_asset_amounts_exposed':True,'security_ranking_or_portfolio_returns_computed':False}
