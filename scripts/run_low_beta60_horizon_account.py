"""Six fixed continuous accounts through Oct20; no strategy mutation or source calls."""
import argparse
import csv
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import partial
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.run_low_beta60_intraday_development_v2 import METHOD_FILES as PRIOR_METHODS, SourceIOGuard
from scripts.run_low_beta60_intraday_development import PARTICIPATION, EXTRA_BPS, CAPITAL
from scripts.run_low_risk_intraday_replay import TapeBank, write_case
from scripts.run_low_risk_raw_share_validation import clean
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistribution, StockDistributionAccount

END = '2026-10-20'
OUTPUT = 'low-beta60-intraday-horizon-20261021'
METHOD_FILES = (*PRIOR_METHODS, 'scripts/run_low_beta60_horizon_account.py', 'scripts/prepare_low_beta60_horizon_events.py',
    'src/stock_rsi/low_beta60.py', 'src/stock_rsi/low_beta60_extension.py')
LOCAL_FILES = ('low-beta60-raw-horizon-20261021/manifest.json', 'low-beta60-raw-horizon-20261021/calendar.json',
    'low-beta60-horizon-independent-audit-20261021.json', 'low-beta60-account-source-events-horizon-20261021/summary.json',
    'low-beta60-account-source-events-horizon-20261021/derived_events.json', 'low-beta60-account-source-events-horizon-20261021/event_source_receipts.json',
    'low-beta60-horizon-event-independent-audit-20261021.json', 'low-beta60-intraday-development-20261021/summary.json',
    'low-beta60-intraday-independent-audit-20261021.json', 'low-beta60-intraday-development-v2-parity-20261021/summary.json',
    'low-beta60-intraday-v2-ledger-parity-audit-20261021.json',
    'low-beta60-calendar-extension-formations-20261021/targets.json', 'low-beta60-pre2026-formations-20261021/targets.json',
    'low-beta60-minutes-dev-20261021/manifest.json', 'low-beta60-minutes-dev-20261021/plan.json',
    'low-beta60-minutes-2026-20261021/manifest.json', 'low-beta60-minutes-2026-20261021/plan.json',
    'low-beta60-minute-admission-20261021/summary.json', 'low-beta60-minute-admission-2026-20261021/summary.json',
    'low-beta60-minute-independent-audit-20261021.json', 'low-beta60-2026-minute-independent-audit-20261021.json')
PUBLIC_FILES = ('experiments/qlib/low-beta60-horizon-event-results.json', 'experiments/qlib/low-beta60-horizon-event-independent-audit.json',
    'experiments/qlib/low-beta60-horizon-events-output-review.json', 'experiments/qlib/low-beta60-horizon-source-independent-audit.json',
    'experiments/qlib/low-beta60-minute-source-results.json', 'experiments/qlib/low-beta60-minute-source-independent-audit.json',
    'experiments/qlib/low-beta60-2026-minute-source-results.json', 'experiments/qlib/low-beta60-2026-minute-source-independent-audit.json',
    'docs/research/low-beta60-horizon-account-plan-2026-10-21.md')
ARTIFACTS = {'days': 'daily.csv', 'intents': 'intents.json', 'parent_instructions': 'parent_instructions.json',
    'orders': 'orders.json', 'fills': 'fills.json', 'corporate_ledger': 'corporate_ledger.json', 'ownership': 'ownership.json'}


class ContinuousTapeBank(TapeBank):
    def __init__(self, old, new, bars):
        for root in (Path(old), Path(new)):
            manifest = json.loads((root / 'manifest.json').read_bytes())
            if manifest['complete_capture'] is not True:
                raise ValueError('complete old and new minute sources required')
        super().__init__(Path(old), Path(new), bars, END)
        for (code, day), (path, h) in self.index.items():
            if code not in bars or day not in bars[code] or day > END or file_sha(path) != h:
                raise ValueError('minute source bytes or daily identity changed')

    def __call__(self, code, day):
        key = (code, day.isoformat())
        if key not in self.index or key[1] > END:
            raise ValueError('missing or future frozen minute tape')
        path, expected = self.index[key]
        if file_sha(path) != expected:
            raise ValueError('minute bytes changed, including cached tape')
        return super().__call__(code, day)


def fixed_interval_returns(rows, initial_cash):
    nav = {r['day']: Decimal(str(r['equity'])) for r in rows}
    if len(nav) != len(rows) or rows[-1]['day'] != END:
        raise ValueError('unique observations through fixed cutoff required')
    start, end24, end25, end26 = Decimal(initial_cash), nav['2024-12-31'], nav['2025-12-31'], nav[END]
    if any(not v.is_finite() or v <= 0 for v in (start, end24, end25, end26)):
        raise ValueError('finite positive continuous account values required')
    r24, r25, r26 = end24 / start - 1, end25 / end24 - 1, end26 / end25 - 1
    return {'2024_return_pct': float(r24 * 100), '2025_return_pct': float(r25 * 100),
        '2026_through_2026-10-20_return_pct': float(r26 * 100),
        'three_numeric_conditions_met_at_interim_cutoff': r24 > 0 and r25 > 0 and r26 >= Decimal('.1'),
        '2026_starting_equity': str(end25), 'ending_equity': str(end26)}


