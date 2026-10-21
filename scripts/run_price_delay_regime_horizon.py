"""Unchanged price-delay portfolio; separately evidenced SSE trading regimes.

Reuses the frozen raw/event source authentication and Decimal ledger checks.
Neither the original failed account nor any investment rule is modified.
"""
import argparse
import json
import traceback
from copy import deepcopy
from datetime import date
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts import run_price_delay_horizon_raw as old
from scripts.replay_regime_stock_distribution_targets import simulate_regime_fixed_targets
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.trading_regime_horizon_source import regime_source_rows_on, validate_regime_evidence

read, sha, safe, need, clean = old.read, old.sha, old.safe, old.need, old.clean
OUTPUT = 'price-delay-regime-raw-daily-horizon-20261021'
PRIMARY = 'price-delay-regime-primary-horizon-20261021'
OLD_PLAN = 'experiments/qlib/price-delay-horizon-raw-daily-request.json'
FAILURE_AUDIT = 'experiments/qlib/price-delay-horizon-raw-account-failure-independent-review.json'
EVIDENCE = 'experiments/qlib/price-delay-regime-horizon-evidence.json'
PRIMARY_MANIFEST = 'experiments/qlib/price-delay-regime-primary-source-manifest.json'
PROTOCOL = 'docs/research/price-delay-regime-horizon-protocol-2026-10-21.md'
METHOD_FILES = old.METHOD_FILES + ('src/stock_rsi/trading_regime_source.py',
    'src/stock_rsi/trading_regime_horizon_source.py',
    'scripts/replay_regime_stock_distribution_targets.py',
    'scripts/run_price_delay_regime_horizon.py')
PUBLIC_FILES = (OLD_PLAN, FAILURE_AUDIT, EVIDENCE, PRIMARY_MANIFEST, PROTOCOL)
LOCAL_FILES = (PRIMARY + '/manifest.json', old.OUTPUT + '/summary.json',
               old.OUTPUT + '/case_results.json')
PROFILE = {'status': 'FROZEN_UNCHANGED_PRICE_DELAY_SSE_REGIME_HORIZON',
    'candidate': old.POLICY, 'candidate_budget': 1, 'initial_CNY': old.CAPITAL,
    'extra_cost_bps': list(old.COSTS), 'reference_extra_bps': 40,
    'window': [old.START, old.END], 'output_relative': OUTPUT,
    'allocator': 'plan_integer_targets', 'risk_warning_buy_permission': False,
    'source_queries': 0, 'investment_rule_changed': False,
    'old_failure_must_remain_unchanged': True, 'full_October_2026_complete': False,
    'sealed_2026_evidence_claimed': False, 'all_profile_gates_before_any_returns': True}


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(clean(value), stream, indent=2, allow_nan=False)
        stream.write('\n')


def verify_hashes(known):
    for name, expected in known.items():
        need(sha(name) == expected, 'frozen input changed: ' + name)


def require_plan(plan):
    need(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in PROFILE.items()),
         'unchanged strategy, integer allocator, account and both cost profiles required')
    for field, names in (('method_code_sha256', METHOD_FILES), ('public_evidence_sha256', PUBLIC_FILES),
                         ('local_source_sha256', LOCAL_FILES)):
        need(set(plan[field]) == set(names), 'complete fixed method/evidence/source map required')


