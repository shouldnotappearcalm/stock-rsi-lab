"""Apply the frozen IVOL rule only after source and monthly-clock admission.

Calendar insufficiency is a failed application, not permission to alter the
factor or carry a position with an unregistered fallback. No account is run.
"""
import argparse
import json
from datetime import date
from pathlib import Path

from scripts import run_ivol_regime_raw_pre2026 as development
from scripts.prepare_low_market_residual_vol_pre2026 import authenticate
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.run_qlib_low_risk_pre2026 import input_hashes, parse_memberships
from stock_rsi.low_market_residual_vol import FAMILIES, CONTROL, MIN_OBSERVATIONS, _previous_month
from stock_rsi.low_market_residual_vol_horizon import START, END, build_targets
from stock_rsi.qlib_snapshot import QlibSnapshot

read, write, sha, safe = development.read, development.write, development.file_sha, development.safe
OUTPUT = 'low-market-residual-vol1m-horizon-formations-20261021'
PROVIDER = 'qlib-enhanced-dev'
PRE_PROVIDER = 'qlib-price-delay-pre2026-clock-v2-20261021'
OLD_FORMATIONS = 'low-market-residual-vol1m-pre2026-formations-20261021'
OLD_REQUEST = 'experiments/qlib/low-market-residual-vol1m-pre2026-formation-request.json'
OLD_PLAN = 'experiments/qlib/low-market-residual-vol1m-regime-raw-development-request.json'
AUDIT = 'experiments/qlib/low-market-residual-vol1m-regime-independent-account-audit.json'
VERIFICATION = 'experiments/qlib/low-market-residual-vol1m-regime-run-verification.json'
PROTOCOL = 'docs/research/low-market-residual-vol1m-horizon-protocol-2026-10-21.md'
METHOD_FILES = tuple(dict.fromkeys(development.METHOD_FILES + (
    'scripts/prepare_low_market_residual_vol_pre2026.py',
    'src/stock_rsi/low_market_residual_vol.py',
    'src/stock_rsi/low_market_residual_vol_horizon.py',
    'src/stock_rsi/prior_close_orders.py', 'src/stock_rsi/qlib_snapshot.py',
    'scripts/run_qlib_low_risk_pre2026.py',
    'scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/prepare_low_market_residual_vol_horizon_formations.py')))
PUBLIC_FILES = (OLD_REQUEST, OLD_PLAN, AUDIT, VERIFICATION, PROTOCOL)
LOCAL_FILES = (PRE_PROVIDER + '/manifest.json', OLD_FORMATIONS + '/targets.json',
               OLD_FORMATIONS + '/formation_receipts.json', development.OUTPUT + '/summary.json')
BINDINGS = (('method_code_sha256', METHOD_FILES), ('public_evidence_sha256', PUBLIC_FILES),
            ('local_source_sha256', LOCAL_FILES))
PROFILE = {'status': 'FROZEN_UNCHANGED_IVOL_HORIZON_CLOCK_ADMISSION_THEN_FORMATIONS',
    'candidate': FAMILIES[0], 'candidate_budget': 1, 'window': [START, END],
    'provider_relative': PROVIDER, 'source_calendar_end': '2026-10-13',
    'output_relative': OUTPUT, 'required_formations': 34, 'original_formations': 24,
    'network_calls_permitted': 0, 'investment_rule_changes_permitted': False,
    'portfolio_returns_to_compute': False, 'controls_selectable': False,
    'minimum_return_observations': MIN_OBSERVATIONS,
    'on_inadmissible_month': 'FAIL_NO_SKIP_NO_CARRY_NO_PARAMETER_CHANGE',
    'full_October_2026_complete': False, 'sealed_2026_evidence_claimed': False}


def validate_contract(plan, base, out):
    if (any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in PROFILE.items())
            or any(set(plan.get(field, {})) != set(names) for field, names in BINDINGS)
            or Path(out).resolve() != (Path(base) / OUTPUT).resolve()):
        raise ValueError('one unchanged IVOL policy, fixed horizon and fail-closed clock required')


