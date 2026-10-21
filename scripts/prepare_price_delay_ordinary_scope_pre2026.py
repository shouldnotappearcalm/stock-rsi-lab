"""Authenticate only ordinary minute packets; require separate account proof.

The original 2,502-sample admission remains failed. No ST tape is admitted,
source rewritten, account replayed or portfolio return computed here.
"""
import argparse
import json
from pathlib import Path

from scripts import admit_price_delay_minutes_pre2026 as admission
from scripts.fundamental_query_journal import file_sha
from scripts.run_low_beta60_intraday_development import CompletePrefixTapeBank

FAILED = 'price-delay-minute-admission-20261021'
OUTPUT = 'price-delay-ordinary-source-scope-20261021'
PLAN = 'experiments/qlib/price-delay-minute-admission-plan.json'
AUDIT = 'experiments/qlib/price-delay-minute-admission-independent-audit.json'
METHOD_FILES = tuple(dict.fromkeys((*admission.METHOD_FILES,
    'scripts/prepare_price_delay_ordinary_scope_pre2026.py',
    'scripts/run_low_beta60_intraday_development.py', 'scripts/run_low_risk_intraday_replay.py',
    'src/stock_rsi/ordinary_source_scope.py', 'scripts/replay_ordinary_stock_distribution_targets.py')))
PUBLIC_FILES = (PLAN, AUDIT,
    'experiments/qlib/price-delay-minute-admission-summary.json',
    'experiments/qlib/price-delay-minute-admission-verification.json',
    'experiments/qlib/audit_sources/2026-10-21-price-delay-minute-admission-audit.py',
    'experiments/qlib/price-delay-ordinary-scope-code-review.json',
    'experiments/qlib/price-delay-ordinary-scope-preparation-verification.json',
    'docs/research/price-delay-ordinary-source-admission-plan-2026-10-21.md')
LOCAL_FILES = (FAILED + '/summary.json', FAILED + '/details.json',
               admission.CAPTURE + '/manifest.json')
BINDINGS = (('method_code_sha256', METHOD_FILES), ('public_evidence_sha256', PUBLIC_FILES),
            ('local_source_sha256', LOCAL_FILES))
PROFILE = {'status': 'FROZEN_PRICE_DELAY_ORDINARY_SOURCE_SCOPE', 'candidate': 'price_delay_d1',
    'window': ['2024-01-02', '2025-12-31'], 'ordinary_packets': 2490,
    'rejected_packets': 12, 'nonordinary_daily_intervals': 241, 'nonexecuting_halt_intervals': 2,
    'network_calls_permitted': 0, 'account_dependency_guard_required': True,
    'original_strict_admission_remains_failed': True, 'new_2026_values_read': False,
    'portfolio_returns_computed': False, 'objective_achieved': False, 'output_relative': OUTPUT}


def read(path):
    return json.loads(Path(path).read_text())


def validate_plan(plan, base, out):
    if (any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in PROFILE.items())
            or any(set(plan[field]) != set(names) for field, names in BINDINGS)
            or Path(out).resolve() != (Path(base) / OUTPUT).resolve()):
        raise ValueError('fixed ordinary scope and guard requirement must be preserved')


class OrdinaryScopeTapeBank(CompletePrefixTapeBank):
    """Keep original packet bytes, but never expose rejected ST identities."""
    def __init__(self, capture, bars, scope):
        super().__init__(capture, bars)
        ordinary = scope['ordinary_packet_sha256']
        rejected = scope['rejected_packet_sha256']
        original = {c + '-' + d + '.json': h for (c, d), (_, h) in self.index.items()}
        if (set(ordinary) & set(rejected) or {**ordinary, **rejected} != original):
            raise ValueError('complete disjoint original packet partition required')
        for (code, day), (_, h) in self.index.items():
            name = code + '-' + day + '.json'
            state = bars[code][day]['isST']
            if ((name in ordinary and state != '0') or (name in rejected and state != '1')):
                raise ValueError('nonordinary tape may not enter the executable index')
        self.index = {key: value for key, value in self.index.items()
                      if key[0] + '-' + key[1] + '.json' in ordinary}