def authenticate_primary(evidence, manifest, root, bind):
    need(manifest['status'] == 'HASH_VERIFIED_EXISTING_PRIMARY_BYTES_IMPORTED_FOR_SSE_REGIME_HORIZON'
         and manifest['source_data_modified'] is False and manifest['SDK_queries'] == 0,
         'immutable primary-source byte import required')
    for name, expected in manifest['artifact_sha256'].items():
        bind(safe(root, name), expected)
    need(manifest['artifact_sha256'] == read(root / 'manifest.json')['artifact_sha256'],
         'identical complete primary artifacts required')
    expected = manifest['reviewed_regime_evidence']
    need(evidence == expected and evidence['account_capabilities'] == {'risk_warning_buy_permission': False},
         'reviewed original documents, state clocks and unsigned risk capability required')
    documents = {d['file']: d for d in manifest['documents']}
    need(len(documents) == len(manifest['documents']), 'unique original primary document names required')
    for document in manifest['documents']:
        need(document['sha256'] == manifest['artifact_sha256'][document['file']],
             'every primary original must be in the authenticated artifact map')
    for rule in evidence['rule_epochs']:
        need(rule['source_file'] in documents and rule['sha256'] == documents[rule['source_file']]['sha256']
             and rule['published_on'] == documents[rule['source_file']]['published_on'],
             'rule metadata must match independently reviewed original bytes')
    for state in evidence['state_intervals']:
        need(state['source_file'] in documents
             and state['source_sha256'] == documents[state['source_file']]['sha256']
             and state['published_on'] == documents[state['source_file']]['published_on'],
             'issuer state must match independently reviewed original bytes')
    # Validate both epochs and every state's metadata without market access.
    for day in ('2023-12-29', '2026-07-06', '2026-10-20'):
        validate_regime_evidence(evidence, date.fromisoformat(day), day + 'T09:25:00+08:00')


def load_inputs(base, repo, plan_path, expected_sha):
    base, repo, plan_path = Path(base).resolve(), Path(repo).resolve(), Path(plan_path).resolve()
    need(sha(plan_path) == expected_sha, 'externally frozen request SHA changed')
    plan = read(plan_path)
    require_plan(plan)
    known = {str(plan_path): expected_sha}
    def bind(path, expected):
        path = Path(path).resolve()
        need(path.is_relative_to(base) or path.is_relative_to(repo), 'input outside registered roots')
        need(str(path) not in known or known[str(path)] == expected, 'conflicting bound hash')
        need(sha(path) == expected, 'frozen source/method changed: ' + str(path))
        known[str(path)] = expected
    for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                        ('local_source_sha256', base)):
        for name, expected in plan[field].items():
            bind(safe(root, name), expected)
    original_plan = read(repo / OLD_PLAN)
    # This source validator never calls a strategy, simulation or ROI scorer.
    inputs = old.load_inputs(base, repo, original_plan)
    for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                        ('local_source_sha256', base), ('immutable_financial_sha256', base)):
        for name, expected in original_plan[field].items():
            bind(safe(root, name), expected)
    for relative in (old.RAW, old.OLDRAW):
        manifest = read(base / relative / 'manifest.json')
        for code, expected in manifest['per_code_sha256'].items():
            bind(base / relative / 'codes' / (code + '.json'), expected)
    source = base / old.EVENTS
    for name, expected in read(source / 'summary.json')['artifact_sha256'].items():
        bind(safe(source, name), expected)
    proof = read(base / old.PROOFDIR / 'reviewed-manifest.json')
    documents = proof['documents'].values() if isinstance(proof['documents'], dict) else proof['documents']
    for document in documents:
        bind(safe(base / old.PROOFDIR, document['file']), document['sha256'])
    audit = read(repo / FAILURE_AUDIT)
    need(audit['status'] == 'INDEPENDENT_BOUNDED_RAW_ACCOUNT_FAILURE_EVIDENCE_CONFIRMED_NO_ANNUAL_ROI'
         and not audit['critical_or_important_findings']
         and audit['plan_sha256'] == plan['public_evidence_sha256'][OLD_PLAN]
         and audit['summary_sha256'] == sha(base / old.OUTPUT / 'summary.json')
         and audit['case_results_sha256'] == sha(base / old.OUTPUT / 'case_results.json')
         and audit['all60_original_financial_file_bytes_unchanged'] is True
         and audit['annual_returns_computed_after_both_complete_gates'] is False
         and audit['failure_day'] == '2026-03-31' and audit['failure_instrument'] == 'SH600079',
         'preserved independently audited original source failure required')
    for label, case in audit['profiles'].items():
        for name, expected in case['failure_artifact_sha256'].items():
            bind(safe(base / old.OUTPUT / label, name), expected)
    primary = base / PRIMARY
    manifest = read(primary / 'manifest.json')
    need(manifest == read(repo / PRIMARY_MANIFEST), 'identical frozen public/local primary manifest required')
    evidence = read(repo / EVIDENCE)
    authenticate_primary(evidence, manifest, primary, bind)
    need({s['instrument'] for s in evidence['state_intervals']} <= set(inputs['packets']),
         'issuer proof outside complete authenticated source universe')
    # State assertions agree with every original source row in the declared
    # experiment clip. No bar, target or raw history is rewritten.
    for state in evidence['state_intervals']:
        bars = inputs['raw_bars'][state['instrument']]
        for day in inputs['sessions']:
            if state['effective_from'] <= day <= state['effective_through']:
                need(bars[day]['isST'] == '1', 'source state conflicts with original issuer state proof')
    inputs.update(plan=plan, regime_evidence=evidence, known_hashes=known,
        failed_prefix={cost: {'case': read(base / old.OUTPUT / str(cost) / 'partial_case.json'),
                            'state': read(base / old.OUTPUT / str(cost) / 'failed_account_state.json')}
                       for cost in old.COSTS})
    verify_hashes(known)
    return inputs


