"""Separately frozen60-profile conditional-source Amihud22 confirmation.

Calls the unchanged original strategy replay/account/broker. No2026 access,
search, gate override, source network or portfolio optimization is performed.
"""
import argparse
import copy
from dataclasses import asdict
from decimal import Decimal
from functools import partial
import json
from pathlib import Path

from scripts import build_illiquidity_archive_scenario_sources as source
from scripts.illiquidity_scenario_tape import ScenarioTapeBank
from scripts.run_illiquidity_intraday_development import METHOD_FILES as ORIGINAL_METHODS, confirmation_passes
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.run_low_risk_intraday_replay import PARTICIPATION, EXTRA_BPS, TapeBank, write_case
from scripts.run_low_risk_raw_share_validation import CAPITALS, clean, summarize_case
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

read, write, file_sha, need = source.read, source.write, source.file_sha, source.need
SOURCE_REQUEST = 'experiments/qlib/illiquidity-archive-scenario-source-request.json'
SOURCE_REQUEST_SHA = 'c917b4c4cde4a6ce13d626e0ccc8f1f80f6875c08b417e07d98b29c6ba4a191c'
SOURCE_DIR = 'illiquidity-archive-scenario-sources-20261022'
SOURCE_AUDIT = 'experiments/qlib/illiquidity-archive-scenario-independent-source-audit.json'
SOURCE_VERIFY = 'experiments/qlib/illiquidity-archive-scenario-source-run-verification.json'
LEDGER_AUDIT = 'experiments/qlib/audit_sources/2026-10-22-illiquidity-source-scenario-development-ledger.py'
PUBLIC_FILES = (SOURCE_REQUEST, SOURCE_AUDIT, SOURCE_VERIFY,
    'experiments/qlib/illiquidity-archive-scenario-source-results.json',
    'experiments/qlib/audit_sources/2026-10-22-illiquidity-archive-scenario-independent-source-audit.py',
    'experiments/qlib/illiquidity-pre2026-results.json',
    'experiments/qlib/illiquidity-pre2026-independent-csv-audit.json',
    'experiments/qlib/illiquidity-pre2026-plan.json',
    'experiments/qlib/illiquidity-scenario-tape-code-review.json',
    'experiments/qlib/illiquidity-source-scenario-development-code-review.json', LEDGER_AUDIT,
    'docs/research/illiquidity-source-scenario-development-contract-2026-10-22.md')
METHOD_FILES = tuple(dict.fromkeys((*source.METHOD_FILES, *ORIGINAL_METHODS,
    'scripts/illiquidity_scenario_tape.py', 'scripts/run_illiquidity_source_scenario_development.py')))
STATUS = 'FROZEN_BEFORE_ILLIQUIDITY_CONDITIONAL_SOURCE_DEVELOPMENT_ACCOUNTS'
PROFILES = tuple(f'{p}/{cost}/{capital}' for p in PARTICIPATION for cost in EXTRA_BPS for capital in CAPITALS)


def required_input_paths(base, root):
    paths = source.required_input_paths(base, root)
    for name in (*METHOD_FILES, *PUBLIC_FILES):
        paths['repo/' + name] = root / name
    for name in read(root / SOURCE_VERIFY)['all34_output_file_sha256']:
        need(Path(name).name == name, 'unsafe source scenario artifact')
        paths['source/' + SOURCE_DIR + '/' + name] = base / SOURCE_DIR / name
    return paths


def verify_plan(base, root, plan_file, expected_sha):
    need(file_sha(plan_file) == expected_sha, 'frozen account plan changed')
    plan = read(plan_file)
    need(plan['status'] == STATUS and plan['strategy'] == 'amihud22'
         and plan['phase'] == 'dev' and plan['end'] == '2025-12-31'
         and plan['participation_bps'] == list(PARTICIPATION)
         and plan['extra_bps'] == list(EXTRA_BPS) and plan['capitals'] == list(CAPITALS)
         and plan['profiles'] == list(PROFILES), 'complete fixed pre2026 profile matrix required')
    need(plan['source_contract'] == source.CONTRACT and plan['source_scenario_dir'] == SOURCE_DIR
         and plan['source_request_sha256'] == SOURCE_REQUEST_SHA
         and plan['original_source_admission_overridden'] is False
         and plan['conditional_engineering_only'] is True
         and plan['2026_evaluation_permitted'] is False, 'explicit conditional-source scope required')
    need(set(plan['method_code_sha256']) == set(METHOD_FILES), 'complete frozen account methods required')
    for name, expected in plan['method_code_sha256'].items():
        need(file_sha(root / name) == expected, 'frozen account method changed')
    paths = required_input_paths(base, root)
    source.check_hashes(paths, plan['input_sha256'])
    return plan, paths