def verify_financial_prefix(case, reference):
    if set(reference) != set(ARTIFACTS):
        raise ValueError('all seven original financial artifacts required')
    clocks = {'days': 'day', 'intents': 'execution_session', 'parent_instructions': 'eligible_at',
              'orders': 'submitted_at', 'fills': 'execution_at', 'corporate_ledger': 'day'}
    for key in ARTIFACTS:
        actual = clean(case[key])
        if key == 'ownership': actual = {day: value for day, value in actual.items() if day < '2026-01-01'}
        else: actual = [row for row in actual if row[clocks[key]] < '2026-01-01']
        if actual != reference[key]:
            raise ValueError('original pre2026 financial prefix changed: ' + key)


def run_profiles(out, calendar, bars, events, targets, bank, references):
    out = Path(out)
    if out.exists(): raise ValueError('preserve existing full or partial account replay')
    out.mkdir(parents=True); results = {}; bank = SourceIOGuard(bank)
    event_by_id = {e.event_id: e for e in events}
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            profile = f'{participation}/{cost}'; folder = out / profile; folder.mkdir(parents=True); holders = []
            print('continuous account', profile, 'initialCNY', CAPITAL, flush=True)
            def factory(cal, cash, distributions, **kwargs):
                broker = partial(IntradayBroker, participation_bps=participation, extra_cost_bps=cost, tape_provider=bank)
                account = StockDistributionAccount(cal, cash, distributions, broker_factory=broker, **kwargs)
                holders.append(account); return account
            try:
                case = simulate_fixed_targets(calendar, bars, events, targets, CAPITAL, lifecycles={}, account_factory=factory, policy_id='low_beta60')
                if len(case['days']) != 676 or len(case['intents']) != 34 or case['days'][-1]['day'] != END:
                    raise ValueError('complete676-session34-intent account required')
                for r in case['corporate_ledger']:
                    if r['kind'] != 'EX_DATE_ENTITLEMENT' or not r['registered_quantity']: continue
                    e = event_by_id[r['event_id']]
                    if e.capital_per_share and not e.capital_tax_exempt_verified or e.stock_per_share and not e.stock_tax_basis_verified:
                        raise ValueError('owned noncash event has unsupported tax evidence')
                case['parent_instructions'] = case.pop('orders'); case['orders'] = holders[0].broker.child_orders
                verify_financial_prefix(case, references[profile])
                if case['whole_day_volume_violations']:
                    raise ValueError('whole-day source capacity exceeded')
                artifacts = write_case(folder, case)
                values = fixed_interval_returns(case['days'], CAPITAL)
                days = case['days'][1:]; peak = Decimal(CAPITAL); drawdown = Decimal(0)
                for row in days: peak = max(peak, row['equity']); drawdown = min(drawdown, row['equity'] / peak - 1)
                result = {'status': 'NESTED_EXECUTION_ACCOUNT_RECONCILED', **values,
                    'development_financial_prefix_identical': True, 'account_sessions': len(days), 'monthly_decisions': len(case['intents']),
                    'average_exposure_pct': float(sum((r['exposure'] for r in days), Decimal(0)) / len(days) * 100),
                    'max_drawdown_pct': float(drawdown * 100), 'parent_instructions': len(case['parent_instructions']),
                    'child_orders': len(case['orders']), 'fills': len(case['fills']),
                    'all_children_within_1million_shares': all(0 < o['quantity'] <= 1000000 for o in case['orders']),
                    'portfolio_returns_computed': True, 'artifact_sha256': artifacts}
            except (ValueError, KeyError, ArithmeticError, OSError) as exc:
                result = {'status': 'INVALID_SOURCE_OR_ACCOUNT', 'error_type': type(exc).__name__, 'error': str(exc), 'portfolio_returns_computed': False}
                if holders:
                    account = holders[0]
                    state = clean({'last_account_clock': account._last_clock, 'last_intraday_end': account.broker._last_end,
                        'cash': account.broker.cash, 'positions': account.broker.positions, 'owned_shares': account.owned_quantities(),
                        'entitlements': account.entitlements, 'parent_instructions': account.broker.orders, 'child_orders': account.broker.child_orders,
                        'fills': account.broker.fills, 'corporate_ledger': account.corporate_ledger, 'cash_claims': account.cash_claims, 'stock_claims': account.stock_claims})
                    (folder / 'failed_account_state.json').write_text(json.dumps(state, indent=2) + '\n')
                (folder / 'error.json').write_text(json.dumps(result, indent=2) + '\n')
                result['failure_artifact_sha256'] = {f.name: file_sha(f) for f in sorted(folder.iterdir())}
            results[profile] = result
            (out / 'case_results.json').write_text(json.dumps(results, indent=2) + '\n')
    return results


