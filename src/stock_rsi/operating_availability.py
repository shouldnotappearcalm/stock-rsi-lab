"""Complete-cohort operating source visibility; no monetary measures or ranks."""
from collections import defaultdict
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_operating as op
from stock_rsi.data import digest
from stock_rsi.industry_catalog import snapshot_catalog, ARCHIVE_RECONSTRUCTED
from stock_rsi.profitability_availability import public_end

SUPPORTED = 'OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA'
FAILURES = ('OPERATING_SOURCE_SCHEMA_UNSUPPORTED', 'COVER_IDENTITY_UNVERIFIED')


def snapshot_availability(documents, case_reader, industry, cohort, as_of, *, mode=op.OBSERVED):
    op.need(mode in (op.OBSERVED, op.RECONSTRUCTED), 'explicit operating source availability mode')
    op.need(type(cohort) in (list, tuple) and len(cohort) == len(set(cohort))
            and all(type(c) is str and re.fullmatch(r'(SH|SZ)[0-9]{6}', c) for c in cohort), 'complete unique canonical cohort')
    clock = op.aware(as_of)
    op.need(clock.astimezone(ZoneInfo('Asia/Shanghai')).year <= 2025, 'operating development source coverage ends in2025')
    catalog = snapshot_catalog(industry, cohort, as_of,
                               mode=op.OBSERVED if mode == op.OBSERVED else ARCHIVE_RECONSTRUCTED)
    sectors = {r['instrument']: r for r in catalog['classifications']}
    visible = defaultdict(list)
    for document in documents:
        public, observed = public_end(document), op.aware(document['captured_at_utc'])
        op.need(public <= observed, 'publication and observed chronology required')
        if clock < (max(public, observed) if mode == op.OBSERVED else public):
            continue
        code = document['instrument']
        if code not in sectors:
            continue
        year = document['effective_fiscal_year']
        op.need(type(year) is int and 1900 <= year < public.year
                and re.fullmatch('[a-f0-9]{64}', document['source_sha256'])
                and re.fullmatch('[0-9]+', document['announcement_id']), 'visible annual source identity required')
        visible[code].append(document)
    rows = []
    for code in sorted(cohort):
        row = {'instrument': code, 'industry_status': sectors[code]['status'],
               'industry_classification_period': '2021Q3', 'current_business_identity_verified': False,
               'financial_version_history_complete': False, 'financial_reporting_compatibility_verified': False,
               'investment_factor_admitted': False}
        candidates = visible[code]
        if not candidates:
            rows.append({**row, 'annual_status': 'NO_VISIBLE_ANNUAL_REPORT'})
            continue
        latest = max((d['effective_fiscal_year'], d['day']) for d in candidates)
        editions = sorted((d for d in candidates if (d['effective_fiscal_year'], d['day']) == latest),
                           key=lambda d: (int(d['announcement_id']), d['capture_key']))
        row.update(latest_fiscal_year=latest[0], latest_publication_day=latest[1],
                   selected_edition_capture_keys=[d['capture_key'] for d in editions])
        if len({d['source_sha256'] for d in editions}) > 1:
            rows.append({**row, 'annual_status': 'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'})
            continue
        document = editions[0]
        case = case_reader(document['capture_key'])
        op.need(case['capture_key'] == document['capture_key'] and case['instrument'] == code
                and case['source_sha256'] == document['source_sha256'] and case['fiscal_year'] == latest[0], 'selected source case identity')
        status = case['status']
        op.need(status in (SUPPORTED, *FAILURES), 'known operating source status required')
        row.update(selected_source_sha256=document['source_sha256'], selected_capture_key=document['capture_key'],
                   selected_source_status=status)
        if status != SUPPORTED:
            op.need(case['operating_report'] is None, 'failed latest source cannot supply monetary report')
            rows.append({**row, 'annual_status': 'LATEST_'+status})
            continue
        report = case['operating_report']
        op.need(type(report) is dict and report['record_id'] == digest({k: v for k, v in report.items() if k != 'record_id'}),
                'selected source report integrity required')
        payload = report['payload']
        rebuilt = op.make_report(report['instrument'], report['report_year'], report['publication_day'], report['observed_at'],
                                  payload['document_sha256'], payload['announcement_id'], payload['parsed'])
        op.need(rebuilt == report and report['instrument'] == code and report['report_year'] == latest[0]
                and report['publication_day'] == document['day'] and op.aware(report['public_day_end_at']) == public_end(document)
                and op.aware(report['observed_at']) == op.aware(document['captured_at_utc'])
                and payload['document_sha256'] == document['source_sha256']
                and payload['announcement_id'] == document['announcement_id'], 'one coherent visible operating source edition')
        rows.append({**row, 'annual_status': 'LATEST_OPERATING_SOURCE_SUPPORTED_NOT_INVESTMENT_ADMITTED',
                     'operating_record_id': report['record_id'],
                     'current_fiscal_end': f'{latest[0]}-12-31', 'lagged_asset_fiscal_end': f'{latest[0]-1}-12-31'})
    return {'as_of': clock.isoformat(), 'visibility_mode': mode, 'cohort_count': len(cohort), 'classifications': rows,
            'source_only_no_monetary_values_exposed': True, 'historical_arrival_verified': False,
            'investment_factor_admitted': False, 'security_ranking_or_portfolio_returns_computed': False}