def load_inputs(base, root, plan):
    source_request, _ = source.verify_request(base, root, root / SOURCE_REQUEST, SOURCE_REQUEST_SHA)
    summary = read(base / SOURCE_DIR / 'summary.json')
    audit, verification = read(root / SOURCE_AUDIT), read(root / SOURCE_VERIFY)
    expected_outputs = verification['all34_output_file_sha256']
    need(len(expected_outputs) == 34 and expected_outputs == audit['all_output_sha256'],
         'complete independently audited source artifacts required')
    for name, expected in expected_outputs.items():
        need(Path(name).name == name and file_sha(base / SOURCE_DIR / name) == expected,
             'audited source projection bytes changed')
    summary_sha = file_sha(base / SOURCE_DIR / 'summary.json')
    need(summary_sha == plan['source_summary_sha256'] == audit['summary_sha256'] == verification['summary_sha256']
         and summary_sha == file_sha(root / 'experiments/qlib/illiquidity-archive-scenario-source-results.json')
         and audit['status'] == 'PASS_INDEPENDENT_ILLIQUIDITY_CONDITIONAL_ARCHIVE_SOURCE_AUDIT'
         and audit['critical_or_important_findings'] == []
         and audit['all_inputs_sha256'] == {**source_request['input_sha256'], 'frozen_request': SOURCE_REQUEST_SHA}
         and audit['audit_code_sha256'] == file_sha(root / verification['independent_audit_code_file'])
         and verification['independent_audit_sha256'] == file_sha(root / SOURCE_AUDIT)
         and verification['root_audit_reproduced_byte_identically'] is True,
         'source audit identity or scope changed')
    need(summary['conditional_source_coverage_complete'] is True
         and summary['status_counts'] == {'SOURCE_SCENARIO_COMPLETE': 2276}
         and summary['request_sha256'] == SOURCE_REQUEST_SHA
         and summary['admitted_for_account_replay'] is False
         and summary['original_admission_overridden'] is False
         and summary['historical_arrival_verified'] is False
         and summary['cent_grid_and_binary32_promotion_are_assumptions'] is True,
         'conditional source coverage required; original source gate cannot be substituted')
    admission = read(root / source.ADMISSION)
    need(admission['admitted_for_reconstructed_execution'] is False
         and admission['status_counts'] == {'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE': 2247, 'SOURCE_REJECTED': 29},
         'original failure gate changed')
    screen = read(root / 'experiments/qlib/illiquidity-pre2026-independent-csv-audit.json')
    need(screen['development_gate_passes_independently'] is True
         and screen['summary_sha256'] == file_sha(root / 'experiments/qlib/illiquidity-pre2026-results.json'),
         'original pre2026 candidate qualification required')
    packets, proof, calendar = source.authenticate_sources(base / source.RAW, base / source.PROOF,
                                                          base / source.TARGET, root)
    initial, lifecycle = source.classify_source_coverage(packets, proof, calendar)
    events, receipts = source.compile_distribution_events(packets, proof, calendar)
    originals = {'derived_events.json': clean([asdict(e) for e in events]),
                 'event_source_receipts.json': list(receipts),
                 'initial_listing_classification.json': initial, 'lifecycle_source_intervals.json': lifecycle}
    for name, value in originals.items():
        need(read(base / source.EVENTS / name) == value, 'original corporate compilation changed')
    bars = {code: {r['date']: r for r in p['bars']} for code, p in packets.items()}
    targets = read(base / source.TARGET)
    active, skipped = source.prefix_minute_requirements(targets, bars, proof['lifecycles'])
    original = read(root / source.MIN_REQ)
    need(active == original['active_requests'] and skipped == original['nonexecuting_source_intervals']
         and len(active) == 2276 and len(skipped) == 18, 'original complete source scope changed')
    details = read(base / SOURCE_DIR / 'details.json')
    need(file_sha(base / SOURCE_DIR / 'details.json') == summary['details_sha256']
         and details['nonexecuting_source_intervals'] == skipped, 'source details changed')
    records = copy.deepcopy(details['sessions'])
    for row in records:
        if row['source_kind'] == 'CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION':
            name = row['instrument'] + '-selected-development-rows.json'
            row['archive_selected_source_sha256'] = source_request['input_sha256']['source/' + source.ARCHIVE + '/' + name]
    rejected = [[r['instrument'], r['day']] for r in admission['exceptions']]
    bank = ScenarioTapeBank(TapeBank(base / source.OLD, base / source.EXTRA, bars, '2025-12-31'),
                            records, base / SOURCE_DIR, base / source.ARCHIVE, active, rejected)
    need(len(calendar.days) == 486 and calendar.days[-1].isoformat() == '2025-12-31'
         and len(targets) == 24, 'complete development calendar and targets required')
    return {'calendar': calendar, 'bars': bars, 'events': events, 'receipts': receipts,
            'targets': targets, 'lifecycles': proof['lifecycles'], 'lifecycle_source_audit': lifecycle, 'bank': bank}


