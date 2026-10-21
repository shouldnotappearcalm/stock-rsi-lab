"""Freeze and inspect monthly annual-source availability without ranking/prices."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from scripts.immutable_http_capture import file_sha, need, write_once
from stock_rsi import profitability_availability as source

OUTPUT = 'gross-profitability-monthly-availability-v1-20261022'
STATUS = 'FROZEN_BEFORE_MONTHLY_FULL_COHORT_SOURCE_AVAILABILITY'
V7_REQUEST = 'experiments/qlib/profitability-all1236-v7-request.json'
V7_OUTPUT = 'gross-profitability-all1236-header-v7-20261022'
INDUSTRY_OUTPUT = 'gross-profitability-2021Q3-industry-catalog-v1-20261022'
CALENDAR = 'qlib-enhanced-dev/calendars/day.txt'
METHODS = ('src/stock_rsi/profitability_availability.py', 'src/stock_rsi/annual_profitability.py',
           'src/stock_rsi/industry_catalog.py', 'src/stock_rsi/data.py',
           'scripts/immutable_http_capture.py', 'scripts/build_profitability_availability.py')


def read(path):
    return json.loads(Path(path).read_text())


def formations(calendar):
    days = [date.fromisoformat(s) for s in calendar.read_text().splitlines()]
    need(days == sorted(set(days)), 'explicit unique ordered sessions')
    result = []
    for previous, current in zip(days, days[1:]):
        if '2024-01-02' <= current.isoformat() <= '2025-12-31' and previous.strftime('%Y-%m') != current.strftime('%Y-%m'):
            result.append({'execution_session': current.isoformat(), 'as_of': previous.isoformat() + 'T15:05:00+08:00'})
    need(len(result) == 24 and len({r['execution_session'][:7] for r in result}) == 24,
         'complete24 monthly explicit-session transitions')
    return result


def resolve(key, root, base, membership):
    if key == 'membership':
        return membership
    if key.startswith('catalog/'):
        name = key[8:]
        old = base / 'cninfo-csi500-reports-20261017'
        fixed = base / 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json'
        special = {'membership_intervals': membership, 'metadata_manifest': old / 'manifest.json',
                   'metadata_plan': old / 'plan.json', 'PDF_document_records': fixed,
                   'inventory_code': root / 'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
        if name in special:
            return special[name]
        if name.startswith('metadata/'):
            need(len(Path(name).parts) == 2 and '..' not in Path(name).parts, 'safe metadata alias')
            return old / 'codes' / (name[9:] + '.json')
        docs = {d['capture_key']: d for d in read(fixed)}
        need(name.startswith('PDF/') and name[4:] in docs, 'known fixed original alias')
        relative = Path(docs[name[4:]]['source_path'])
        need(not relative.is_absolute() and '..' not in relative.parts, 'safe original alias path')
        return base / relative
    need(key.startswith(('source/', 'repo/')) and '..' not in Path(key).parts, 'known safe source namespace')
    relative = Path(key.split('/', 1)[1])
    need(not relative.is_absolute(), 'relative source binding required')
    return (base if key.startswith('source/') else root) / relative


def verify(base, root, membership, request, expected_sha):
    need(file_sha(request) == expected_sha, 'frozen availability request')
    req = read(request)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT
         and req['cohort_count'] == 394 and req['document_count'] == 1236
         and req['formations'] == formations(base / CALENDAR)
         and req['modes'] == [source.OBSERVED, source.RECONSTRUCTED]
         and req['network_permitted'] is False and req['ranking_or_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False
         and req['newer_source_failures_block_older_values'] is True
         and req['classification_is_2021_vintage_only'] is True
         and set(req['method_sha256']) == set(METHODS), 'complete cohort source-only availability contract')
    paths = {key: resolve(key, root, base, membership) for key in req['input_sha256']}
    for key, path in paths.items():
        need(file_sha(path) == req['input_sha256'][key], 'bound availability input: ' + key)
    for name, value in req['method_sha256'].items():
        need(value == req['input_sha256']['repo/' + name], 'complete method binding')
    v7 = read(root / V7_REQUEST)
    need(len(v7['documents']) == 1236 and req['documents'] == v7['documents'], 'all prior source editions')
    cohort = sorted({c for c, start, end in (s.split() for s in membership.read_text().splitlines())
                     if start <= '2024-01-02' <= end and c.startswith(('SH60', 'SZ00'))})
    need(cohort == req['cohort'] and len(cohort) == 394, 'same full dated source cohort')
    for parent, relative in (('v7', V7_OUTPUT), ('industry', INDUSTRY_OUTPUT)):
        audit = read(root / req['parent_audit_paths'][parent])
        outputs = {str(p.relative_to(base / relative)): file_sha(p)
                   for p in sorted((base / relative).rglob('*')) if p.is_file()}
        need(outputs == audit['all_output_sha256'], 'entire authenticated parent output inventory')
        for key, value in outputs.items():
            need(req['input_sha256']['source/' + relative + '/' + key] == value, 'parent output closure')
        for key, value in audit['all_input_sha256'].items():
            if key != 'frozen_source_request':
                need(req['input_sha256'][key] == value, 'parent original-source closure')
    return req, paths


def run(base, root, membership, request, expected_sha, *, builder=source.snapshot_availability):
    out = base / OUTPUT
    need(not out.exists(), 'fresh availability output; no resume or overwrite')
    req, paths = verify(base, root, membership, request, expected_sha)
    paths = {**paths, 'frozen_source_request': request}
    expected = {**req['input_sha256'], 'frozen_source_request': expected_sha}
    for key, path in paths.items():
        need(file_sha(path) == expected[key], 'availability input before: ' + key)
    out.mkdir(parents=True)
    completed, primary, mismatches, persistence = [], None, [], []
    try:
        write_once(out / 'input-before.json', expected)
        cases, industry = read(base / V7_OUTPUT / 'case_results.json'), read(base / INDUSTRY_OUTPUT / 'catalog.json')
        need(set(cases) == {d['capture_key'] for d in req['documents']}, 'all source cases')
        for formation in req['formations']:
            for mode in req['modes']:
                result = builder(req['documents'], cases.__getitem__, industry, req['cohort'], formation['as_of'], mode=mode)
                name = formation['execution_session'] + '-' + mode + '.json'
                write_once(out / name, result)
                counts = dict(Counter(r['annual_status'] for r in result['classifications']))
                cross = dict(Counter(r['industry_status'] + '/' + r['annual_status'] for r in result['classifications']))
                completed.append({**formation, 'mode': mode, 'artifact': name, 'annual_status_counts': counts,
                                  'industry_annual_status_counts': cross})
                print('availability', len(completed), '/', len(req['formations']) * len(req['modes']), flush=True)
    except BaseException as exc:
        primary = exc
    finally:
        for key, path in paths.items():
            try:
                if file_sha(path) != expected[key]:
                    mismatches.append({'input': key, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': key, 'reason': type(exc).__name__})
        post = {'all_inputs_unchanged': not mismatches, 'count': len(paths), 'mismatches': mismatches}
        terminal = {'completed_queries': completed, 'pending_query_count': len(req['formations']) * len(req['modes']) - len(completed),
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': post, 'persistence_errors': persistence}
        for name, value in (('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write_once(out / name, value)
            except BaseException as exc:
                persistence.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence:
            primary.add_note('availability persistence: ' + str(persistence))
        raise primary
    need(not mismatches and not persistence, 'unchanged availability inputs and persisted terminal')
    summary = {'status': 'MONTHLY_FULL_COHORT_SOURCE_AVAILABILITY_COMPLETE_NOT_FACTOR_ADMITTED',
               'request_sha256': expected_sha, 'cohort_count': len(req['cohort']), 'document_count': len(req['documents']),
               'queries': completed, 'input_count': len(paths), 'all_inputs_unchanged': True,
               'historical_arrival_verified': False, 'current_business_identity_verified': False,
               'financial_version_history_complete': False, 'investment_factor_admitted': False,
               'security_ranking_or_portfolio_returns_computed': False,
               '2026_financial_or_market_values_read': False, 'objective_achieved': False}
    write_once(out / 'summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    for name in ('source-root', 'membership-file', 'request', 'expected-request-sha256'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    result = run(Path(a.source_root).resolve(), Path(__file__).resolve().parents[1],
                 Path(a.membership_file).resolve(), Path(a.request).resolve(), a.expected_request_sha256)
    print(result['status'], flush=True)


if __name__ == '__main__':
    main()