def _read(path): return json.loads(Path(path).read_bytes())


def load_inputs(base, repo, plan):
    if (set(plan['method_code_sha256']) != set(METHOD_FILES) or set(plan['local_source_sha256']) != set(LOCAL_FILES)
            or set(plan['public_evidence_sha256']) != set(PUBLIC_FILES)):
        raise ValueError('complete mandatory code, local and public binding scopes required')
    for field, root in (('method_code_sha256', repo), ('local_source_sha256', base), ('public_evidence_sha256', repo)):
        for name, h in plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root / name) != h:
                raise ValueError('frozen account source, code or evidence changed')
    raw = base / 'low-beta60-raw-horizon-20261021'; m = _read(raw / 'manifest.json')
    raw_audit = _read(base / 'low-beta60-horizon-independent-audit-20261021.json')
    sessions = _read(raw / 'calendar.json')['sessions']
    if (m['capture_complete'] is not True or raw_audit['manifest_sha256'] != file_sha(raw / 'manifest.json')
            or m['calendar_sha256'] != file_sha(raw / 'calendar.json') or len(sessions) != 676
            or sessions != sorted(set(sessions)) or [sessions[0], sessions[-1]] != ['2023-12-29', END]):
        raise ValueError('fixed complete raw source calendar required')
    bars = {}
    for code, h in m['per_code_sha256'].items():
        f = raw / 'codes' / (code + '.json')
        if Path(code).name != code or file_sha(f) != h: raise ValueError('raw packet bytes changed')
        p = _read(f)
        if p['instrument'] != code or [r['date'] for r in p['bars']] != sessions: raise ValueError('raw issuer/calendar changed')
        bars[code] = {r['date']: r for r in p['bars']}
    eventdir = base / 'low-beta60-account-source-events-horizon-20261021'; summary = _read(eventdir / 'summary.json')
    audit = _read(base / 'low-beta60-horizon-event-independent-audit-20261021.json')
    if (summary['raw_manifest_sha256'] != file_sha(raw / 'manifest.json') or audit['summary_sha256'] != file_sha(eventdir / 'summary.json')
            or audit['verified_events'] != 269 or audit['full2026_reference_and_adjustment_coverage'] is not True
            or not all(audit['semantic_negative_controls_rejected'].values()) or audit['unverified_tax_event_keys'] != ['SZ000937|2026-06-17']):
        raise ValueError('independently reconstructed269 events and retained tax guard required')
    for name, h in summary['artifact_sha256'].items():
        if Path(name).name != name or file_sha(eventdir / name) != h: raise ValueError('compiled event artifact changed')
    events = []
    for r in _read(eventdir / 'derived_events.json'):
        events.append(StockDistribution(**{k: (None if v is None else date.fromisoformat(v)) if k in
            ('announced', 'recorded', 'ex_date', 'pay_date', 'listed') else Decimal(v) if k in
            ('cash_per_share', 'capital_per_share', 'stock_per_share', 'stock_taxable_income_per_share') else v for k, v in r.items()}))
    old = base / 'low-beta60-intraday-development-20261021'; old_summary = _read(old / 'summary.json')
    old_audit = _read(base / 'low-beta60-intraday-independent-audit-20261021.json')
    if old_audit['summary_sha256'] != file_sha(old / 'summary.json') or old_summary['raw_development_confirmation_passes'] is not True:
        raise ValueError('independent original six-profile confirmation required')
    parity = _read(base / 'low-beta60-intraday-v2-ledger-parity-audit-20261021.json')
    if (parity['original_summary_sha256'] != file_sha(old / 'summary.json')
            or parity['guarded_summary_sha256'] != file_sha(base / 'low-beta60-intraday-development-v2-parity-20261021/summary.json')
            or parity['accounting_files_checked'] != 42 or parity['v2_does_not_change_original_account_economics'] is not True):
        raise ValueError('original V2 typed IO guard financial parity required')
    references = {}
    for label, result in old_summary['results_by_profile'].items():
        if set(result['artifact_sha256']) != set(ARTIFACTS.values()): raise ValueError('all seven original profile artifacts required')
        for name, h in result['artifact_sha256'].items():
            if file_sha(old / label / name) != h: raise ValueError('original financial artifact changed')
        references[label] = {}
        for key, name in ARTIFACTS.items():
            if key == 'days':
                with (old / label / name).open() as f: references[label][key] = list(csv.DictReader(f))
            else: references[label][key] = _read(old / label / name)
    targets = _read(base / 'low-beta60-calendar-extension-formations-20261021/targets.json')['low_beta60']
    old_targets = _read(base / 'low-beta60-pre2026-formations-20261021/targets.json')['low_beta60']
    if (len(targets) != 34 or len(bars) != 79 or {d: t for d, t in targets.items() if d < '2026-01-01'} != old_targets
            or {c for t in targets.values() for c in t['weights']} != set(bars)):
        raise ValueError('unchanged34 target schedule required')
    for suffix, expected_pairs in (('dev', 1332), ('2026', 754)):
        minute_dir = base / f'low-beta60-minutes-{suffix}-20261021'; manifest = _read(minute_dir / 'manifest.json')
        admission_dir = base / ('low-beta60-minute-admission-20261021' if suffix == 'dev' else 'low-beta60-minute-admission-2026-20261021')
        admission = _read(admission_dir / 'summary.json')
        auditfile = base / ('low-beta60-minute-independent-audit-20261021.json' if suffix == 'dev' else 'low-beta60-2026-minute-independent-audit-20261021.json')
        minute_audit = _read(auditfile)
        if (len(manifest['per_session_sha256']) != expected_pairs or admission['capture_manifest_sha256'] != file_sha(minute_dir / 'manifest.json')
                or admission['admitted_for_reconstructed_execution'] is not True or minute_audit['admission_summary_sha256'] != file_sha(admission_dir / 'summary.json')
                or minute_audit['source_pairs_reconstructed'] != expected_pairs or minute_audit['reconstructed_source_admission_passes'] is not True):
            raise ValueError('complete independently reconstructed minute admission required')
    bank = ContinuousTapeBank(base / 'low-beta60-minutes-dev-20261021', base / 'low-beta60-minutes-2026-20261021', bars)
    if len(bank.index) != 2086: raise ValueError('full2086 potential tape identities required')
    return TradingCalendar(sessions), bars, events, targets, bank, references


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('plan', 'expected-plan-sha256', 'source-root', 'output-dir'): parser.add_argument('--' + name, required=True)
    a = parser.parse_args(argv); repo = Path(__file__).resolve().parents[1]; base, out = Path(a.source_root), Path(a.output_dir)
    if out.exists() or file_sha(a.plan) != a.expected_plan_sha256: raise ValueError('frozen external plan and unused output required')
    plan = _read(a.plan)
    if (plan['status'] != 'FROZEN_LOW_BETA60_SIX_CONTINUOUS_ACCOUNTS_THROUGH_OCT20'
            or plan['window'] != ['2023-12-29', END] or plan['initial_CNY'] != CAPITAL
            or plan['participation_bps'] != list(PARTICIPATION) or plan['extra_cost_bps'] != list(EXTRA_BPS)
            or plan['output_directory'] != OUTPUT or out.resolve() != (base / OUTPUT).resolve()
            or plan['source_queries_allowed'] is not False or plan['investment_rule_changes_allowed'] is not False
            or set(plan['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('fixed six-profile investment/account protocol changed')
    calendar, bars, events, targets, bank, references = load_inputs(base, repo, plan)
    results = run_profiles(out, calendar, bars, events, targets, bank, references)
    summary = {'status': 'SIX_CONTINUOUS_ACCOUNTS_RECORDED_WITH_FAILURE_STATES', 'plan_sha256': a.expected_plan_sha256,
        'window': ['2023-12-29', END], 'initial_CNY': CAPITAL, 'results_by_profile': results,
        'source_prefix_pairs': len(bank.index), 'tape_accessed_pairs': len(bank.accessed), 'compiled_events': len(events),
        'source_queries': 0, 'method_code_sha256': plan['method_code_sha256'],
        'portfolio_returns_computed': any(r['portfolio_returns_computed'] for r in results.values()),
        'all_profiles_complete': all(r['status'] == 'NESTED_EXECUTION_ACCOUNT_RECONCILED' for r in results.values()),
        'tax_model': 'Flat20percent stress on cash+verified taxable stock income; actualFIFO unverified; unknown capital tax stops owned account',
        'source_evidence_level': 'RECONSTRUCTED_ENGINEERING_SIMULATION', 'historical_arrival_verified': False,
        'queue_and_impact_calibrated': False, 'full_corporate_actions_certified': False, 'actual_FIFO_tax_liability_verified': False,
        'full_October_complete': False, 'sealed_evidence': False, 'candidate_promoted': False, 'objective_achieved': False}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('continuous accounts complete', summary['all_profiles_complete'], 'portfolio returns computed', summary['portfolio_returns_computed'], flush=True)
    return 0 if summary['all_profiles_complete'] else 2


if __name__ == '__main__': raise SystemExit(main())