def failure_context(exc, account, bank, case=None):
    """Read stopped original traceback locals; never alter replay execution."""
    partial_case, frame = {}, None
    trace = exc.__traceback__
    original = Path(__file__).with_name('replay_stock_distribution_targets.py').resolve()
    while trace is not None:
        if (Path(trace.tb_frame.f_code.co_filename).resolve() == original
                and trace.tb_frame.f_code.co_name == 'simulate_fixed_targets'):
            frame = trace
        trace = trace.tb_next
    context = {}
    if frame is not None:
        values = frame.tb_frame.f_locals
        for name, key in (('rows', 'days'), ('intents', 'intents'), ('ownership', 'ownership'),
                          ('lifecycle_audit', 'lifecycle_source_audit')):
            if name in values:
                partial_case[key] = clean(copy.deepcopy(values[name]))
        for name in ('day', 'number', 'marks', 'target', 'before_corp', 'before_fills'):
            if name in values:
                context[name] = clean(copy.deepcopy(values[name]))
        for name in ('required', 'pending'):
            if name in values:
                context[name] = sorted(values[name])
        context.update(original_replay_file='scripts/replay_stock_distribution_targets.py',
                       original_replay_line=frame.tb_lineno)
        try:
            context['original_replay_source_line'] = original.read_text().splitlines()[frame.tb_lineno - 1].strip()
        except (OSError, UnicodeError, IndexError) as diagnostic:
            context['original_replay_source_line_error'] = type(diagnostic).__name__
    elif case is not None:
        partial_case = clean(copy.deepcopy(case))
    state = None
    if account is not None:
        state = clean({'cash': account.broker.cash, 'positions': account.broker.positions,
                       'owned_shares': account.owned_quantities(), 'parent_instructions': account.broker.orders,
                       'child_orders': account.broker.child_orders, 'fills': account.broker.fills,
                       'corporate_ledger': account.corporate_ledger, 'cash_claims': account.cash_claims,
                       'stock_claims': account.stock_claims, 'entitlements': account.entitlements,
                       'last_account_clock': account._last_clock, 'last_broker_end': account.broker._last_end,
                       'processed_account_clocks': sorted(account._processed)})
    rows = partial_case.get('days', [])
    trace_record = {'error_type': type(exc).__name__, 'error': str(exc),
                    'attempted_day': context.get('day', rows[-1]['day'] if rows else None),
                    'last_completed_day': rows[-1]['day'] if rows else None,
                    'complete_simulation_returned': case is not None,
                    'last_account_clock': state['last_account_clock'] if state else None,
                    'tape_accessed_pairs': [list(k) for k in sorted(bank.accessed)], 'frame_context': context}
    return state, partial_case, trace_record


