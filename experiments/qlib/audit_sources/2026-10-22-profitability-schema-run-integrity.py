"""Check frozen schema-run conservation; does not independently parse PDF cells.

Authored after the run by the same researcher. No production imports or network.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def need(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def safe_child(root, name):
    need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'relative bound artifact required')
    child = root / name
    need(child.resolve().is_relative_to(root.resolve()), 'artifact outside bound root')
    return child


def inspect(root, base, request, expected_sha, run):
    need(sha(request) == expected_sha, 'frozen schema request identity')
    req = read(request)
    need(req['status'] == 'FROZEN_BEFORE_FIXED36_FINANCIAL_SOURCE_SCHEMA_INSPECTION'
         and req['document_count'] == 36 and req['security_ranking_or_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False, 'source-only fixed36 scope')
    expected = {**req['input_sha256'], 'frozen_source_request': expected_sha}
    paths = {}
    for key in req['input_sha256']:
        prefix, name = key.split('/', 1)
        need(prefix in ('repo', 'source'), 'known input root')
        paths[key] = safe_child(root if prefix == 'repo' else base, name)
    paths['frozen_source_request'] = request
    need(len(paths) == 283, 'complete283 bound inputs')
    for key, path in paths.items():
        need(sha(path) == expected[key], 'unchanged input before integrity check: ' + key)
    outputs = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    documents = read(base / 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json')
    cases, summary = read(run / 'case_results.json'), read(run / 'summary.json')
    required = {d['capture_key'] + '.json' for d in documents} | {
        'case_results.json', 'input-before.json', 'input-postcheck.json', 'terminal.json', 'summary.json'}
    need(set(outputs) == required and len(required) == 41, 'exact41 source-run artifacts')
    need(set(cases) == {d['capture_key'] for d in documents}, 'complete fixed36 cases')
    false_fields = ('financial_version_history_complete', 'historical_arrival_verified',
                    'economic_sector_compatibility_verified', 'manual_numeric_visual_review_complete',
                    'investment_factor_admitted')
    counts, coverage, observations = Counter(), {}, 0
    supported = 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW'
    for document in documents:
        key = document['capture_key']
        case = cases[key]
        need(case == read(run / (key + '.json')), 'case packet conservation')
        need(case['instrument'] == document['instrument'] and case['fiscal_year'] == document['fiscal_year']
             and case['source_sha256'] == document['source_sha256'], 'source document identity conservation')
        need(all(case[field] is False for field in false_fields), 'no unearned data admission')
        hashes = case['all_extracted_page_text_sha256']
        need(set(hashes) == {str(i) for i in range(1, case['page_count'] + 1)}
             and all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in hashes.values()),
             'complete physical page hash inventory; text not independently rederived')
        status = case['status']
        if status == supported:
            need(case['cover_code_consistent'] and case['cover_annual_year_consistent']
                 and len(case['source_observations']) == 2, 'supported parse cover and fiscal pair')
            need({o['fiscal_end'] for o in case['source_observations']} == {
                f"{document['fiscal_year']}-12-31", f"{document['fiscal_year'] - 1}-12-31"}, 'current/prior pair')
            for observation in case['source_observations']:
                payload = observation['payload']
                need(observation['instrument'] == document['instrument']
                     and observation['publication_day'] == document['day']
                     and observation['observed_at'] == document['captured_at_utc']
                     and payload['document_sha256'] == document['source_sha256']
                     and payload['announcement_id'] == document['announcement_id']
                     and set(payload['cells']) == {'revenue', 'cost_of_sales', 'total_assets'},
                     'literal observation/source chronology conservation')
        else:
            need(case['source_observations'] == [], 'rejected source emits no financial observations')
            if status == 'COVER_IDENTITY_UNVERIFIED':
                need(not (case['cover_code_consistent'] and case['cover_annual_year_consistent']), 'failed cover check')
            else:
                need(status == 'SOURCE_SCHEMA_UNSUPPORTED' and case['cover_code_consistent']
                     and case['cover_annual_year_consistent'] and case['error']
                     and case['error_type'] in ('ValueError', 'KeyError', 'ArithmeticError'), 'explicit schema error')
        counts[status] += 1
        observations += len(case['source_observations'])
        coverage.setdefault(case['instrument'], {})[str(case['fiscal_year'])] = {
            'capture_key': key, 'status': status, 'error': case.get('error')}
    need(summary['status'] == 'FIXED36_FINANCIAL_SOURCE_SCHEMA_INSPECTION_COMPLETE_NOT_FACTOR_ADMITTED'
         and summary['documents'] == 36 and summary['issuer_count'] == 12
         and summary['request_sha256'] == expected_sha and summary['status_counts'] == dict(counts)
         and summary['coverage_by_issuer'] == coverage and summary['source_observations'] == observations
         and summary['all3_year_supported_parse_issuers'] == sum(
             all(r['status'] == supported for r in years.values()) for years in coverage.values())
         and summary['input_count'] == 283 and summary['all_inputs_unchanged'] is True,
         'summary rebuilt from all36 case packets')
    need(all(summary[field] is False for field in (*false_fields,
         'original_parser_or_financial_source_changed', 'security_ranking_or_portfolio_returns_computed',
         '2026_financial_or_market_values_read', 'objective_achieved')), 'source scope remains unadmitted')
    post = {'all_inputs_unchanged': True, 'count': 283, 'mismatches': [],
            'source_request_rehashed_after_processing': True}
    need(read(run / 'input-before.json') == expected and read(run / 'input-postcheck.json') == post,
         'complete original input journals')
    need(read(run / 'terminal.json') == {'status': 'FIXED36_SCHEMA_INSPECTION_TERMINAL',
         'completed_documents': 36, 'pending': [], 'original_error': None, 'postcheck': post,
         'persistence_errors': [], 'portfolio_returns_computed': False}, 'successful terminal conservation')
    for key, path in paths.items():
        need(sha(path) == expected[key], 'unchanged input after integrity check: ' + key)
    need(outputs == {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()},
         'run artifacts unchanged during check')
    return {'status': 'PASS_FIXED36_SCHEMA_RUN_INTEGRITY_NOT_PDF_CELL_AUTHENTICATION',
        'audit_code_sha256': sha(__file__), 'request_sha256': expected_sha,
        'summary_sha256': sha(run / 'summary.json'), 'all283_input_sha256': expected,
        'all41_output_sha256': outputs, 'status_counts': dict(counts), 'source_observations': observations,
        'production_modules_imported': False, 'PDF_text_or_cells_independently_rederived': False,
        'authored_after_run_same_researcher': True, 'blinded_or_independent_researcher_audit_claimed': False,
        'investment_factor_admitted': False, 'historical_arrival_verified': False, 'objective_achieved': False}


def main():
    parser = argparse.ArgumentParser()
    for name in ('repo-root', 'source-root', 'request', 'expected-request-sha256', 'run-dir', 'output'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args()
    root, base, request, run, out = map(lambda p: Path(p).resolve(),
        (a.repo_root, a.source_root, a.request, a.run_dir, a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base), 'new external report only')
    report = inspect(root, base, request, a.expected_request_sha256, run)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(report['status'], sha(out), report['status_counts'])


if __name__ == '__main__':
    main()