def clock_admission(calendar, start=START, end=END):
    """Check the original factor's calendar conditions without reading quotes.

    This mirrors only the date branches of build_targets. A complete short
    exchange month is still below the frozen n>=15 rule; missing sessions are
    never manufactured. The original factor remains the final formation gate.
    """
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first < date.fromisoformat(START) or last > date.fromisoformat(END) or first > last:
        raise ValueError('fixed horizon cap exceeded')
    days = tuple(calendar)
    if any(type(d) is not date for d in days) or list(days) != sorted(set(days)):
        raise ValueError('ordered unique explicit calendar required')
    months = []
    for i, execution in enumerate(days):
        if not first <= execution <= last:
            continue
        if i == 0:
            months.append({'execution_session': execution.isoformat(), 'admitted': False,
                           'reason': 'missing_previous_source_session'})
            continue
        prior = days[i - 1]
        if (prior.year, prior.month) == (execution.year, execution.month):
            continue
        month = _previous_month(execution)
        j = i - 1
        while j > 0 and (days[j - 1].year, days[j - 1].month) == month:
            j -= 1
        reason = None
        if (prior.year, prior.month) != month:
            reason = 'missing_preceding_complete_natural_month'
        elif j == 0 or (days[j - 1].year, days[j - 1].month) != _previous_month(days[j]):
            reason = 'missing_preceding_month_baseline_close'
        elif i - j < MIN_OBSERVATIONS:
            reason = 'complete_source_month_fewer_than_frozen_15_observations'
        months.append({'execution_session': execution.isoformat(), 'formation_asof': prior.isoformat(),
                       'return_month': f'{month[0]:04d}-{month[1]:02d}',
                       'sample_dates': [d.isoformat() for d in days[j:i]],
                       'n': i - j, 'minimum_return_observations': MIN_OBSERVATIONS,
                       'admitted': reason is None, 'reason': reason})
    return months


def require_original_prefix(targets, receipts, old_targets, old_receipts):
    prefix = {name: {d: t for d, t in values.items() if d <= '2025-12-31'}
              for name, values in targets.items()}
    if prefix != old_targets or [r for r in receipts if r['execution_session'] <= '2025-12-31'] != old_receipts:
        raise ValueError('all original24 targets and factor receipts must be identical')


