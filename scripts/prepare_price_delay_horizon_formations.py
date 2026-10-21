"""Frozen forward application of one policy, without computing portfolio ROI."""
import argparse
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.run_qlib_low_risk_pre2026 import input_hashes, parse_memberships
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from stock_rsi.price_delay_horizon import build_targets
from stock_rsi.qlib_snapshot import QlibSnapshot

OUTPUT = 'price-delay-horizon-formations-20261021'
PROVIDER = 'qlib-enhanced-dev'
PRE_PROVIDER = 'qlib-price-delay-pre2026-20261021'
OLD_FORMATIONS = 'price-delay-pre2026-formations-20261021'
OLD_RUN = 'price-delay-intraday-pre2026-20261021'
PRE_END = '2025-12-31'
PRE_REQUEST = 'experiments/qlib/price-delay-provider-pre2026-request.json'
OLD_REQUEST = 'experiments/qlib/price-delay-pre2026-formation-request.json'
OLD_PLAN = 'experiments/qlib/price-delay-intraday-plan.json'
AUDIT = 'experiments/qlib/price-delay-intraday-independent-ledger-audit.json'
METHOD_FILES = ('scripts/prepare_price_delay_horizon_formations.py',
    'src/stock_rsi/price_delay_horizon.py', 'src/stock_rsi/price_delay.py',
    'src/stock_rsi/prior_close_orders.py', 'src/stock_rsi/qlib_snapshot.py',
    'scripts/run_qlib_low_risk_pre2026.py', 'scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/prepare_qlib_master_market_pre2026.py', 'scripts/fundamental_query_journal.py')
PUBLIC_FILES = (OLD_PLAN, AUDIT, PRE_REQUEST, OLD_REQUEST,
    'experiments/qlib/price-delay-intraday-results.json',
    'experiments/qlib/price-delay-intraday-verification.json',
    'experiments/qlib/price-delay-intraday-output-review.json',
    'docs/research/price-delay-horizon-formation-plan-2026-10-21.md')
LOCAL_FILES = (PROVIDER + '/calendars/day.txt', PRE_PROVIDER + '/manifest.json',
    OLD_FORMATIONS + '/targets.json', OLD_FORMATIONS + '/formation_receipts.json',
    OLD_RUN + '/summary.json')
BINDINGS = (('method_code_sha256', METHOD_FILES), ('public_evidence_sha256', PUBLIC_FILES),
            ('local_source_sha256', LOCAL_FILES))
ARTIFACTS = ('daily.csv', 'intents.json', 'parent_instructions.json', 'orders.json',
             'fills.json', 'corporate_ledger.json', 'ownership.json', 'source_scope_audit.json')
FINANCIAL_FILES = tuple(f'{OLD_RUN}/{p}/{c}/{n}' for p in (100, 500, 1000)
                        for c in (20, 40) for n in ARTIFACTS)
PROFILE = {'status': 'FROZEN_PRICE_DELAY_HORIZON_FORMATIONS_NO_RETURNS',
    'candidate': 'price_delay_d1', 'candidate_budget': 1, 'window': ['2024-01-02', '2026-10-20'],
    'provider_relative': PROVIDER, 'source_calendar_end': '2026-10-13', 'output_relative': OUTPUT,
    'formation_count': 34, 'original_formation_count': 24, 'network_calls_permitted': 0,
    'investment_rule_changes_permitted': False, 'portfolio_returns_to_compute': False,
    'nonselectable_controls_remain_nonselectable': True, 'full_October_2026_complete': False}


def read(path):
    return json.loads(Path(path).read_text())


def immutable_financial_hashes(base):
    result = {}
    summary = read(base / OLD_RUN / 'summary.json')
    cases = summary['results_by_profile']
    if set(cases) != {f'{p}/{c}' for p in (100, 500, 1000) for c in (20, 40)}:
        raise ValueError('complete six original accounts required')
    for label, case in cases.items():
        if case['status'] != 'NESTED_EXECUTION_ACCOUNT_RECONCILED' or set(case['artifact_sha256']) != set(ARTIFACTS):
            raise ValueError('all original eight-artifact accounts required')
        result.update({OLD_RUN + '/' + label + '/' + n: h for n, h in case['artifact_sha256'].items()})
    return result


def validate_contract(plan, base, out, financial):
    if (any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in PROFILE.items())
            or any(set(plan[field]) != set(names) for field, names in BINDINGS)
            or set(financial) != set(FINANCIAL_FILES)
            or plan['immutable_financial_sha256'] != financial
            or Path(out).resolve() != (Path(base) / OUTPUT).resolve()):
        raise ValueError('one unchanged policy, fixed source scope and all48 financial anchors required')


def require_original_prefix(targets, receipts, old_targets, old_receipts):
    prefix = {name: {d: t for d, t in values.items() if d <= PRE_END} for name, values in targets.items()}
    if prefix != old_targets or [r for r in receipts if r['execution_session'] <= PRE_END] != old_receipts:
        raise ValueError('original targets and regression receipts must be identical')