def make_source_view(inputs):
    audit = []
    def source_view(bars, day, required, lifecycles, *, evidence, as_of):
        d = day.isoformat()
        visible = {c: rows for c, rows in bars.items()
                   if c in inputs['old_codes'] or d > old.PRE or d == old.PRE and c in inputs['boundary_codes']}
        need(set(required) <= set(visible), 'future-only issuer used before its frozen account source boundary')
        accepted, exceptions, regimes = regime_source_rows_on(visible, day, required, lifecycles,
                                                             evidence=evidence, as_of=as_of)
        for row in exceptions:
            if row not in audit:
                audit.append(deepcopy(row))
        return accepted, exceptions, regimes
    return source_view, audit


def require_failed_financial_prefix(case, prior):
    trace, state = prior['case'], prior['state']
    cut, n = '2026-03-31', len(trace['rows'])
    need(n == 541 and len(trace['intents']) == 27, 'complete original failed prefix required')
    need(clean(case['days'][:n]) == trace['rows']
         and clean([r for r in case['intents'] if r['execution_session'] < cut]) == trace['intents']
         and clean({d: q for d, q in case['ownership'].items() if d < cut}) == trace['ownership']
         and clean([r for r in case['fills'] if r['execution_at'][:10] < cut]) == state['fills']
         and clean([r for r in case['corporate_ledger'] if str(r['day']) < cut]) == state['corporate_ledger'],
         'new regime replay changed the preserved541day/27intent financial prefix')
    return {'old541_financial_days_and27_intents_identical': True, 'old_failure_relabelled_success': False}


def validate_case(case, checkpoint, inputs, cost):
    need([r['day'] for r in case['days']] == inputs['sessions']
         and [r['execution_session'] for r in case['intents']] == sorted(inputs['targets'])
         and len(case['intents']) == 34 and case['whole_day_volume_violations'] == 0,
         'complete676days/34decisions and no whole-day capacity violation required')
    old.verify_prefix(case, checkpoint, inputs['references'][cost], inputs['old_scope'])
    prefix = require_failed_financial_prefix(case, inputs['failed_prefix'][cost])
    # Keep the old independently checked Decimal reconstruction of every
    # cash, T+1 lot, entitlement, claim, fee and daily asset value.
    old.reconcile_case(case, inputs['events'], inputs['bars'], inputs['sessions'], cost)
    need(len(case['phase_audit']) == 4 * len(inputs['sessions'])
         and len(case['regime_audit']) == 4 * len(inputs['sessions']), 'all daily phase/regime audits required')
    need(not any(o['action'] == 'BUY' and o['status'] == 'FILLED'
                 and any(s['instrument'] == o['security_id']
                         and s['effective_from'] <= o['eligible_at'][:10] <= s['effective_through']
                         for s in inputs['regime_evidence']['state_intervals']) for o in case['orders']),
         'unsigned risk-warning account must not gain a new ST buy fill')
    return prefix


def postcheck(inputs, callback):
    result = {'all_bound_inputs_unchanged': False, 'source_authentication_repeated': False, 'errors': []}
    try:
        callback()
        result['source_authentication_repeated'] = True
    except BaseException as error:
        result['errors'].append({'check': 'source_authentication', 'error_type': type(error).__name__, 'error': str(error)})
    try:
        verify_hashes(inputs['known_hashes'])
        result['all_bound_inputs_unchanged'] = True
    except BaseException as error:
        result['errors'].append({'check': 'bound_byte_hashes', 'error_type': type(error).__name__, 'error': str(error)})
    result['completed'] = not result['errors']
    return result


