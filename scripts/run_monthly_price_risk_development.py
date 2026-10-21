"""One separately frozen risk-overlay account trial; unchanged account methods.

The source-only targets must already be independently reconstructed. No source
query, strategy search, 2026 evaluation or legal allocation assumption is made.
"""
import argparse
from dataclasses import asdict
from pathlib import Path

from scripts import build_monthly_price_risk_targets as risk

original = risk.original
read, write, file_sha, need = risk.read, risk.write, risk.file_sha, risk.need
REQUEST = 'experiments/qlib/amihud-monthly-price-risk-target-request.json'
TARGET_DIR = 'amihud-monthly-price-risk-targets-20261022'
TARGET_FILES = ('targets.json', 'formation_receipts.json', 'formation_accesses.json',
                'minute_requirements.json', 'input-before.json', 'input-postcheck.json',
                'terminal.json', 'summary.json')
TARGET_AUDIT = 'experiments/qlib/amihud-monthly-price-risk-independent-target-audit.json'
TARGET_AUDIT_CODE = 'experiments/qlib/audit_sources/2026-10-22-amihud-monthly-price-risk-target-audit.py'
LEDGER_AUDIT_CODE = 'experiments/qlib/audit_sources/2026-10-22-amihud-monthly-price-risk-development-ledger.py'
PUBLIC_FILES = (REQUEST, TARGET_AUDIT, TARGET_AUDIT_CODE, LEDGER_AUDIT_CODE,
                'experiments/qlib/monthly-price-risk-account-code-review.json')
METHOD_FILES = (*risk.METHOD_FILES, 'scripts/run_monthly_price_risk_development.py')
STATUS = 'FROZEN_BEFORE_MONTHLY_PRICE_RISK_DEVELOPMENT_ACCOUNTS'


def required_input_paths(base, root):
    paths = risk.required_input_paths(base, root)
    for name in (*PUBLIC_FILES, *METHOD_FILES):
        paths['repo/' + name] = root / name
    for name in TARGET_FILES:
        paths['source/' + TARGET_DIR + '/' + name] = base / TARGET_DIR / name
    return paths


def verify_plan(base, root, plan_file, expected_sha):
    need(file_sha(plan_file) == expected_sha, 'frozen risk account plan changed')
    plan = read(plan_file)
    need(plan['status'] == STATUS and plan['strategy'] == risk.POLICY_ID
         and plan['base_strategy'] == plan['decision_record_seed_policy_id'] == 'amihud22'
         and plan['risk_contract'] == risk.CONTRACT and plan['phase'] == 'dev'
         and plan['end'] == '2025-12-31' and plan['candidate_budget'] == 1
         and plan['participation_bps'] == list(original.PARTICIPATION)
         and plan['extra_bps'] == list(original.EXTRA_BPS) and plan['capitals'] == list(original.CAPITALS)
         and plan['profiles'] == list(original.PROFILES), 'one complete fixed pre2026 risk account matrix required')
    need(plan['source_contract'] == original.source.CONTRACT
         and plan['source_scenario_dir'] == original.SOURCE_DIR
         and plan['source_request_sha256'] == original.SOURCE_REQUEST_SHA
         and plan['original_source_admission_overridden'] is False
         and plan['conditional_engineering_only'] is True
         and plan['registry_allocation_assumed'] is False
         and plan['2026_evaluation_permitted'] is False, 'unchanged conditional-source scope required')
    need(set(plan['method_code_sha256']) == set(METHOD_FILES), 'complete risk account methods required')
    for name, digest in plan['method_code_sha256'].items():
        need(file_sha(root / name) == digest, 'frozen risk account method changed')
    paths = required_input_paths(base, root)
    original.source.check_hashes(paths, plan['input_sha256'])
    return plan, paths


def load_inputs(base, root, plan):
    request, _ = risk.verify_request(base, root, root / REQUEST, plan['risk_target_request_sha256'])
    directory = base / TARGET_DIR
    audit = read(root / TARGET_AUDIT)
    need(audit['status'] == 'PASS_INDEPENDENT_MONTHLY_PRICE_RISK_TARGET_AUDIT'
         and audit['request_sha256'] == plan['risk_target_request_sha256']
         and audit['audit_code_sha256'] == file_sha(root / TARGET_AUDIT_CODE)
         and audit['all_input_sha256'] == {**request['input_sha256'],
                                          'frozen_risk_target_request': plan['risk_target_request_sha256']}
         and set(audit['all_output_sha256']) == set(TARGET_FILES)
         and audit['critical_or_important_findings'] == [], 'complete independent risk target audit required')
    for name, digest in audit['all_output_sha256'].items():
        need(file_sha(directory / name) == digest, 'independently audited target bytes changed')
    summary = read(directory / 'summary.json')
    need(file_sha(directory / 'summary.json') == plan['risk_target_summary_sha256']
         and summary['status'] == 'MONTHLY_PRICE_RISK_TARGETS_BUILT_ACCOUNT_NOT_RUN'
         and summary['contract'] == risk.CONTRACT and summary['policy_id'] == risk.POLICY_ID
         and summary['all_inputs_unchanged'] is True and summary['months'] == 24
         and summary['portfolio_returns_computed'] is False, 'completed source-only risk targets required')
    old_plan, _ = original.verify_plan(base, root, root / risk.BASE_PLAN, risk.BASE_PLAN_SHA)
    authenticate_source_summary(base, plan, old_plan)
    context = original.load_inputs(base, root, old_plan)
    targets = read(directory / 'targets.json')
    need(set(targets) == set(context['targets']), 'original24 execution sessions required')
    for day, target in targets.items():
        need(target['as_of'] == context['targets'][day]['as_of']
             and set(target['weights']) <= set(context['targets'][day]['weights'])
             and target['risk_overlay']['contract'] == risk.CONTRACT,
             'risk targets may not introduce securities or change formation timing')
    active, skipped = original.source.prefix_minute_requirements(targets, context['bars'], context['lifecycles'])
    need(read(directory / 'minute_requirements.json') == {
        'active_requests': active, 'nonexecuting_source_intervals': skipped}, 'risk minute scope changed')
    context['targets'] = targets
    return context