def complete_confirmation_passes(results):
    return set(results) == set(PROFILES) and confirmation_passes(results)


def run_profiles(context, out, results):
    calendar, bank = context['calendar'], context['bank']
    zero_ids = {r['event_id'] for r in context['receipts'] if r['requires_zero_record_ownership_if_tax_unverified']}
    union = set()
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            for capital in CAPITALS:
                label = f'{participation}/{cost}/{capital}'
                folder = out / label
                folder.mkdir(parents=True)
                holders, case, active_error = [], None, None
                bank.accessed.clear()
                print('conditional-source account ' + label, flush=True)
                def factory(cal, cash, distributions, **kwargs):
                    constructor = partial(IntradayBroker, participation_bps=participation,
                                          extra_cost_bps=cost, tape_provider=bank)
                    account = StockDistributionAccount(cal, cash, distributions, broker_factory=constructor, **kwargs)
                    holders.append(account)
                    return account
                try:
                    case = simulate_fixed_targets(calendar, context['bars'], context['events'], context['targets'],
                                                  capital, lifecycles=context['lifecycles'], account_factory=factory)
                    need([r['day'] for r in case['days']] == [str(d) for d in calendar.days]
                         and len(case['intents']) == 24 and case['whole_day_volume_violations'] == 0,
                         'complete account calendar, decisions and capacity required')
                    record = {r['event_id']: r['quantity'] for r in case['corporate_ledger']
                              if r['kind'] == 'RECORD_DATE_OWNERSHIP' and r['event_id'] in zero_ids}
                    ex = {r['event_id']: r['registered_quantity'] for r in case['corporate_ledger']
                          if r['kind'] == 'EX_DATE_ENTITLEMENT' and r['event_id'] in zero_ids}
                    need(set(record) == zero_ids == set(ex) and all(record[k] == ex[k] == 0 for k in zero_ids),
                         'unverified share distribution has actual entitlement')
                    need(case['lifecycle_source_audit'] == context['lifecycle_source_audit'],
                         'all original lifecycle dependency checks required')
                    case['parent_instructions'] = case.pop('orders')
                    case['orders'] = holders[0].broker.child_orders
                    write(folder / 'lifecycle_source_audit.json', case['lifecycle_source_audit'])
                    write(folder / 'tape_accessed_pairs.json', [list(k) for k in sorted(bank.accessed)])
                    artifacts = write_case(folder, case)
                    development = [r for r in case['days'] if r['day'] >= '2024-01-02']
                    results[label] = {'status': 'NESTED_EXECUTION_ACCOUNT_RECONCILED', **summarize_case(case, capital),
                                      'average_exposure_pct': float(sum((r['exposure'] for r in development), Decimal(0)) / len(development) * 100),
                                      'zero_entitlements_verified': True, 'actual_delisting_exit_verified': True,
                                      'unfilled_parents': sum(p['remaining'] > 0 for p in case['parent_instructions']),
                                      'artifact_sha256': artifacts}
                except BaseException as exc:
                    active_error = exc
                    error = {'status': 'INVALID_SOURCE_OR_ACCOUNT', 'error_type': type(exc).__name__, 'error': str(exc)}
                    results[label] = error
                    persistence_errors = []
                    try:
                        state, partial_case, trace = failure_context(exc, holders[0] if holders else None, bank, case)
                    except BaseException as diagnostic:
                        persistence_errors.append('failure_context:' + type(diagnostic).__name__)
                        state, partial_case = None, {}
                        trace = {'error_type': type(exc).__name__, 'error': str(exc),
                                 'tape_accessed_pairs': [list(k) for k in sorted(bank.accessed)],
                                 'diagnostic_error': type(diagnostic).__name__}
                    for name, value in (('failed_account_state.json', state), ('partial_case.json', partial_case),
                                        ('failure_trace.json', trace), ('error.json', error),
                                        ('tape_accessed_pairs.json', trace['tape_accessed_pairs'])):
                        try:
                            write(folder / name, value)
                        except BaseException as persistence:
                            persistence_errors.append(name + ':' + type(persistence).__name__)
                    artifacts = {}
                    try:
                        for path in sorted(folder.iterdir()):
                            try:
                                artifacts[path.name] = file_sha(path)
                            except BaseException as persistence:
                                persistence_errors.append(path.name + ':hash:' + type(persistence).__name__)
                    except BaseException as persistence:
                        persistence_errors.append('folder_listing:' + type(persistence).__name__)
                    results[label] = {**error, 'failure_artifact_sha256': artifacts,
                                      'persistence_errors': persistence_errors}
                    if persistence_errors:
                        exc.add_note('Failed-case persistence errors: ' + str(persistence_errors))
                        raise exc
                    if not isinstance(exc, (ValueError, KeyError, AssertionError)):
                        raise
                finally:
                    union.update(bank.accessed)
                    context['all_tape_accessed'] = union
                    try:
                        write(out / 'case_results.json', results)
                    except BaseException as persistence:
                        if active_error is not None:
                            active_error.add_note('Case-result persistence error: ' + type(persistence).__name__)
                            raise active_error from persistence
                        raise


