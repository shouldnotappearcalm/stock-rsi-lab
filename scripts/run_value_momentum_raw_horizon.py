"""Frozen continuous daily engineering diagnostic; never a minute-execution claim."""
import argparse
import csv
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import partial
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.replay_budgeted_stock_distribution_targets import simulate_budgeted_fixed_targets
from scripts.run_low_risk_feedback_cost_stress import write_case
from scripts.run_low_risk_raw_share_validation import clean
from stock_rsi.calendar import TradingCalendar
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

START, PRE_END, END = '2023-12-29', '2025-12-31', '2026-10-20'
RAW = 'szse-value-momentum-raw-full-v2-20261021'
OLD_RAW = 'szse-value-momentum-raw-dev-20261021'
EVENTS = 'szse-value-momentum-full-account-events-20261021'
OLD_EVENTS = 'szse-value-momentum-account-sources-20261021'
TARGET = 'szse-value-momentum-formations-full-v2-20261021/targets.json'
OLD_TARGET = 'szse-value-momentum-formations-pre2026-20261021/targets.json'
OLD_DAILY = 'szse-value-momentum-raw-daily-dev-20261021'
OLD_INTRADAY = 'szse-value-momentum-intraday-dev-20261021'
OUTPUT = 'szse-value-momentum-raw-daily-horizon-20261021'
POLICY = 'szse_value_momentum_equal'
ARTIFACTS = ('daily.csv', 'intents.json', 'fills.json', 'orders.json', 'corporate_ledger.json', 'ownership.json')
LOCAL_FILES = (RAW+'/manifest.json', RAW+'/calendar.json', OLD_RAW+'/manifest.json', OLD_RAW+'/calendar.json',
    EVENTS+'/summary.json', OLD_EVENTS+'/summary.json', OLD_EVENTS+'/derived_events.json',
    OLD_EVENTS+'/lifecycles.json', TARGET, OLD_TARGET, OLD_DAILY+'/summary.json', OLD_INTRADAY+'/summary.json',
    'szse-value-momentum-raw-reassembly-v2-audit-20261021.json')
PUBLIC_FILES = ('experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json',
    'experiments/qlib/szse-value-momentum-noncash-2026-content-review.json',
    'experiments/qlib/szse-value-momentum-raw-reassembly-v2-request.json',
    'docs/research/szse-value-momentum-full-daily-plan-2026-10-21.md')
METHOD_FILES = ('scripts/run_value_momentum_raw_horizon.py', 'scripts/fundamental_query_journal.py',
    'scripts/prepare_value_momentum_full_events.py', 'scripts/replay_budgeted_stock_distribution_targets.py',
    'scripts/run_low_risk_feedback_cost_stress.py', 'scripts/run_low_risk_raw_share_validation.py',
    'src/stock_rsi/stock_distribution_account.py', 'src/stock_rsi/raw_share_account.py',
    'src/stock_rsi/execution_cost.py', 'src/stock_rsi/broker.py', 'src/stock_rsi/budgeted_raw_orders.py',
    'src/stock_rsi/budgeted_lot_orders.py', 'src/stock_rsi/prior_close_orders.py',
    'src/stock_rsi/lifecycle_source_rows.py', 'src/stock_rsi/calendar.py',
    'src/stock_rsi/models.py', 'src/stock_rsi/data.py', 'src/stock_rsi/time.py')


def read(path):
    return json.loads(Path(path).read_bytes())


def immutable_financial_hashes(base):
    result = {}
    for directory, key, profiles, names in (
        (OLD_DAILY, 'results_by_extra_bps', {'20', '40'}, set(ARTIFACTS)),
        (OLD_INTRADAY, 'results_by_profile', {f'{p}/{c}' for p in (100, 500, 1000) for c in (20, 40)},
         set(ARTIFACTS) | {'parent_instructions.json'})):
        values = read(base / directory / 'summary.json')[key]
        if set(values) != profiles:
            raise ValueError('original profile set changed')
        for profile, value in values.items():
            if set(value['artifact_sha256']) != names:
                raise ValueError('complete original financial artifact sets required')
            result.update({directory+'/'+profile+'/'+n: h for n, h in value['artifact_sha256'].items()})
    if len(result) != 54:
        raise ValueError('exact54 original financial hashes required')
    return result