def load_inputs(base, repo, plan, out):
    financial = immutable_financial_hashes(base)
    validate_contract(plan, base, out, financial)
    for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                        ('local_source_sha256', base), ('immutable_financial_sha256', base)):
        for name, expected in plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root / name) != expected:
                raise ValueError('frozen source/policy/evidence changed: ' + name)
    old_plan = read(repo / OLD_PLAN)
    for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
        for name, expected in old_plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root / name) != expected:
                raise ValueError('original minute-account input changed: ' + name)
    summary = read(base / OLD_RUN / 'summary.json')
    audit, verification = read(repo / AUDIT), read(repo / PUBLIC_FILES[5])
    review = read(repo / PUBLIC_FILES[6])
    if (summary['raw_development_confirmation_passes'] is not True
            or audit['all_six_profile_ledgers_reconstructed'] is not True
            or audit['development_confirmation_passes_independently'] is not True
            or audit['imports_project_code'] is not False
            or audit['summary_sha256'] != file_sha(base / OLD_RUN / 'summary.json')
            or verification['root_ledger_reproduction_byte_identical'] is not True
            or verification['summary_sha256'] != file_sha(base / OLD_RUN / 'summary.json')
            or verification['independent_ledger_audit_sha256'] != file_sha(repo / AUDIT)
            or review['ready_for_2026_source_design'] is not True):
        raise ValueError('independently passed pre2026 accounts required before new market values')
    old_request = read(repo / OLD_REQUEST)
    for name, expected in old_request['method_code_sha256'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(repo / name) != expected:
            raise ValueError('original formation rule changed')
    provider = base / PROVIDER
    memberships = parse_memberships((provider / 'instruments/csi500.txt').read_text())
    original_source = read(repo / PRE_REQUEST)['source_input_sha256']
    if plan['source_input_sha256'] != original_source or input_hashes(provider, memberships) != original_source:
        raise ValueError('original provider identity changed')
    codes = sorted(c for c, spans in memberships.items()
                   if any(a <= '2026-10-20' and b >= '2023-12-29' for a, b in spans))
    if codes != plan['full_source_codes'] or price_input_digest(provider, codes) != plan['full_price_input_digest']:
        raise ValueError('complete unchanged horizon membership/source hash required')
    calendar = (provider / 'calendars/day.txt').read_text().splitlines()
    if calendar != sorted(set(calendar)) or calendar[-1] != PROFILE['source_calendar_end']:
        raise ValueError('original source calendar end changed; no invented sessions')
    prefix_manifest = read(base / PRE_PROVIDER / 'manifest.json')
    if file_sha(base / PRE_PROVIDER / 'manifest.json') != old_request['provider_manifest_sha256']:
        raise ValueError('original physically capped provider manifest changed')
    for name, meta in prefix_manifest['per_feature'].items():
        clipped = base / PRE_PROVIDER / name
        if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(clipped) != meta['sha256']:
            raise ValueError('original physical pre2026 feature changed')
        with (provider / name).open('rb') as stream:
            if stream.read(clipped.stat().st_size) != clipped.read_bytes():
                raise ValueError('horizon source differs from original physical pre2026 bytes')
    return provider, memberships


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(argv)
    base, repo, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.output_dir)
    if out.exists() or file_sha(a.plan) != a.expected_plan_sha256:
        raise ValueError('preserve previous output and externally frozen request')
    plan = read(a.plan)
    provider, memberships = load_inputs(base, repo, plan, out)
    if a.preflight_only:
        print('unchanged full source identity/pre26 prefix/all48 financials verified; no2026quotes decoded', flush=True)
        return 0
    out.mkdir(parents=True)
    try:
        snapshot = QlibSnapshot(provider)
        targets, receipts = build_targets(snapshot, memberships)
        require_original_prefix(targets, receipts, read(base / OLD_FORMATIONS / 'targets.json'),
                                read(base / OLD_FORMATIONS / 'formation_receipts.json'))
        if (len(receipts) != 34 or len(targets['price_delay_d1']) != 34
                or any(r['latest_measurement_price_read'] > r['measurement_cap']
                       or r['latest_formation_price_read'] != r['formation_asof'] for r in receipts)):
            raise ValueError('34 complete monthly formations with unchanged measurement lag required')
        for name, value in (('targets.json', targets), ('formation_receipts.json', receipts),
                            ('candidate_targets.json', targets['price_delay_d1'])):
            (out / name).write_text(json.dumps(value, indent=2) + '\n')
        result = {'status': 'UNCHANGED_POLICY_HORIZON_FORMATIONS_NO_PORTFOLIO_RETURNS',
            'plan_sha256': a.expected_plan_sha256, 'candidate': 'price_delay_d1', 'formations': 34,
            'original_24_formations_and_receipts_identical': True, 'source_calendar_end': calendar_end(provider),
            'unconditional_interim_observation_end': '2026-10-20', 'full_October_2026_complete': False,
            'artifact_sha256': {n: file_sha(out / n) for n in ('targets.json', 'formation_receipts.json', 'candidate_targets.json')},
            'new_2026_market_values_read': True, 'investment_rule_changed': False,
            'controls_selectable': False, 'portfolio_returns_computed': False,
            'historical_arrival_verified': False, 'strict_OS_future_boundary': False,
            'candidate_promoted': False, 'objective_achieved': False}
        (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        print('34 unchanged policy formations; original24 identical; no portfolioROI', flush=True)
        return 0
    except Exception as exc:
        (out / 'failure.json').write_text(json.dumps({'error_type': type(exc).__name__, 'error': str(exc),
            'plan_sha256': a.expected_plan_sha256, 'new_2026_market_values_may_have_been_read': True,
            'portfolio_returns_computed': False, 'objective_achieved': False}, indent=2) + '\n')
        raise


def calendar_end(provider):
    return (provider / 'calendars/day.txt').read_text().splitlines()[-1]


if __name__ == '__main__':
    raise SystemExit(main())