def run(base, root, plan_file, expected_sha, out):
    need(not out.exists(), 'account output already exists')
    plan, paths = verify_plan(base, root, plan_file, expected_sha)
    context = load_inputs(base, root, plan)
    paths = {**paths, 'frozen_account_plan': Path(plan_file)}
    expected = {**plan['input_sha256'], 'frozen_account_plan': expected_sha}
    source.check_hashes(paths, expected)
    out.mkdir(parents=True)
    results, primary, mismatches, persistence_errors = {}, None, [], []
    try:
        write(out / 'input-before.json', expected)
        write(out / 'derived_events.json', [asdict(e) for e in context['events']])
        write(out / 'event_source_receipts.json', context['receipts'])
        run_profiles(context, out, results)
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
        terminal = {'status': 'CONDITIONAL_SOURCE_ACCOUNT_RUN_TERMINAL',
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'completed_profiles': len(results), 'postcheck': post, 'persistence_errors': persistence_errors}
        for name, value in (('case_results.json', results), ('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('Account terminal persistence failures: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'account inputs changed or terminal evidence could not be saved')
    need(set(results) == set(PROFILES), 'all60profile outcomes required')
    result = {'status': 'ILLIQUIDITY_CONDITIONAL_SOURCE_DEVELOPMENT_COMPLETE', 'strategy': 'amihud22', 'phase': 'dev',
              'start': '2024-01-02', 'source_warmup_start': '2023-12-29', 'end': '2025-12-31',
              'results_by_profile': results, 'method_code_sha256': plan['method_code_sha256'],
              'plan_sha256': expected_sha, 'raw_development_confirmation_passes': complete_confirmation_passes(results),
              'reference_CNY': '1000000', 'source_contract': source.CONTRACT,
              'source_request_sha256': SOURCE_REQUEST_SHA, 'source_summary_sha256': plan['source_summary_sha256'],
              'source_scenario_dir': SOURCE_DIR, 'all_inputs_unchanged': True, 'input_count': len(paths),
              'tape_accessed_sessions': len(context.get('all_tape_accessed', set())),
              'derived_events_sha256': file_sha(out / 'derived_events.json'),
              'event_source_receipts_sha256': file_sha(out / 'event_source_receipts.json'),
              'conditional_engineering_only': True, 'original_source_admission_overridden': False,
              'registry_allocation_assumed': False, 'original_account_guards_changed': False,
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
        source.check_hashes(paths, plan['input_sha256'])
        need(file_sha(args.plan) == args.expected_plan_sha256, 'preflight account plan changed')
        print('source preflight complete; account/ROI not run', flush=True)
    else:
        need(args.output_dir is not None, 'account output directory required')
        result = run(base, root, Path(args.plan), args.expected_plan_sha256, Path(args.output_dir))
        print(result['status'], result['raw_development_confirmation_passes'], flush=True)


if __name__ == '__main__':
    main()