def require_exact_bindings(plan, financial):
    for field, expected in (('method_code_sha256', set(METHOD_FILES)),
                            ('local_source_sha256', set(LOCAL_FILES)),
                            ('public_evidence_sha256', set(PUBLIC_FILES))):
        if set(plan[field]) != expected:
            raise ValueError('exact required frozen binding set missing: ' + field)
    if plan['immutable_financial_sha256'] != financial:
        raise ValueError('all54 original financial identities required')


def interval_returns(rows, initial_cash):
    nav = {r['day']: Decimal(str(r['equity'])) for r in rows}
    if len(nav) != len(rows) or not rows or rows[-1]['day'] != END:
        raise ValueError('unique continuous observations through exact Oct20 required')
    values = [Decimal(initial_cash), nav['2024-12-31'], nav[PRE_END], nav[END]]
    if any(not v.is_finite() or v <= 0 for v in values):
        raise ValueError('positive finite account values required')
    returns = [values[i+1] / values[i] - 1 for i in range(3)]
    return {'2024_return_pct': float(returns[0] * 100), '2025_return_pct': float(returns[1] * 100),
        '2026_through_2026-10-20_return_pct': float(returns[2] * 100),
        'three_numeric_conditions_met_at_interim_cutoff': returns[0] > 0 and returns[1] > 0 and returns[2] >= Decimal('.1'),
        '2026_starting_equity': str(values[2]), 'ending_equity': str(values[3])}


class CheckpointAccount(StockDistributionAccount):
    """Capture end2025 before the new Jan2026 instruction can mutate old orders."""
    def end_day(self, day):
        super().end_day(day)
        if day.isoformat() == PRE_END and not hasattr(self, 'pre2026_checkpoint'):
            self.pre2026_checkpoint = deepcopy(clean({
                'orders': self.broker.orders, 'fills': self.broker.fills,
                'corporate_ledger': self.corporate_ledger}))


def verify_prefix(case, checkpoint, original):
    # Order status is observed AT the boundary, not read backwards from a later
    # mutable order object. New Jan instructions belong to the extension.
    for key in ('orders', 'fills', 'corporate_ledger'):
        if checkpoint[key] != original[key]:
            raise ValueError('boundary financial collection changed: ' + key)
    for key, clock in (('intents', 'execution_session'),):
        if clean([r for r in case[key] if r[clock] <= PRE_END]) != original[key]:
            raise ValueError('old decision snapshots changed')
    ownership = {d: v for d, v in case['ownership'].items() if d <= PRE_END}
    if clean(ownership) != original['ownership']:
        raise ValueError('old integer holdings changed')
    days = [{k: str(v) for k, v in r.items()} for r in case['days'] if r['day'] <= PRE_END]
    if days != original['days']:
        raise ValueError('old daily assets or returns changed')


def load_packets(base, directory):
    root = base / directory; manifest = read(root / 'manifest.json'); packets = {}
    if file_sha(root / 'calendar.json') != manifest['calendar_sha256']:
        raise ValueError('explicit raw calendar changed')
    for code, expected in manifest['per_code_sha256'].items():
        f = root / 'codes' / (code + '.json')
        if Path(code).name != code or file_sha(f) != expected:
            raise ValueError('raw packet changed')
        packets[code] = read(f)
    return manifest, read(root / 'calendar.json')['sessions'], packets