def load_inputs(base, repo, plan, out):
    base, repo = Path(base).resolve(), Path(repo).resolve()
    validate_contract(plan, base, out)
    known = {}
    def bind(path, expected):
        path = Path(path).resolve()
        if not (path.is_relative_to(base) or path.is_relative_to(repo)):
            raise ValueError('input outside registered source roots')
        if str(path) in known and known[str(path)] != expected:
            raise ValueError('conflicting frozen input checksum')
        if sha(path) != expected:
            raise ValueError('frozen input changed: ' + str(path))
        known[str(path)] = expected
    for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                        ('local_source_sha256', base)):
        for name, expected in plan[field].items():
            bind(safe(root, name), expected)
    # Authenticate the completed development proof and all of its source,
    # primary documents, old financial files and preserved failure outputs.
    ctx = development.load_inputs(base, repo, repo / OLD_PLAN, plan['public_evidence_sha256'][OLD_PLAN])
    for name, expected in ctx['known_hashes'].items():
        bind(name, expected)
    audit, verification = read(repo / AUDIT), read(repo / VERIFICATION)
    summary = read(base / development.OUTPUT / 'summary.json')
    if (audit['status'] != 'PASS_INDEPENDENT_REGIME_DAILY_ACCOUNT_AUDIT'
            or audit['critical_or_important_findings']
            or audit['both_profiles_complete'] is not True
            or audit['all_profile_daily_ledgers_independently_reconstructed'] is not True
            or audit['imports_project_code'] is not False
            or verification['root_reproduced_independent_audit_byte_identically'] is not True
            or verification['independent_account_audit_sha256'] != sha(repo / AUDIT)
            or summary['raw_daily_proxy_development_gate_passes'] is not True
            or audit['summary_sha256'] != sha(base / development.OUTPUT / 'summary.json')
            or verification['summary_sha256'] != audit['summary_sha256']):
        raise ValueError('independently completed original two-profile development required')
    if audit['all_output_file_sha256'] != verification['all_output_file_sha256']:
        raise ValueError('complete original26 output identity required')
    for name, expected in audit['all_output_file_sha256'].items():
        bind(safe(base / development.OUTPUT, name), expected)
    old_request = read(repo / OLD_REQUEST)
    authenticate(base / PRE_PROVIDER, repo, old_request)  # Physically capped; no 2026 values.
    manifest = read(base / PRE_PROVIDER / 'manifest.json')
    provider = base / PROVIDER
    memberships = parse_memberships((provider / 'instruments/csi500.txt').read_text())
    if (plan['source_input_sha256'] != manifest['source_input_sha256']
            or input_hashes(provider, memberships) != plan['source_input_sha256']):
        raise ValueError('original full provider identity changed')
    for name, expected in plan['source_input_sha256'].items():
        if name != 'price_files':
            bind(safe(provider, name), expected)
    codes = sorted(c for c, spans in memberships.items()
                   if any(a <= END and b >= '2023-12-29' for a, b in spans))
    if codes != plan['full_source_codes'] or price_input_digest(provider, codes) != plan['full_price_input_digest']:
        raise ValueError('complete horizon source/membership hash changed')
    for name, meta in manifest['per_feature'].items():
        clipped, full = safe(base / PRE_PROVIDER, name), safe(provider, name)
        bind(clipped, meta['sha256'])
        with full.open('rb') as stream:
            if stream.read(clipped.stat().st_size) != clipped.read_bytes():
                raise ValueError('full provider differs from original physical prefix')
    calendar = tuple(date.fromisoformat(d) for d in (provider / 'calendars/day.txt').read_text().splitlines())
    if not calendar or calendar[-1].isoformat() != PROFILE['source_calendar_end']:
        raise ValueError('explicit source calendar end changed')
    clock = clock_admission(calendar)
    if len(clock) != 34 or sum(r['execution_session'] <= '2025-12-31' for r in clock) != 24:
        raise ValueError('complete34 monthly clock boundaries required')
    return provider, memberships, clock, known


def run_formations(provider, memberships, clock, out):
    """The denial branch must not construct or decode a full QlibSnapshot."""
    denied = [row for row in clock if not row['admitted']]
    write(out / 'clock_admission.json', clock)
    if denied:
        write(out / 'failure.json', {'status': 'UNCHANGED_IVOL_CLOCK_ADMISSION_FAILED',
              'denied_months': denied, 'new_2026_quote_values_decoded': False,
              'full_provider_snapshot_constructed': False, 'targets_generated': False,
              'portfolio_returns_computed': False, 'investment_rule_changed': False,
              'fallback_added': False, 'objective_achieved': False})
        return 2, None
    targets, receipts = build_targets(QlibSnapshot(provider), memberships)
    if (len(receipts) != 34 or set(targets) != {FAMILIES[0], 'eligible_equal_weight', CONTROL}
            or any(len(t) != 34 for t in targets.values())
            or any(r['latest_factor_price_read'] != r['formation_asof']
                   or r['formation_asof'] >= r['execution_session'] for r in receipts)):
        raise ValueError('complete34 unchanged bounded factor formations required')
    return 0, (targets, receipts)


