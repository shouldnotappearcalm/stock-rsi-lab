"""Source-only frozen generation of a new monthly risk-overlay trial.

No account/return calculation or network. Original targets and failed accounts
are retained. This step changes desired weights, never actual inventory.
"""
import argparse
from collections import Counter
from pathlib import Path

from scripts import run_illiquidity_source_scenario_development as original
from stock_rsi.monthly_price_risk import CONTRACT, POLICY_ID, build_overlay_targets

read, write, file_sha, need = original.read, original.write, original.file_sha, original.need
BASE_PLAN = 'experiments/qlib/illiquidity-source-scenario-development-plan.json'
BASE_PLAN_SHA = '7a164209327630135689ddfb6a3b4b4b4a3fd885692e6ae2e37500563e298471'
PRIMARY_DIR = 'amihud-monthly-price-risk-primary-20261022'
PUBLIC_FILES = (BASE_PLAN,
    'experiments/qlib/illiquidity-source-scenario-development-results.json',
    'experiments/qlib/illiquidity-source-scenario-development-independent-ledger-audit.json',
    'experiments/qlib/illiquidity-source-scenario-development-run-verification.json',
    'experiments/qlib/illiquidity-source-scenario-development-failure-diagnostic.json',
    'experiments/qlib/amihud-monthly-price-risk-primary-discovery.json',
    'experiments/qlib/amihud-monthly-price-risk-primary-review.json',
    'experiments/qlib/monthly-price-risk-module-code-review.json',
    'experiments/qlib/monthly-price-risk-builder-code-review.json',
    'docs/research/amihud-monthly-price-risk-plan-2026-10-22.md')
METHOD_FILES = tuple(dict.fromkeys((*original.METHOD_FILES,
    'src/stock_rsi/monthly_price_risk.py', 'scripts/build_monthly_price_risk_targets.py')))
STATUS = 'FROZEN_BEFORE_MONTHLY_PRICE_RISK_REAL_TARGET_GENERATION'
FAILED_DIR = 'illiquidity-source-scenario-development-20261022'


def authenticated_primary_paths(base, root):
    discovery = read(root / 'experiments/qlib/amihud-monthly-price-risk-primary-discovery.json')
    review_path = root / 'experiments/qlib/amihud-monthly-price-risk-primary-review.json'
    review = read(review_path)
    directory = base / PRIMARY_DIR
    manifest_path = directory / 'manifest.json'
    manifest = read(manifest_path)
    need(file_sha(manifest_path) == discovery['source_manifest_sha256']
         and file_sha(review_path) == discovery['independent_review_sha256'],
         'primary manifest or independent review anchor changed')
    expected = discovery['formal_primary_file_sha256']
    canonical = {'capture-manifest.json', 'szse-listing-rules-2023-08.pdf',
                 'sse-delist-rule-2020-12-31.html', 'sse-delist-rule-2020-12-31.html.txt',
                 'sse-delist-2024-01-09.html', 'sse-delist-2024-01-09.html.txt',
                 'szse-page-113.png', 'szse-page-116.png'}
    canonical.update('review-' + name for name in review['reading_page_artifact_sha256'])
    need(len(expected) == 22 and len(review['reading_page_artifact_sha256']) == 14
         and set(expected) == canonical and manifest['file_sha256'] == expected,
         'complete canonical22 primary evidence required')
    need(expected['capture-manifest.json'] == review['capture_manifest_sha256'],
         'primary capture anchor changed')
    need(len(review['sources']) == 3 and {Path(r['local_path']).name for r in review['sources']}
         == {'szse-listing-rules-2023-08.pdf', 'sse-delist-rule-2020-12-31.html',
             'sse-delist-2024-01-09.html'}, 'exact three reviewed primary sources required')
    for receipt in review['sources']:
        need(expected[Path(receipt['local_path']).name] == receipt['sha256'],
             'reviewed primary source changed')
    for name, digest in review['reading_page_artifact_sha256'].items():
        need(expected['review-' + name] == digest, 'reviewed primary page changed')
    need(manifest['portfolio_returns_computed'] is False and manifest['historical_arrival_verified'] is False,
         'primary-source-only manifest required')
    paths = {'source/' + PRIMARY_DIR + '/manifest.json': manifest_path}
    for name, digest in expected.items():
        need(Path(name).name == name, 'unsafe primary source filename')
        path = directory / name
        need(file_sha(path) == digest, 'primary evidence bytes changed')
        paths['source/' + PRIMARY_DIR + '/' + name] = path
    return paths


