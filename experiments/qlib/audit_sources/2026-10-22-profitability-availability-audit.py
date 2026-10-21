"""Separate monthly-source join checker. No production-selector imports."""
import argparse
from collections import Counter
from datetime import datetime, time, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def inventory(folder):
    return {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def main():
    p = argparse.ArgumentParser()
    for name in ('repo-root', 'source-root', 'membership-file', 'request',
                 'expected-request-sha256', 'run-dir', 'output'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    root, base, membership, request, run, output = (Path(getattr(a, k)).resolve() for k in
        ('repo_root', 'source_root', 'membership_file', 'request', 'run_dir', 'output'))
    need(not output.exists() and not output.is_relative_to(run), 'fresh external audit output')
    need(sha(request) == a.expected_request_sha256, 'frozen monthly-source request')
    req = read(request)
    fixed = base / 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json'
    original = {d['capture_key']: d for d in read(fixed)}
    old = base / 'cninfo-csi500-reports-20261017'
    aliases = {'membership_intervals': membership, 'metadata_manifest': old / 'manifest.json',
               'metadata_plan': old / 'plan.json', 'PDF_document_records': fixed,
               'inventory_code': root / 'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    paths = {'frozen_source_request': request}
    for key in req['input_sha256']:
        if key == 'membership':
            path = membership
        else:
            prefix, name = key.split('/', 1)
            if prefix == 'repo': path = root / name
            elif prefix == 'source': path = base / name
            else:
                need(prefix == 'catalog', 'known source namespace')
                if name in aliases: path = aliases[name]
                elif name.startswith('metadata/'): path = old / 'codes' / (name[9:] + '.json')
                else:
                    need(name.startswith('PDF/') and name[4:] in original, 'known original alias')
                    path = base / original[name[4:]]['source_path']
        paths[key] = path
    expected = {**req['input_sha256'], 'frozen_source_request': a.expected_request_sha256}
    for key, path in paths.items():
        need(sha(path) == expected[key], 'input before: ' + key)
    outputs = inventory(run)
    expected_files = {q['execution_session'] + '-' + mode + '.json' for q in req['formations'] for mode in req['modes']}
    expected_files.update(('input-before.json', 'input-postcheck.json', 'terminal.json', 'summary.json'))
    need(set(outputs) == expected_files and len(outputs) == 52, 'complete52-file source output')
    need(read(run / 'input-before.json') == expected, 'complete initial input manifest')
    post, terminal, summary = (read(run / n) for n in ('input-postcheck.json', 'terminal.json', 'summary.json'))
    need(post['all_inputs_unchanged'] and not post['mismatches'] and post['count'] == len(paths)
         and terminal['pending_query_count'] == 0 and terminal['original_error'] is None
         and not terminal['persistence_errors'], 'complete successful source termination')
    v7 = read(root / 'experiments/qlib/profitability-all1236-v7-request.json')
    cases = read(base / 'gross-profitability-all1236-header-v7-20261022/case_results.json')
    industry = read(base / 'gross-profitability-2021Q3-industry-catalog-v1-20261022/catalog.json')
    need(req['documents'] == v7['documents'] and len(req['documents']) == len(cases) == 1236, 'all source editions')
    sectors = {r['stock_code']: r for r in industry['records']}
    metadata_by_code = {}
    for doc in req['documents']:
        publication = datetime.combine(datetime.strptime(doc['day'], '%Y-%m-%d').date(), time.max, ZoneInfo('Asia/Shanghai'))
        observed = datetime.fromisoformat(doc['captured_at_utc'])
        metadata_by_code.setdefault(doc['instrument'], []).append((publication, observed, doc))
    cohort = sorted({c for c, start, end in (line.split() for line in membership.read_text().splitlines())
                     if start <= '2024-01-02' <= end and c.startswith(('SH60', 'SZ00'))})
    need(cohort == req['cohort'] and len(cohort) == 394, 'independent full dated cohort')
    days = (base / 'qlib-enhanced-dev/calendars/day.txt').read_text().splitlines()
    expected_formations = [{'execution_session': b, 'as_of': a + 'T15:05:00+08:00'} for a, b in zip(days, days[1:])
                           if '2024-01-02' <= b <= '2025-12-31' and a[:7] != b[:7]]
    need(req['formations'] == expected_formations and len(expected_formations) == 24, 'explicit prior-session24 transitions')
    records_checked, supported_checked, queries = 0, 0, []
    for formation in expected_formations:
        clock = datetime.fromisoformat(formation['as_of']).astimezone(timezone.utc)
        for mode in req['modes']:
            name = formation['execution_session'] + '-' + mode + '.json'
            snap = read(run / name)
            need(snap['as_of'] == clock.isoformat() and snap['visibility_mode'] == mode
                 and snap['cohort_count'] == 394, 'query clock/mode/cohort')
            rows = snap['classifications']
            need([r['instrument'] for r in rows] == cohort, 'all394 rows no future parse-success subset')
            for row in rows:
                code = row['instrument']
                candidates = []
                for publication, observed, doc in metadata_by_code.get(code, []):
                    if clock >= (max(publication, observed) if mode == 'OBSERVED' else publication):
                        candidates.append(doc)
                industry_visible = clock >= max(datetime.fromisoformat(industry['public_content_available_by']),
                    datetime.fromisoformat(industry['observed_at'])) if mode == 'OBSERVED' else clock >= datetime.fromisoformat(industry['public_content_available_by'])
                sector = sectors.get(code[2:])
                expected_sector = ('NOT_AVAILABLE_AT_CLOCK' if not industry_visible else
                    'NOT_IN_SOURCE_VINTAGE' if sector is None else
                    'FINANCIAL_IN_SOURCE_VINTAGE' if sector['sector_code'] == 'J' else 'NONFINANCIAL_IN_SOURCE_VINTAGE')
                need(row['industry_status'] == expected_sector and row['industry_classification_period'] == '2021Q3', 'independent sector vintage')
                for flag in ('current_business_identity_verified', 'financial_version_history_complete',
                             'financial_reporting_compatibility_verified', 'investment_factor_admitted'):
                    need(row[flag] is False, 'row source evidence limit')
                current = None
                if not candidates:
                    expected_status = 'NO_VISIBLE_ANNUAL_REPORT'
                    need('latest_fiscal_year' not in row, 'no invisible annual identity')
                else:
                    years = {d['effective_fiscal_year'] for d in candidates}
                    year = sorted(years)[-1]
                    annual = [d for d in candidates if d['effective_fiscal_year'] == year]
                    last_day = sorted({d['day'] for d in annual})[-1]
                    editions = sorted([d for d in annual if d['day'] == last_day], key=lambda d: (int(d['announcement_id']), d['capture_key']))
                    need(row['latest_fiscal_year'] == year and row['latest_publication_day'] == last_day
                         and row['selected_edition_capture_keys'] == [d['capture_key'] for d in editions], 'independent latest edition set')
                    if len({d['source_sha256'] for d in editions}) > 1:
                        expected_status = 'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'
                    else:
                        doc = editions[0]; case = cases[doc['capture_key']]
                        need(row['selected_capture_key'] == doc['capture_key'] and row['selected_source_sha256'] == doc['source_sha256']
                             and row['selected_source_status'] == case['status'], 'selected immutable source case')
                        if case['status'] != 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW':
                            expected_status = 'LATEST_' + case['status']
                        else:
                            expected_status = 'LATEST_CURRENT_SOURCE_SUPPORTED_NOT_ADMITTED'
                            current = [o for o in case['source_observations'] if o['fiscal_end'] == f'{year}-12-31']
                            need(len(current) == 1, 'single current column')
                            current = current[0]; observation = row['current_observation']
                            need(observation['source'] == current and observation['record_id'] == current['record_id']
                                 and current['record_id'] == digest({k: v for k, v in current.items() if k != 'record_id'}), 'immutable current observation')
                            money = current['payload']['cells']
                            gross = Fraction(money['revenue']['value_CNY']) - Fraction(money['cost_of_sales']['value_CNY'])
                            assets = Fraction(money['total_assets']['value_CNY'])
                            need(Fraction(observation['gross_profit_CNY']) == gross and assets > 0, 'exact gross profit/assets')
                            # Production Decimal rounds at60 significant digits; rational check bounds its error.
                            need(abs(Fraction(observation['gross_profit_to_assets']) - gross / assets) <=
                                 max(abs(gross / assets), Fraction(1)) / 10**59, 'independent rational ratio')
                            supported_checked += 1
                need(row['annual_status'] == expected_status, 'independent latest annual status')
                if current is None:
                    need('current_observation' not in row, 'missing/failed/conflicting latest cannot backfill older source')
                records_checked += 1
            counts = dict(Counter(r['annual_status'] for r in rows))
            cross = dict(Counter(r['industry_status'] + '/' + r['annual_status'] for r in rows))
            queries.append({**formation, 'mode': mode, 'artifact': name, 'annual_status_counts': counts,
                            'industry_annual_status_counts': cross})
    need(summary['queries'] == terminal['completed_queries'] == queries, 'all48 summary/terminal independently recomputed')
    for flag in ('historical_arrival_verified', 'current_business_identity_verified', 'financial_version_history_complete',
                 'investment_factor_admitted', 'security_ranking_or_portfolio_returns_computed',
                 '2026_financial_or_market_values_read', 'objective_achieved'):
        need(summary[flag] is False, 'summary evidence limit')
    for key, path in paths.items():
        need(sha(path) == expected[key], 'input after: ' + key)
    need(inventory(run) == outputs, 'all source output bytes unchanged through QA')
    result = {'status': 'SEPARATE48_QUERY_FULL_COHORT_SOURCE_AVAILABILITY_AUDIT_PASSED_NOT_ADMITTED',
              'audit_code_sha256': sha(Path(__file__)), 'request_sha256': a.expected_request_sha256,
              'input_count': len(paths), 'input_binding_digest': digest(expected), 'all_output_sha256': outputs,
              'all_inputs_and_outputs_unchanged': True, 'queries_checked': len(queries),
              'cohort_query_rows_checked': records_checked, 'current_observations_checked': supported_checked,
              'no_production_selector_imports': True, 'same_researcher_after_source_run': True,
              'complete_manual_business_review': False, 'investment_factor_admitted': False, 'objective_achieved': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2); handle.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'all_output_sha256'}))


if __name__ == '__main__':
    main()