def authenticate_sources(base, repo, plan):
    for field, parent in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                          ('local_source_sha256', base)):
        for name, expected in plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(parent / name) != expected:
                raise ValueError('frozen conditional scope input changed: ' + name)
    original = read(repo / PLAN)
    admission.validate_admission_plan(original, base, base / FAILED)
    for field, parent in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                          ('local_source_sha256', base)):
        for name, expected in original[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(parent / name) != expected:
                raise ValueError('original strict-admission input changed: ' + name)
    failed = base / FAILED
    summary, details, audit = read(failed / 'summary.json'), read(failed / 'details.json'), read(repo / AUDIT)
    if (summary['admitted_for_reconstructed_execution'] is not False
            or summary['plan_sha256'] != file_sha(repo / PLAN)
            or summary['status_counts'] != {'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE': 2490, 'SOURCE_REJECTED': 12}
            or summary['details_sha256'] != file_sha(failed / 'details.json')
            or audit['admission_summary_sha256'] != file_sha(failed / 'summary.json')
            or audit['admission_details_sha256'] != file_sha(failed / 'details.json')
            or audit['failed_admission_correctly_preserved'] is not True
            or audit['all2502_details_and_entire_summary_reconstructed'] is not True
            or audit['imports_project_code'] is not False
            or audit['audit_code_sha256'] != file_sha(repo / PUBLIC_FILES[4])
            or not isinstance(audit['semantic_negative_controls_rejected'], dict)
            or len(audit['semantic_negative_controls_rejected']) < 4
            or any(v is not True for v in audit['semantic_negative_controls_rejected'].values())):
        raise ValueError('independently reconstructed strict failure must remain unchanged')
    request, capture_plan = read(repo / admission.RQ), read(repo / admission.CP)
    reused, fresh = admission.authenticate(base, repo, request, capture_plan)
    capture = base / admission.CAPTURE
    manifest, cleanup = read(capture / 'manifest.json'), read(capture / 'client_cleanup.json')
    if not admission.verify_capture_scope(read(capture / 'price-delay-scope.json'), manifest, cleanup,
            capture_plan_sha256=file_sha(repo / admission.CP), request_sha256=file_sha(repo / admission.RQ),
            manifest_sha256=file_sha(capture / 'manifest.json'), cleanup_sha256=file_sha(capture / 'client_cleanup.json')):
        raise ValueError('original source cleanup failed')
    admission.verify_journal_bytes(capture, read(repo / admission.AUDIT))
    raw = base / admission.RAW
    rm = read(raw / 'manifest.json')
    bars = {code: {r['date']: r for r in read(raw / 'codes' / (code + '.json'))['bars']}
            for code in rm['per_code_sha256']}
    nonordinary = []
    for code, days in sorted(bars.items()):
        for day, row in sorted(days.items()):
            if type(row['isST']) is not str or row['isST'] not in ('0', '1'):
                raise ValueError('unknown original source state')
            if row['isST'] == '1':
                nonordinary.append({'instrument': code, 'day': day, 'source_isST': '1',
                    'tradestatus': row['tradestatus'], 'account_dependency_proven_absent': False})
    rows = details['sessions']
    if ([ [r['instrument'], r['day']] for r in rows] != request['active_requests']
            or details['nonexecuting_source_intervals'] != request['nonexecuting_source_intervals']):
        raise ValueError('entire original source inventory required')
    ordinary, rejected = {}, {}
    for row in rows:
        code, day = row['instrument'], row['day']
        name = code + '-' + day + '.json'
        path = capture / 'sessions' / name
        h = file_sha(path)
        if h != manifest['per_session_sha256'][name] or h != row['source_sha256']:
            raise ValueError('original source packet changed')
        packet = read(path)
        if name in reused:
            if row['origin'] != reused[name] or h != reused[name]['sha256']:
                raise ValueError('original reused source route changed')
        else:
            if row['origin'] != 'FROZEN_FRESH_QUERY':
                raise ValueError('original fresh route changed')
            admission.verify_query_receipt(capture, code, day, packet, capture_plan['host'])
        daily = bars[code][day]
        if daily['isST'] == '0':
            result = admission.inspect_packet(code, day, packet, daily)
            if any(row.get(k) != v for k, v in result.items()):
                raise ValueError('ordinary sample differs from independently audited admission')
            ordinary[name] = h
        else:
            if (code != 'SZ002092' or daily['tradestatus'] != '1' or row['status'] != 'SOURCE_REJECTED'
                    or row['error_type'] != 'ValueError'
                    or row['error'] != 'source security/date/ordinary active state changed'):
                raise ValueError('original ST rejection cannot be promoted or erased')
            rejected[name] = h
    if (len(ordinary) != 2490 or len(rejected) != 12 or len(nonordinary) != 241
            or summary['exceptions'] != [r for r in rows if r['status'] == 'SOURCE_REJECTED']):
        raise ValueError('fixed ordinary/rejected scope changed')
    scope = {'ordinary_packet_sha256': ordinary, 'rejected_packet_sha256': rejected,
             'nonordinary_source_intervals': nonordinary,
             'nonexecuting_halt_intervals': request['nonexecuting_source_intervals']}
    bank = OrdinaryScopeTapeBank(capture, bars, scope)
    if len(bank.index) != 2490 or len(fresh) != 918:
        raise ValueError('ordinary-only tape index required')
    return scope


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(argv)
    base, repo, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.output_dir)
    if out.exists():
        raise ValueError('preserve prior conditional source scope')
    if file_sha(a.plan) != a.expected_plan_sha256:
        raise ValueError('conditional source scope plan changed')
    plan = read(a.plan)
    validate_plan(plan, base, out)
    scope = authenticate_sources(base, repo, plan)
    if a.preflight_only:
        print('2490 ordinary,12 rejected,241 ST intervals authenticated; no account/ROI/network', flush=True)
        return 0
    out.mkdir(parents=True)
    (out / 'scope.json').write_text(json.dumps(scope, indent=2) + '\n')
    result = {'status': 'ORDINARY_SOURCE_SCOPE_PREPARED_ACCOUNT_PROOF_REQUIRED',
        'plan_sha256': a.expected_plan_sha256, 'method_code_sha256': plan['method_code_sha256'],
        'scope_sha256': file_sha(out / 'scope.json'), 'ordinary_packets_content_verified': 2490,
        'rejected_packets_retained': 12, 'nonordinary_daily_intervals': 241,
        'original_strict_admission_remains_failed': True, 'account_dependency_guard_required': True,
        'all_account_dependencies_ordinary_proven': False, 'admitted_for_unconditional_execution': False,
        'new_2026_values_read': False, 'portfolio_returns_computed': False, 'objective_achieved': False}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print('ordinary source scope prepared; actual account dependency proof still required', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