def authenticated_failed_paths(base, root):
    prefix = root / 'experiments/qlib/illiquidity-source-scenario-development'
    verification = read(Path(str(prefix) + '-run-verification.json'))
    audit_path = Path(str(prefix) + '-independent-ledger-audit.json')
    audit = read(audit_path)
    expected = verification['all307_local_output_file_sha256']
    canonical = {f'{p}/{c}/{capital}/{name}' for p in (100, 500, 1000)
                 for c in (0, 5, 10, 20, 40)
                 for capital in ('100000', '1000000', '10000000', '100000000')
                 for name in ('error.json', 'failed_account_state.json', 'failure_trace.json',
                              'partial_case.json', 'tape_accessed_pairs.json')}
    canonical.update(('summary.json', 'input-before.json', 'event_source_receipts.json',
                      'input-postcheck.json', 'derived_events.json', 'terminal.json', 'case_results.json'))
    need(len(expected) == 307 and set(expected) == canonical and expected == audit['all_output_sha256'],
         'complete canonical307 old failed outputs required')
    need(file_sha(audit_path) == verification['independent_audit_sha256']
         and audit['plan_sha256'] == verification['plan_sha256'] == BASE_PLAN_SHA
         and audit['completed_profiles'] == 0 and audit['failed_profiles'] == 60
         and audit['raw_confirmation_passes_independently'] is False,
         'old failed account audit anchor changed')
    need(file_sha(Path(str(prefix) + '-results.json')) == verification['summary_sha256']
         == audit['summary_sha256'] == expected['summary.json'], 'old failure summary anchor changed')
    paths = {}
    for name, digest in expected.items():
        path = base / FAILED_DIR / name
        need(file_sha(path) == digest, 'old failed account bytes changed')
        paths['source/' + FAILED_DIR + '/' + name] = path
    return paths


def required_input_paths(base, root):
    paths = original.required_input_paths(base, root)
    for name in (*METHOD_FILES, *PUBLIC_FILES):
        paths['repo/' + name] = root / name
    paths.update(authenticated_primary_paths(base, root))
    paths.update(authenticated_failed_paths(base, root))
    return paths


def verify_request(base, root, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha, 'frozen risk target request changed')
    request = read(request_file)
    need(request['status'] == STATUS and request['contract'] == CONTRACT and request['policy_id'] == POLICY_ID
         and request['candidate_budget'] == 1 and request['minimum_formation_raw_close_CNY'] == '1.00'
         and request['surviving_target_budget'] == '.95' and request['end'] == '2025-12-31'
         and request['portfolio_returns_permitted'] is False and request['2026_evaluation_permitted'] is False,
         'one fixed pre2026 source-only risk trial required')
    need(set(request['method_code_sha256']) == set(METHOD_FILES), 'complete frozen risk methods required')
    for name, expected in request['method_code_sha256'].items():
        need(file_sha(root / name) == expected, 'frozen risk method changed')
    paths = required_input_paths(base, root)
    original.source.check_hashes(paths, request['input_sha256'])
    return request, paths