def postcheck_inputs(base, repo, plan, out, clock, known, plan_path):
    """Attempt both checks even after an interruption; never mask its cause."""
    result = {'all_bound_inputs_unchanged': False,
              'full_provider_identity_and_pre2026_prefix_rechecked': False, 'errors': []}
    try:
        _, _, after_clock, after = load_inputs(base, repo, plan, out)
        expected = {k: v for k, v in known.items() if k != str(Path(plan_path).resolve())}
        if after_clock != clock or after != expected:
            raise ValueError('source/clock/evidence changed during application')
        result['full_provider_identity_and_pre2026_prefix_rechecked'] = True
    except BaseException as error:
        result['errors'].append({'check': 'complete_source_and_clock',
                                 'error_type': type(error).__name__, 'error': str(error)})
    try:
        development.verify_inputs(known)
        result['all_bound_inputs_unchanged'] = True
    except BaseException as error:
        result['errors'].append({'check': 'all_bound_input_hashes',
                                 'error_type': type(error).__name__, 'error': str(error)})
    result['completed'] = not result['errors']
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args(argv)
    base, repo, out = Path(args.source_root), Path(__file__).resolve().parents[1], Path(args.output_dir)
    if out.exists() or out.is_symlink() or sha(args.plan) != args.expected_plan_sha256:
        raise ValueError('preserve output and externally frozen plan')
    plan = read(args.plan)
    provider, memberships, clock, known = load_inputs(base, repo, plan, out)
    known[str(Path(args.plan).resolve())] = args.expected_plan_sha256
    if args.preflight_only:
        print('source bytes, original accounts and monthly clock authenticated; no2026 quote decoding')
        return 0
    out.mkdir(parents=True)
    decoded = False
    try:
        write(out / 'input-before.json', known)
        exit_code, formed = run_formations(provider, memberships, clock, out)
        if formed is not None:
            decoded = True
            targets, receipts = formed
            require_original_prefix(targets, receipts, read(base / OLD_FORMATIONS / 'targets.json'),
                                    read(base / OLD_FORMATIONS / 'formation_receipts.json'))
            write(out / 'targets.json', targets)
            write(out / 'formation_receipts.json', receipts)
        # Full source identities and complete pre2026 financial evidence are
        # checked again on success or a declared calendar denial.
        post = postcheck_inputs(base, repo, plan, out, clock, known, args.plan)
        write(out / 'input-postcheck.json', post)
        if not post['completed']:
            raise ValueError('source postcheck failed; retain account/source evidence and original failure')
        write(out / 'summary.json', {
            'status': 'UNCHANGED_IVOL_HORIZON_FORMATIONS_ONLY' if formed else 'UNCHANGED_IVOL_CLOCK_ADMISSION_FAILED',
            'plan_sha256': args.expected_plan_sha256, 'actual_exit_code': exit_code,
            'candidate': FAMILIES[0], 'candidate_budget': 1, 'clock_months_checked': len(clock),
            'denied_months': [row for row in clock if not row['admitted']],
            'source_calendar_end': PROFILE['source_calendar_end'], 'interim_observation_end': END,
            'full_October_2026_complete': False, 'investment_rule_changed': False,
            'new_2026_quote_values_decoded': decoded, 'targets_generated': formed is not None,
            'portfolio_returns_computed': False, 'all_original_financial_evidence_preserved': True,
            'all_bound_inputs_unchanged': True, 'bound_input_count': len(known),
            'sealed_2026_evidence_claimed': False, 'historical_arrival_verified': False,
            'strict_OS_future_boundary': False, 'objective_achieved': False,
            'artifact_sha256': {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}})
        print('unchanged factor clock denied; no2026 quote decoding or portfolioROI' if exit_code else
              '34 unchanged factor formations; original24 identical; no portfolioROI', flush=True)
        return exit_code
    except BaseException as error:
        terminal = {'error_type': type(error).__name__, 'error': str(error),
            'new_2026_quote_values_may_have_been_decoded': decoded or not any(not r['admitted'] for r in clock),
            'portfolio_returns_computed': False, 'objective_achieved': False,
            'source_postcheck_after_original_error': postcheck_inputs(base, repo, plan, out, clock, known, args.plan)}
        # Persistence errors are recorded where possible but never replace the
        # first exception, including KeyboardInterrupt and source mismatch.
        try:
            write(out / 'error-input-postcheck.json', terminal['source_postcheck_after_original_error'])
        except BaseException as persistence_error:
            terminal['postcheck_persistence_error'] = {'error_type': type(persistence_error).__name__,
                                                       'error': str(persistence_error)}
        try:
            write(out / 'terminal-error.json', terminal)
        except BaseException:
            pass
        raise


if __name__ == '__main__':
    raise SystemExit(main())