def authenticate_source_summary(base, plan, old_plan):
    need(plan['source_summary_sha256'] == old_plan['source_summary_sha256']
         == file_sha(base / original.SOURCE_DIR / 'summary.json'),
         'risk account source summary metadata changed')


def run(base, root, plan_file, expected_sha, out):
    need(not out.exists(), 'risk account output already exists')
    plan, paths = verify_plan(base, root, plan_file, expected_sha)
    context = load_inputs(base, root, plan)
    paths = {**paths, 'frozen_account_plan': Path(plan_file)}
    expected = {**plan['input_sha256'], 'frozen_account_plan': expected_sha}
    original.source.check_hashes(paths, expected)
    out.mkdir(parents=True)
    results, primary, mismatches, persistence_errors = {}, None, [], []
    try:
        write(out / 'input-before.json', expected)
        write(out / 'derived_events.json', [asdict(e) for e in context['events']])
        write(out / 'event_source_receipts.json', context['receipts'])
        original.run_profiles(context, out, results)
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
                'account_plan_rehashed_after_processing': True}
        terminal = {'status': 'MONTHLY_PRICE_RISK_ACCOUNT_RUN_TERMINAL',
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'completed_profiles': len(results), 'postcheck': post, 'persistence_errors': persistence_errors}
        for name, value in (('case_results.json', results), ('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('Risk account terminal persistence failures: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'risk account inputs changed or terminal evidence failed')
    need(set(results) == set(original.PROFILES), 'all60 risk profile outcomes required')
    result = {'status': 'MONTHLY_PRICE_RISK_DEVELOPMENT_COMPLETE', 'strategy': risk.POLICY_ID,
              'base_strategy': 'amihud22', 'decision_record_seed_policy_id': 'amihud22', 'risk_contract': risk.CONTRACT,
              'phase': 'dev', 'start': '2024-01-02', 'source_warmup_start': '2023-12-29', 'end': '2025-12-31',
              'results_by_profile': results, 'method_code_sha256': plan['method_code_sha256'],
              'plan_sha256': expected_sha, 'raw_development_confirmation_passes': original.complete_confirmation_passes(results),
              'reference_CNY': '1000000', 'source_contract': original.source.CONTRACT,
              'source_request_sha256': original.SOURCE_REQUEST_SHA, 'source_summary_sha256': plan['source_summary_sha256'],
              'source_scenario_dir': original.SOURCE_DIR, 'risk_target_request_sha256': plan['risk_target_request_sha256'],
              'risk_target_summary_sha256': plan['risk_target_summary_sha256'],
              'independent_target_audit_sha256': file_sha(root / TARGET_AUDIT),
              'all_inputs_unchanged': True, 'input_count': len(paths),
              'tape_accessed_sessions': len(context.get('all_tape_accessed', set())),
              'derived_events_sha256': file_sha(out / 'derived_events.json'),
              'event_source_receipts_sha256': file_sha(out / 'event_source_receipts.json'),
              'conditional_engineering_only': True, 'original_source_admission_overridden': False,
              'registry_allocation_assumed': False, 'original_account_guards_changed': False,
              'original_targets_or_failed_results_changed': False,
              'queue_and_impact_calibrated': False, 'historical_arrival_verified': False,
              '2026_strategy_returns_queried': False, 'sealed_evidence': False, 'objective_achieved': False}
    write(out / 'summary.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--output-dir')
    parser.add_argument('--source-preflight-only', action='store_true')
    args = parser.parse_args(argv)
    base, root = Path(args.source_root).resolve(), Path(__file__).resolve().parents[1]
    if args.source_preflight_only:
        plan, paths = verify_plan(base, root, Path(args.plan), args.expected_plan_sha256)
        load_inputs(base, root, plan)
        original.source.check_hashes(paths, plan['input_sha256'])
        need(file_sha(args.plan) == args.expected_plan_sha256, 'risk preflight plan changed')
        print('risk source preflight complete; account/ROI not run', flush=True)
    else:
        need(args.output_dir is not None, 'risk account output directory required')
        result = run(base, root, Path(args.plan), args.expected_plan_sha256, Path(args.output_dir))
        print(result['status'], result['raw_development_confirmation_passes'], flush=True)


if __name__ == '__main__':
    main()