def finalize_returns(results, cases, postcheck_ok, scorer):
    if (not postcheck_ok or set(results) != {'20', '40'} or set(cases) != {20, 40}
            or any(r['status'] != 'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED' for r in results.values())):
        return False
    # A second-profile scoring failure must not publish a first-profile ROI.
    computed = {cost: scorer(cases[cost]) for cost in old.COSTS}
    for cost in old.COSTS:
        results[str(cost)].update(computed[cost], portfolio_returns_computed=True)
    return True


def run_profiles(out, inputs, *, check_sources, simulator=None, validator=validate_case, scorer=old.annual_returns):
    out = Path(out)
    need(not out.exists() and not out.is_symlink(), 'preserve old and current account output; no resume/overwrite')
    need(out.name == OUTPUT, 'fixed new output directory required')
    verify_hashes(inputs['known_hashes'])
    out.mkdir(parents=True)
    results, cases = {}, {}
    simulate = simulator or simulate_regime_fixed_targets
    Account = old.checkpoint_account_type()
    interrupted = None
    first_failure = None
    persistence_errors = []
    def persist(path, value, *, exclusive=True):
        nonlocal interrupted
        try:
            if exclusive and Path(path).exists():
                return
            (write if exclusive else old.write_json)(path, value)
        except BaseException as error:
            failure = {'stage': 'OUTPUT_PERSISTENCE', 'file': Path(path).name,
                       'error_type': type(error).__name__, 'error': str(error)}
            persistence_errors.append(failure)
            # Diagnostic writes cannot replace the actual simulation error.
            interrupted = interrupted or deepcopy(first_failure) or failure
    try:
        write(out / 'input-before.json', inputs['known_hashes'])
        for cost in old.COSTS:
            folder = out / str(cost)
            folder.mkdir()
            holders, case = [], None
            source_view, source_audit = make_source_view(inputs)
            def factory(calendar, cash, distributions, **kwargs):
                account = Account(calendar, cash, distributions,
                    broker_factory=partial(ExecutionCostBroker, extra_cost_bps=cost), **kwargs)
                holders.append(account)
                return account
            try:
                case = simulate(inputs['calendar'], inputs['bars'], inputs['events'], inputs['targets'], old.CAPITAL,
                    lifecycles={}, regime_evidence=inputs['regime_evidence'], account_factory=factory,
                    policy_id=old.POLICY, source_rows=source_view)
                checkpoint = getattr(holders[0], 'pre2026_checkpoint', None)
                preserved = validator(case, checkpoint, inputs, cost)
                artifacts = old.write_case(folder, case, checkpoint)
                for name, value in (('regime_audit.json', case['regime_audit']),
                                    ('phase_audit.json', case['phase_audit']), ('preserved_failure_prefix.json', preserved)):
                    write(folder / name, value)
                    artifacts[name] = sha(folder / name)
                results[str(cost)] = {'status': 'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED',
                    'portfolio_returns_computed': False, 'artifact_sha256': artifacts,
                    'all676_daily_conservation_checks_pass': True,
                    'old6_financial_and241_scope_prefixes_identical': True,
                    'old541_days_and27_intents_preserved': True}
                cases[cost] = case
            except BaseException as error:
                first_failure = first_failure or {'error_type': type(error).__name__, 'error': str(error)}
                if not isinstance(error, Exception):
                    interrupted = deepcopy(first_failure)
                failure_engine = simulate if hasattr(simulate, '__code__') else simulate_regime_fixed_targets
                try:
                    results[str(cost)] = old.preserve_failure(folder, error, holders, failure_engine, source_audit, case)
                except BaseException as persistence_error:
                    results[str(cost)] = {'status': 'INVALID_SOURCE_OR_ACCOUNT',
                        'error_type': type(error).__name__, 'error': str(error),
                        'portfolio_returns_computed': False,
                        'failure_persistence_error': {'error_type': type(persistence_error).__name__,
                                                      'error': str(persistence_error)}}
                results[str(cost)]['original_traceback'] = ''.join(traceback.format_exception(error))
                persist(out / 'first-error.json', results[str(cost)])
            finally:
                persist(out / 'case_results.json', results, exclusive=False)
            if interrupted:
                break
    except BaseException as error:
        first_failure = first_failure or {'error_type': type(error).__name__, 'error': str(error)}
        interrupted = interrupted or deepcopy(first_failure)
        persist(out / 'first-error.json', first_failure)
    finally:
        for cost in old.COSTS:
            results.setdefault(str(cost), {'status': 'NOT_RUN_AFTER_INTERRUPTION', 'portfolio_returns_computed': False})
        checked = postcheck(inputs, check_sources)
        persist(out / 'input-postcheck.json', checked)
        persist(out / 'case_results.json', results, exclusive=False)
        checked['persistence_errors'] = persistence_errors
    unscored_results = deepcopy(results)
    try:
        scored = finalize_returns(results, cases, checked['completed'] and not interrupted, scorer)
    except BaseException as error:
        first_failure = first_failure or {'stage': 'SCORING', 'error_type': type(error).__name__, 'error': str(error)}
        interrupted = interrupted or deepcopy(first_failure)
        persist(out / 'first-error.json', first_failure)
        scored = False
    if scored:
        for cost in old.COSTS:
            rows = [r for r in cases[cost]['days'] if r['day'] >= '2024-01-02']
            peak, drawdown = Decimal(old.CAPITAL), Decimal(0)
            for row in rows:
                peak = max(peak, row['equity'])
                drawdown = min(drawdown, row['equity'] / peak - 1)
            results[str(cost)].update(status='CONTINUOUS_DAILY_PROXY_RECONCILED',
                average_exposure_pct=float(sum((r['exposure'] for r in rows), Decimal(0)) / len(rows) * 100),
                max_drawdown_pct=float(drawdown * 100))
    persist(out / 'case_results.json', results, exclusive=False)
    if scored and persistence_errors:
        results = unscored_results
        scored = False
        persist(out / 'case_results.json', results, exclusive=False)
    return results, checked, scored, interrupted


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--source-preflight-only', action='store_true')
    args = parser.parse_args(argv)
    base, repo, out = Path(args.source_root), Path(__file__).resolve().parents[1], Path(args.output_dir)
    need(not out.exists() and out.resolve() == (base / OUTPUT).resolve(), 'fixed new output; preserve old failure')
    inputs = load_inputs(base, repo, args.plan, args.expected_plan_sha256)
    if args.source_preflight_only:
        print('frozen source/events/60financials/oldfailure/SSEepochs verified; no account or ROI')
        return 0
    def check_sources():
        refreshed = load_inputs(base, repo, args.plan, args.expected_plan_sha256)
        need(refreshed['known_hashes'] == inputs['known_hashes'], 'source binding set changed')
    results, checked, scored, interrupted = run_profiles(out, inputs, check_sources=check_sources)
    summary = {'status': 'UNCHANGED_PRICE_DELAY_SSE_REGIME_DAILY_HORIZON_RECORDED',
        'plan_sha256': args.expected_plan_sha256, 'candidate': old.POLICY,
        'window': [old.START, old.END], 'initial_CNY': old.CAPITAL, 'reference_extra_bps': 40,
        'results_by_extra_bps': results, 'postcheck': checked,
        'all_profiles_complete_before_returns': scored, 'interrupted': interrupted,
        'execution_model': 'DAILY_PROXY_ONLY', 'allocator': 'plan_integer_targets',
        'risk_warning_buy_permission': False, 'source_queries': 0,
        'investment_rule_changed': False, 'old_failure_relabelled_success': False,
        'old60_financial_files_unchanged': checked['completed'],
        'full_October_2026_complete': False, 'sealed_2026_evidence_claimed': False,
        'historical_arrival_verified': False, 'queue_and_impact_calibrated': False,
        'actual_FIFO_tax_liability_verified': False, 'candidate_promoted': False, 'objective_achieved': False}
    write(out / 'summary.json', summary)
    return 0 if scored else 2


if __name__ == '__main__':
    raise SystemExit(main())
