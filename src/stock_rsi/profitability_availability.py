"""Cohort-complete annual-source availability; no ranks or investment admission."""
from collections import defaultdict
from datetime import datetime, time
import re
from zoneinfo import ZoneInfo

from stock_rsi.annual_profitability import (
    OBSERVED, RECONSTRUCTED, aware, snapshot_observations,
)
from stock_rsi.industry_catalog import (
    ARCHIVE_RECONSTRUCTED, snapshot_catalog,
)

SUPPORTED = 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW'
FAILURES = ('SOURCE_SCHEMA_UNSUPPORTED', 'COVER_IDENTITY_UNVERIFIED')


def need(ok, why):
    if not ok:
        raise ValueError(why)


def public_end(document):
    day = datetime.strptime(document['day'], '%Y-%m-%d').date()
    need(day.isoformat() == document['day'], 'canonical publication day')
    return datetime.combine(day, time.max, ZoneInfo('Asia/Shanghai'))


def snapshot_availability(documents, case_reader, industry, cohort, as_of, *, mode=OBSERVED):
    """Only read selected visible case payloads; newer failures never fall back.

    Fiscal year is ordered before publication day: a late old-year reissue does
    not displace an available more recent fiscal year. Conflicting same-day
    latest editions remain ambiguous. Identical PDF bytes are deduplicated with
    the smallest numeric announcement ID as the deterministic source witness.
    """
    need(mode in (OBSERVED, RECONSTRUCTED), 'explicit availability mode')
    need(type(cohort) in (list, tuple) and len(set(cohort)) == len(cohort)
         and all(type(c) is str and re.fullmatch(r'(SH|SZ)[0-9]{6}', c) for c in cohort),
         'unique canonical complete cohort')
    clock = aware(as_of)
    need(clock.astimezone(ZoneInfo('Asia/Shanghai')).year <= 2025,
         'source availability development ends in2025')
    classifications = snapshot_catalog(industry, cohort, as_of,
        mode=OBSERVED if mode == OBSERVED else ARCHIVE_RECONSTRUCTED)
    sectors = {row['instrument']: row for row in classifications['classifications']}
    visible = defaultdict(list)
    for document in documents:
        public, observed = public_end(document), aware(document['captured_at_utc'])
        need(public <= observed, 'publication/capture chronology')
        if clock < (max(public, observed) if mode == OBSERVED else public):
            continue
        # Identity/fiscal year/case lookup are deliberately after visibility.
        code = document['instrument']
        if code not in sectors:
            continue
        year = document['effective_fiscal_year']
        need(type(year) is int and 1900 <= year < public.year
             and re.fullmatch('[a-f0-9]{64}', document['source_sha256'])
             and re.fullmatch('[0-9]+', document['announcement_id']), 'visible annual source identity')
        visible[code].append(document)
    rows = []
    for code in sorted(cohort):
        row = {'instrument': code, 'industry_status': sectors[code]['status'],
               'industry_classification_period': '2021Q3',
               'current_business_identity_verified': False, 'financial_version_history_complete': False,
               'financial_reporting_compatibility_verified': False, 'investment_factor_admitted': False}
        candidates = visible[code]
        if not candidates:
            rows.append({**row, 'annual_status': 'NO_VISIBLE_ANNUAL_REPORT'})
            continue
        latest = max((d['effective_fiscal_year'], d['day']) for d in candidates)
        latest_docs = sorted((d for d in candidates if (d['effective_fiscal_year'], d['day']) == latest),
                             key=lambda d: (int(d['announcement_id']), d['capture_key']))
        row.update(latest_fiscal_year=latest[0], latest_publication_day=latest[1],
                   selected_edition_capture_keys=[d['capture_key'] for d in latest_docs])
        if len({d['source_sha256'] for d in latest_docs}) > 1:
            rows.append({**row, 'annual_status': 'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'})
            continue
        document = latest_docs[0]
        case = case_reader(document['capture_key'])
        need(case['capture_key'] == document['capture_key'] and case['instrument'] == code
             and case['source_sha256'] == document['source_sha256']
             and case['fiscal_year'] == latest[0], 'selected source/case identity')
        status = case['status']
        need(status in (SUPPORTED, *FAILURES), 'known selected source status')
        row.update(selected_source_sha256=document['source_sha256'],
                   selected_capture_key=document['capture_key'], selected_source_status=status)
        if status != SUPPORTED:
            need(not case['source_observations'], 'failed case cannot supply observations')
            rows.append({**row, 'annual_status': 'LATEST_' + status})
            continue
        current = [o for o in case['source_observations'] if o['fiscal_end'] == f'{latest[0]}-12-31']
        need(len(current) == 1, 'one current annual observation; no comparative fallback')
        observation = current[0]
        need(observation['instrument'] == code and observation['publication_day'] == document['day']
             and aware(observation['observed_at']) == aware(document['captured_at_utc'])
             and observation['payload']['column_role'] == 'CURRENT'
             and observation['payload']['document_sha256'] == document['source_sha256']
             and observation['payload']['announcement_id'] == document['announcement_id'],
             'one coherent current-year edition')
        source = snapshot_observations([observation], as_of, mode=mode)
        need(len(source['records']) == 1, 'selected current source visible at the same clock')
        rows.append({**row, 'annual_status': 'LATEST_CURRENT_SOURCE_SUPPORTED_NOT_ADMITTED',
                     'current_observation': source['records'][0]})
    return {'as_of': clock.isoformat(), 'visibility_mode': mode, 'cohort_count': len(cohort),
            'classifications': rows, 'historical_arrival_verified': False,
            'investment_factor_admitted': False, 'security_ranking_or_portfolio_returns_computed': False}