def load_inputs(base, repo, plan):
    from scripts.prepare_value_momentum_full_events import load_full_events
    if (plan['status'] != 'FROZEN_COMPOSITE_FULL_DAILY_ENGINEERING_ONLY'
        or plan['initial_CNY'] != '1000000' or plan['extra_cost_bps'] != [20, 40]
        or plan['candidate'] != POLICY or plan['output_directory'] != OUTPUT
        or plan['window'] != [START, END]):
        raise ValueError('fixed continuous account and execution profiles required')
    require_exact_bindings(plan, immutable_financial_hashes(base))
    for mapping, root in ((plan['method_code_sha256'], repo), (plan['local_source_sha256'], base),
                          (plan['public_evidence_sha256'], repo), (plan['immutable_financial_sha256'], base)):
        for name, expected in mapping.items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root / name) != expected:
                raise ValueError('bound source/method/financial file changed: ' + name)
    manifest, sessions, packets = load_packets(base, RAW)
    old_manifest, old_sessions, old = load_packets(base, OLD_RAW)
    if (len(packets) != 127 or len(old) != 103 or len(sessions) != 676 or sessions[:486] != old_sessions
        or sessions != sorted(set(sessions)) or [sessions[0], sessions[-1]] != [START, END]):
        raise ValueError('complete127-name676-session old486-prefix source required')
    audit = read(base / 'szse-value-momentum-raw-reassembly-v2-audit-20261021.json')
    if (manifest['status'] != 'LOCAL_ONLY_V2_RAW_REASSEMBLED_ADMISSION_SEPARATE'
        or audit['raw_manifest_sha256'] != file_sha(base / RAW / 'manifest.json')
        or any(audit[k] is not True for k in ('all127_packets_authenticated', 'all123_accepted_packets_byte_exact',
                                            'all_original103_prefixes_identical', 'all54_original_financial_files_unchanged'))):
        raise ValueError('complete separately rechecked raw source required')
    for c, p in packets.items():
        required = [d for d in sessions if c != 'SZ001389' or d >= '2024-04-02']
        if p['instrument'] != c or [r['date'] for r in p['bars']] != required:
            raise ValueError('unexplained raw source coverage gap')
    for c, p in old.items():
        for k, d in (('bars', 'date'), ('adjustments', 'dividOperateDate'), ('distributions', 'dividOperateDate')):
            if [r for r in packets[c][k] if r[d] <= PRE_END] != p[k]:
                raise ValueError('old raw economic prefix changed')
    targets = read(base / TARGET); prior = read(base / OLD_TARGET)[POLICY]
    if len(targets) != 34 or {d: v for d, v in targets.items() if d <= PRE_END} != prior:
        raise ValueError('frozen34 targets and exact24 prefix required')
    if {c for t in targets.values() for c in t['weights']} != set(packets):
        raise ValueError('frozen full target universe differs from raw source')
    events, lifecycles, summary = load_full_events(base / EVENTS, plan['event_summary_sha256'])
    if plan['event_summary_sha256'] != plan['local_source_sha256'][EVENTS+'/summary.json']:
        raise ValueError('event summary must match frozen local source binding')
    if summary['raw_manifest_sha256'] != file_sha(base / RAW / 'manifest.json'):
        raise ValueError('event projection belongs to another raw source')
    if (summary['target_sha256'] != file_sha(base / TARGET)
        or summary['original_summary_sha256'] != file_sha(base / OLD_EVENTS / 'summary.json')
        or lifecycles != read(base / OLD_EVENTS / 'lifecycles.json')):
        raise ValueError('event target, old-source or lifecycle identity changed')
    old_events = tuple(e for e in events if e.ex_date.isoformat() <= PRE_END)
    if len(old_events) != 255 or clean([asdict(e) for e in old_events]) != read(base / OLD_EVENTS / 'derived_events.json'):
        raise ValueError('exact old255 events required')
    references = {}
    old_results = read(base / OLD_DAILY / 'summary.json')['results_by_extra_bps']
    for bps in (20, 40):
        folder = base / OLD_DAILY / str(bps); refs = {}
        for name, expected in old_results[str(bps)]['artifact_sha256'].items():
            if file_sha(folder / name) != expected:
                raise ValueError('old daily evidence changed')
        with (folder / 'daily.csv').open() as f:
            refs['days'] = list(csv.DictReader(f))
        for key in ('intents', 'fills', 'orders', 'corporate_ledger', 'ownership'):
            refs[key] = read(folder / (key + '.json'))
        refs['artifact_sha256'] = old_results[str(bps)]['artifact_sha256']
        references[bps] = refs
    return TradingCalendar(sessions), packets, events, targets, lifecycles, TradingCalendar(old_sessions), old, old_events, prior, references