def build(base, root, request_file, expected_sha, out):
    need(not out.exists(), 'risk-target output already exists')
    request, paths = verify_request(base, root, request_file, expected_sha)
    base_plan, _ = original.verify_plan(base, root, root / BASE_PLAN, BASE_PLAN_SHA)
    context = original.load_inputs(base, root, base_plan)
    need(len(context['targets']) == 24 and len(context['calendar'].days) == 486,
         'complete original development seed required')
    paths = {**paths, 'frozen_risk_target_request': Path(request_file)}
    expected = {**request['input_sha256'], 'frozen_risk_target_request': expected_sha}
    original.source.check_hashes(paths, expected)
    out.mkdir(parents=True)
    primary, result, mismatches, persistence_errors, accesses = None, None, [], [], []
    try:
        write(out / 'input-before.json', expected)
        def reader(code, day):
            need(day <= '2025-12-31', 'future formation cells forbidden')
            accesses.append([code, day])
            row = context['bars'][code][day]
            return {key: row[key] for key in ('date', 'close', 'tradestatus', 'isST')}
        targets, receipts = build_overlay_targets(context['targets'], context['calendar'].days, reader)
        need(set(targets) == set(context['targets']) and len(receipts) == 24,
             'all24 unchanged formation times required')
        for day, target in targets.items():
            need(set(target['weights']) <= set(context['targets'][day]['weights']),
                 'risk overlay may not introduce or rerank securities')
        active, skipped = original.source.prefix_minute_requirements(targets, context['bars'], context['lifecycles'])
        old = read(root / original.source.MIN_REQ)
        need(set(map(tuple, active)) <= set(map(tuple, old['active_requests']))
             and all(row in old['nonexecuting_source_intervals'] for row in skipped),
             'new targets require minute sources outside unchanged authenticated bank')
        for name, value in (('targets.json', targets), ('formation_receipts.json', receipts),
                            ('formation_accesses.json', accesses), ('minute_requirements.json',
                            {'active_requests': active, 'nonexecuting_source_intervals': skipped})):
            write(out / name, value)
        result = {'status': 'MONTHLY_PRICE_RISK_TARGETS_BUILT_ACCOUNT_NOT_RUN', 'contract': CONTRACT,
                  'policy_id': POLICY_ID, 'request_sha256': expected_sha, 'method_code_sha256': request['method_code_sha256'],
                  'seed_target_sha256': file_sha(base / original.source.TARGET), 'months': 24,
                  'formation_cell_reads': len(accesses), 'changed_weight_months': sum(
                      targets[d]['weights'] != context['targets'][d]['weights'] for d in targets),
                  'blocked_reason_counts': dict(Counter(reason for r in receipts for reasons in r['blocked'].values() for reason in reasons)),
                  'all_filtered_cash_months': sum(r['all_filtered_to_cash'] for r in receipts),
                  'new_active_minute_requirements': len(active), 'new_nonexecuting_source_intervals': len(skipped),
                  'all_minute_sources_inside_original_bank': True,
                  'artifacts_sha256': {n: file_sha(out / n) for n in ('targets.json', 'formation_receipts.json',
                                       'formation_accesses.json', 'minute_requirements.json')},
                  'actual_positions_changed_by_target_generation': False, 'actual_exit_verified': False,
                  'original_targets_or_failed_results_changed': False, 'original_account_or_broker_changed': False,
                  'statutory_delisting_classifier': False, 'historical_arrival_verified': False,
                  'original_source_admission_overridden': False, 'conditional_engineering_only': True,
                  'separate_account_freeze_required': True, 'portfolio_returns_computed': False,
                  '2026_quote_or_return_values_read': False, 'objective_achieved': False}
    except BaseException as exc:
        primary = exc
    finally:
        for name, path in paths.items():
            try:
                if file_sha(path) != expected[name]:
                    mismatches.append({'input': name, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': name, 'reason': type(exc).__name__})
        post = {'all_inputs_unchanged': not mismatches, 'count': len(paths), 'mismatches': mismatches,
                'risk_request_rehashed_after_processing': True}
        terminal = {'status': 'RISK_TARGET_GENERATION_TERMINAL',
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'completed': result is not None, 'formation_accesses': accesses, 'postcheck': post,
                    'persistence_errors': persistence_errors, 'portfolio_returns_computed': False}
        for name, value in (('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('Risk-target terminal persistence errors: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'risk-target input changed or terminal persistence failed')
    result['input_count'] = len(paths)
    result['all_inputs_unchanged'] = True
    write(out / 'summary.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    result = build(Path(args.source_root).resolve(), Path(__file__).resolve().parents[1], Path(args.request),
                   args.expected_request_sha256, Path(args.output_dir))
    print(result['status'], result['changed_weight_months'], flush=True)


if __name__ == '__main__':
    main()