def run_profiles(out, inputs):
    calendar, packets, events, targets, lifecycles, oldcal, old, oldevents, prior, references = inputs
    bars = {c: {r['date']: r for r in p['bars']} for c, p in packets.items()}
    oldbars = {c: {r['date']: r for r in p['bars']} for c, p in old.items()}
    out.mkdir(parents=True); controls = {}
    for bps in (20, 40):
        factory = partial(StockDistributionAccount, broker_factory=partial(ExecutionCostBroker, extra_cost_bps=bps))
        case = simulate_budgeted_fixed_targets(oldcal, oldbars, oldevents, prior, '1000000',
            lifecycles=lifecycles, account_factory=factory, policy_id=POLICY)
        folder = out / 'pre2026-controls' / str(bps); folder.mkdir(parents=True)
        controls[str(bps)] = write_case(folder, case)
        verify_prefix(case, clean({k: case[k] for k in ('orders', 'fills', 'corporate_ledger')}), references[bps])
        if controls[str(bps)] != references[bps]['artifact_sha256']:
            raise ValueError('old six-file daily control bytes changed')
        print('old daily control', bps, 'all six financial collections identical', flush=True)
    results = {}
    for bps in (20, 40):
        folder = out / str(bps); folder.mkdir(); holders = []
        def factory(cal, cash, distributions, **kwargs):
            account = CheckpointAccount(cal, cash, distributions,
                broker_factory=partial(ExecutionCostBroker, extra_cost_bps=bps), **kwargs)
            holders.append(account); return account
        try:
            case = simulate_budgeted_fixed_targets(calendar, bars, events, targets, '1000000',
                lifecycles=lifecycles, account_factory=factory, policy_id=POLICY)
            if len(case['days']) != 676 or len(case['intents']) != 34 or case['whole_day_volume_violations']:
                raise ValueError('complete fixed-horizon account and observed capacity required')
            verify_prefix(case, holders[0].pre2026_checkpoint, references[bps])
            artifacts = write_case(folder, case)
            result = {'status': 'CONTINUOUS_DAILY_PROXY_RECONCILED', **interval_returns(case['days'], '1000000'),
                'pre2026_financial_collections_identical_at_boundary': True, 'artifact_sha256': artifacts}
        except (ValueError, KeyError, ArithmeticError, OSError) as exc:
            result = {'status': 'INVALID_SOURCE_OR_ACCOUNT', 'error_type': type(exc).__name__, 'error': str(exc), 'portfolio_returns_computed': False}
            if holders:
                a = holders[0]
                state = clean({'last_account_clock': a._last_clock, 'cash': a.broker.cash,
                    'positions': a.broker.positions, 'orders': a.broker.orders, 'fills': a.broker.fills,
                    'entitlements': a.entitlements, 'corporate_ledger': a.corporate_ledger,
                    'cash_claims': a.cash_claims, 'stock_claims': a.stock_claims})
                (folder / 'failed_account_state.json').write_text(json.dumps(state, indent=2) + '\n')
            (folder / 'error.json').write_text(json.dumps(result, indent=2) + '\n')
            result['failure_artifact_sha256'] = {f.name: file_sha(f) for f in sorted(folder.iterdir())}
        results[str(bps)] = result
        (out / 'case_results.json').write_text(json.dumps(results, indent=2) + '\n')
        print('continuous daily', bps, result['status'], result.get('error', ''), flush=True)
    return controls, results


def main():
    p = argparse.ArgumentParser()
    for n in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        p.add_argument('--' + n, required=True)
    p.add_argument('--source-preflight-only', action='store_true'); a = p.parse_args()
    base, repo, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.output_dir)
    if out.exists() or file_sha(a.plan) != a.expected_plan_sha256:
        raise ValueError('unused output and external frozen plan required')
    plan = read(a.plan); inputs = load_inputs(base, repo, plan)
    if out.resolve() != (base / OUTPUT).resolve():
        raise ValueError('fixed account output directory required')
    if a.source_preflight_only:
        print('full source/event/old financial identities authenticated; no account outcomes'); return
    controls, results = run_profiles(out, inputs)
    load_inputs(base, repo, plan)
    if file_sha(a.plan) != a.expected_plan_sha256:
        raise ValueError('frozen plan changed during account replay')
    unchanged = all(file_sha(base / n) == h for n, h in plan['immutable_financial_sha256'].items())
    summary = {'plan_sha256': a.expected_plan_sha256, 'old_daily_controls': controls, 'results_by_extra_bps': results,
        'original54_financial_files_unchanged': unchanged, 'execution_model': 'DAILY_PROXY_ONLY',
        'minute_execution_admitted': False, 'historical_arrival_verified': False, 'full_October_complete': False,
        'actual_FIFO_tax_liability_verified': False, 'candidate_promoted': False, 'objective_achieved': False}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not unchanged: raise ValueError('immutable financial evidence changed')
    return 0 if all(r['status'] == 'CONTINUOUS_DAILY_PROXY_RECONCILED' for r in results.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
