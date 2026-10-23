"""Frozen continuous account diagnostic. No investment rules are changed here."""
import argparse
import copy
import csv
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import partial
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.run_asset_expansion_raw_development import (
    CANDIDATE, METHOD_FILES as OLD_METHODS, RAW as OLD_RAW, TARGET as OLD_TARGET,
    restoration_receipts,
)
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.run_low_risk_feedback_cost_stress import write_case
from scripts.run_low_risk_raw_share_validation import clean, validate_source_coverage
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

START, END, PREFIX = '2023-12-29', '2026-10-21', '2025-12-31'
RAW = 'asset-expansion-raw-reconstructed-20261023'
OLD_ACCOUNT = 'asset-expansion-raw-development-20261022'
TARGET_DIR = 'asset-expansion-targets-through2026-v1-20261023'
TARGET = 'experiments/qlib/asset-expansion-2026-targets.json'
SOURCE_QA = 'experiments/qlib/asset-expansion-2026-source-reconstruction-audit.json'
TARGET_QA = 'experiments/qlib/asset-expansion-2026-targets-source-audit.json'
PLAN = 'docs/research/asset-expansion-2026-continuous-account-plan-2026-10-23.md'
OUTPUT = 'asset-expansion-continuous-account-20261023'
NEW_METHODS = ('scripts/run_asset_expansion_raw_horizon.py',
               'tests/test_asset_expansion_raw_horizon_account.py', PLAN)


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(clean(value), indent=2) + '\n')


def dependency_contract(repo, base):
    """Bind full checked source ancestry and frozen historical account evidence."""
    result = {}
    def add(path, expected=None):
        path = path.resolve()
        for prefix, root in (('repo', repo.resolve()), ('source', base.resolve())):
            if path.is_relative_to(root):
                name = prefix + '/' + str(path.relative_to(root))
                break
        else:
            raise ValueError('dependency outside declared roots')
        actual = file_sha(path)
        if expected is not None and actual != expected:
            raise ValueError('checked dependency changed: ' + name)
        if name in result and result[name] != actual:
            raise ValueError('conflicting dependency')
        result[name] = actual
    qa = read(repo/SOURCE_QA)
    for field in ('all_consumed_input_sha256', 'all_reconstruction_output_sha256'):
        for path, h in qa[field].items():
            add(Path(path), h)
    for directory in (RAW, OLD_RAW, OLD_ACCOUNT, TARGET_DIR):
        for path in sorted((base/directory).rglob('*')):
            if path.is_file():
                add(path)
    old = read(repo/'experiments/qlib/asset-expansion-raw-development-request.json')
    for field, root in (('method_code_sha256', repo), ('public_inputs_sha256', repo),
                        ('source_inputs_sha256', base)):
        for name, h in old[field].items():
            add(safe_path(root, name), h)
    for name in (*OLD_METHODS, *NEW_METHODS, TARGET, SOURCE_QA, TARGET_QA,
                 'experiments/qlib/asset-expansion-raw-development-request.json',
                 'experiments/qlib/asset-expansion-raw-account-audit.json',
                 'experiments/qlib/asset-expansion-raw-development-results.json',
                 'experiments/qlib/asset-expansion-primary-content-audit.json',
                 'experiments/qlib/asset-expansion-2026-source-reconstruction-results.json',
                 'experiments/qlib/asset-expansion-2026-targets-results.json'):
        add(repo/name)
    return result


def safe_path(root, name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('root relative dependency required')
    return root/p


def bound_paths(contract, repo, base):
    return {str(safe_path({'repo': repo, 'source': base}[name.split('/', 1)[0]],
                         name.split('/', 1)[1]).resolve()): h for name, h in contract.items()}


def authenticate(request, expected, repo, base):
    if file_sha(request) != expected:
        raise ValueError('frozen account request changed')
    r = read(request)
    if (r['status'] != 'FROZEN_UNCHANGED_CONTINUOUS_ACCOUNT_THROUGH20261021'
            or r['candidate'] != CANDIDATE or r['window'] != [START, END]
            or r['initial_CNY'] != '1000000' or r['extra_cost_bps'] != [20, 40]
            or r['output_directory'] != OUTPUT or r['network_query_budget'] != 0
            or r['strategy_changes_allowed'] is not False
            or r['bound_sha256'] != dependency_contract(repo, base)):
        raise ValueError('complete frozen continuous-account contract required')
    inputs = bound_paths(r['bound_sha256'], repo, base)
    inputs[str(request.resolve())] = expected
    qa = read(repo/SOURCE_QA); targetqa = read(repo/TARGET_QA)
    if (qa['status'] != 'SEPARATE_ALL142_QUERIES_ALL47_SOURCE_ROWS_AND_PRIMARY_EXIT_CHECKED_ACCOUNT_CLEARANCE_PENDING'
            or qa['names'] != 47 or qa['source_query_chains_checked'] != 142
            or qa['global_sessions'] != 677 or qa['all_inputs_and_outputs_unchanged'] is not True
            or targetqa['status'] != 'SEPARATE_ALL34_ASSET_EXPANSION_RANKS_AND_24_LEGACY_TARGETS_PASSED_NOT_ACCOUNT_ADMISSION'
            or targetqa['formations_checked'] != 34 or targetqa['pre2026_full_target_receipt_parity'] != 24):
        raise ValueError('separate complete source and target QA required')
    return r, inputs


def load_sources(repo, base):
    folder = base/RAW; manifest = read(folder/'manifest.json')
    if (manifest != read(repo/'experiments/qlib/asset-expansion-2026-source-reconstruction-results.json')
            or manifest['reconstruction_complete'] is not True or manifest['changed_inputs']
            or manifest['original_error'] is not None or manifest['persistence_errors']):
        raise ValueError('complete immutable source reconstruction required')
    sessions = read(folder/'calendar.json')['sessions']
    if len(sessions) != 677 or sessions != sorted(set(sessions)) or [sessions[0], sessions[-1]] != [START, END]:
        raise ValueError('explicit677 source sessions required')
    lifecycles = read(folder/'lifecycles.json')
    if set(lifecycles) != {'SH603056'} or lifecycles['SH603056']['effective_date'] != '2026-03-31':
        raise ValueError('only frozen authenticated exit allowed')
    packets = {}; restorations = []
    for code, h in manifest['per_code_sha256'].items():
        path = folder/'codes'/(code+'.json'); packet = read(path)
        active = [d for d in sessions if code not in lifecycles or d < lifecycles[code]['effective_date']]
        if (file_sha(path) != h or packet['instrument'] != code or packet['quarantine']
                or packet['window'] != [START, active[-1]] or [v['date'] for v in packet['bars']] != active):
            raise ValueError('exact active issuer window required')
        packets[code] = packet; restorations.extend(restoration_receipts(packet))
    old_manifest = read(base/OLD_RAW/'manifest.json')
    for code in old_manifest['per_code_sha256']:
        old = read(base/OLD_RAW/'codes'/(code+'.json'))
        for field, clock in (('bars', 'date'), ('distributions', 'dividOperateDate'), ('adjustments', 'dividOperateDate')):
            if [v for v in packets[code][field] if v[clock] <= PREFIX] != old[field]:
                raise ValueError('historical market/action prefix changed')
    if {(x['instrument'], x['restoration_day']) for x in restorations} != {('SH600535','2025-03-27'), ('SH600737','2025-08-14')}:
        raise ValueError('unexplained adjustment restoration')
    validate_source_coverage(packets)
    targets = read(repo/TARGET)[CANDIDATE]; old_targets = read(base/OLD_TARGET)[CANDIDATE]
    if (len(packets) != 47 or len(targets) != 34 or {k:v for k,v in targets.items() if k <= PREFIX} != old_targets
            or {c for t in targets.values() for c in t['weights']} != set(packets)
            or read(repo/TARGET) != read(base/TARGET_DIR/'targets.json')):
        raise ValueError('all34 unchanged targets/47 dependencies required')
    primary = read(repo/'experiments/qlib/asset-expansion-primary-content-audit.json')
    docs = []; dates = {'SH600535':'2025-03-20', 'SH600737':'2025-08-05', 'SH603688':'2024-05-16'}
    for d in primary['documents']:
        if file_sha(base/d['source_relative']) != d['sha256']:
            raise ValueError('reviewed primary changed')
        docs.append({'instrument':d['instrument'], 'day':dates[d['instrument']], 'file':d['file'], 'sha256':d['sha256']})
    calendar = TradingCalendar(sessions)
    events, receipts = compile_distribution_events(packets, {'documents':docs, 'cash_overrides':{},
        'capital_tax':{}, 'stock_dividend_tax_bases':{}, 'supplementary_distributions':[]}, calendar)
    old_events = read(base/OLD_ACCOUNT/'source_projection.json')['events']
    old_ids = {e['event_id'] for e in old_events}
    if len(events) != 141 or clean([asdict(e) for e in events if e.event_id in old_ids]) != old_events:
        raise ValueError('all141 events including exact original79 required')
    return calendar, packets, lifecycles, targets, events, receipts, restorations, old_ids


def account_state(account):
    return copy.deepcopy({'last_clock':account._last_clock, 'cash':account.broker.cash,
        'owned':account.owned_quantities(), 'positions':account.broker.positions,
        'orders':account.broker.orders, 'fills':account.broker.fills,
        'corporate_ledger':account.corporate_ledger, 'entitlements':account.entitlements,
        'cash_claims':account.cash_claims, 'stock_claims':account.stock_claims})


def expected_prefix(folder):
    with (folder/'daily.csv').open() as stream:
        days = list(csv.DictReader(stream))
    return {'days':days, **{k:read(folder/(k+'.json')) for k in
                           ('ownership','orders','fills','intents','corporate_ledger')}}


class ObservedAccount(StockDistributionAccount):
    """Observation only. Parent account and broker retain all economic behavior."""
    def __init__(self, *args, expected, lifecycles, checkpoint_day=PREFIX, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected = expected; self.lifecycles = lifecycles
        self.checkpoint_day = checkpoint_day; self.prefix_checkpoint = None; self.exit_checks = []

    def start_day(self, day):
        for code, proof in self.lifecycles.items():
            if day.isoformat() >= proof['effective_date']:
                owned = self.owned_quantities().get(code, 0)
                orders = [o for o in self.broker.orders if o['security_id'] == code and o['status'] == 'PENDING']
                cash = [v for v in self.cash_claims if v['instrument'] == code and not v['paid']]
                stock = [v for v in self.stock_claims if v['instrument'] == code and not v['credited']]
                future = [e.event_id for e in self.events if e.instrument == code and e.ex_date >= day
                          and self.entitlements.get(e.event_id, 0)]
                if owned or orders or cash or stock or future:
                    raise ValueError('post-exit shares/orders/claims/rights unresolved: '+code)
                self.exit_checks.append({'day':day.isoformat(), 'instrument':code, 'owned':0,
                    'pending_orders':0, 'unpaid_cash_claims':0, 'uncredited_stock_claims':0, 'future_entitled_events':[]})
        super().start_day(day)

    def end_day(self, day):
        super().end_day(day)
        if day.isoformat() == self.checkpoint_day:
            state = account_state(self); self.prefix_checkpoint = state
            comparisons = {'cash':self.expected['days'][-1]['cash'],
                'owned':self.expected['ownership'][self.checkpoint_day],
                'fills':self.expected['fills'], 'orders':self.expected['orders']}
            for key, value in comparisons.items():
                if clean(state[key]) != value:
                    raise ValueError('pre2026 checkpoint differs before next intent: '+key)
        if day.isoformat() > self.checkpoint_day and self.prefix_checkpoint is None:
            raise ValueError('2026 advancement without verified historical checkpoint')


def verify_prefix(case, expected, old_ids, old_codes):
    old_days = [clean(v) for v in case['days'] if v['day'] <= PREFIX]
    if old_days != expected['days']:
        raise ValueError('complete old daily financial prefix differs')
    if {d:q for d,q in case['ownership'].items() if d <= PREFIX} != expected['ownership']:
        raise ValueError('old daily ownership differs')
    if clean([v for v in case['intents'] if v['execution_session'] <= PREFIX]) != expected['intents']:
        raise ValueError('old24 intent/snapshot prefix differs')
    rows = clean([v for v in case['corporate_ledger'] if clean(v['day']) <= PREFIX])
    if [v for v in rows if v['event_id'] in old_ids] != expected['corporate_ledger']:
        raise ValueError('old79 event ledger prefix differs')
    extras = [v for v in rows if v['event_id'] not in old_ids]
    for row in extras:
        if row.get('instrument') in old_codes or row['kind'] not in ('RECORD_DATE_OWNERSHIP','EX_DATE_ENTITLEMENT'):
            raise ValueError('new historical event is not unheld dependency evidence')
        fields = ('quantity',) if row['kind'] == 'RECORD_DATE_OWNERSHIP' else (
            'registered_quantity','cash_gross','stress_tax_reserve','capital_shares','stock_shares','taxable_stock_income')
        if any(Decimal(str(row[k])) != 0 for k in fields):
            raise ValueError('new historical dependency event changed financial state')
    return {'all_old_daily_rows':len(old_days), 'old_intents':len(expected['intents']),
            'old_events':len(old_ids), 'extra_zero_ledger_entries':len(extras), 'passed':True}


def summarize(case, initial):
    nav = {r['day']:r['equity'] for r in case['days']}
    days = [r for r in case['days'] if r['day'] > PREFIX]
    start = nav[PREFIX]; peak = start; dd = Decimal(0)
    for r in days:
        peak = max(peak, r['equity']); dd = min(dd, r['equity']/peak-1)
    if not days or days[-1]['day'] != END or len(case['intents']) != 34:
        raise ValueError('complete fixed account horizon required')
    returns = [(nav['2024-12-31']/Decimal(initial)-1)*100,
               (start/nav['2024-12-31']-1)*100, (days[-1]['equity']/start-1)*100]
    return {'2024_return_pct':float(returns[0]), '2025_return_pct':float(returns[1]),
        '2026_through_'+END:{'return_pct':float(returns[2]), 'starting_equity_CNY':str(start),
            'ending_equity_CNY':str(days[-1]['equity']), 'sessions':len(days),
            'max_drawdown_pct':float(dd*100),
            'average_exposure_pct':float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100),
            'fees_CNY':str(sum((r['fees'] for r in days),Decimal(0)))},
        'three_return_conditions_met':returns[0]>0 and returns[1]>0 and returns[2]>=10,
        'whole_day_volume_violations':case['whole_day_volume_violations'],
        'fills':len(case['fills']), 'orders':len(case['orders']), 'monthly_intents':len(case['intents'])}


def execute(request, expected, repo, base, out, preflight=False):
    if out.exists():
        raise ValueError('fresh diagnostic directory required, no overwrite/resume')
    r, inputs = authenticate(request, expected, repo, base)
    wanted = OUTPUT + ('-preflight' if preflight else '')
    if out.resolve() != (base/wanted).resolve():
        raise ValueError('fixed diagnostic output required')
    out.mkdir(parents=True)
    results = {}; holders = []; original = None; persistence = []; error = None; final_error = None
    def persist(name, value):
        nonlocal final_error
        try:
            save(out/name, value)
        except BaseException as exc:
            persistence.append({'file':name, 'error_type':type(exc).__name__, 'error':str(exc)})
            if final_error is None:
                final_error = exc
    try:
        save(out/'inputs-before.json', inputs)
        (out/'request.json').write_bytes(request.read_bytes())
        calendar, packets, lifecycles, targets, events, receipts, restorations, old_ids = load_sources(repo, base)
        persist('source_projection.json', {'events':[asdict(e) for e in events], 'event_receipts':receipts,
            'restoration_receipts':restorations, 'old_event_ids':sorted(old_ids)})
        if final_error is not None:
            raise final_error
        if not preflight:
            bars = {c:{v['date']:v for v in p['bars']} for c,p in packets.items()}
            old_codes = set(read(base/OLD_RAW/'manifest.json')['per_code_sha256'])
            for bps in r['extra_cost_bps']:
                print('continuous frozen account', bps, 'extra bp', flush=True)
                folder = out/str(bps); folder.mkdir(); expected_old = expected_prefix(base/OLD_ACCOUNT/str(bps))
                holders = []
                def factory(cal, cash, distributions, **kw):
                    account = ObservedAccount(cal, cash, distributions, expected=expected_old, lifecycles=lifecycles,
                        broker_factory=partial(ExecutionCostBroker, extra_cost_bps=bps), **kw)
                    holders.append(account)
                    return account
                try:
                    case = simulate_fixed_targets(calendar, bars, events, targets, r['initial_CNY'],
                        lifecycles=lifecycles, account_factory=factory, policy_id=CANDIDATE)
                    artifacts = write_case(folder, case)
                    prefix = verify_prefix(case, expected_old, old_ids, old_codes)
                    account = holders[0]
                    if account.prefix_checkpoint is None or len(account.exit_checks) != 136:
                        raise ValueError('complete prefix and post-exit state evidence required')
                    zero = []
                    for e in events:
                        if e.capital_per_share or e.stock_per_share:
                            q = case['ownership'][e.recorded.isoformat()].get(e.instrument, 0)
                            if q != 0:
                                raise ValueError('unverified noncash must prove zero registered ownership')
                            zero.append({'event_id':e.event_id, 'recorded':e.recorded, 'actual_owned_shares':q})
                    persist(str(bps)+'/account_observations.json', {'checkpoint':account.prefix_checkpoint,
                        'exit_checks':account.exit_checks, 'final_state':account_state(account),
                        'prefix_checks':prefix, 'unverified_noncash_zero_inventory':zero})
                    result = {'status':'RAW_DAILY_PROXY_COMPLETE_PENDING_SEPARATE_LEDGER_QA',
                        'artifact_sha256':artifacts, 'prefix':prefix, **summarize(case, r['initial_CNY'])}
                except BaseException as exc:
                    result = {'status':'STRICT_ACCOUNT_FAILURE_RETAINED', 'error_type':type(exc).__name__, 'error':str(exc)}
                    persist(str(bps)+'/error.json', result)
                    if holders:
                        account = holders[0]
                        persist(str(bps)+'/failed_account_state.json', {'account':account_state(account),
                            'prefix_checkpoint':account.prefix_checkpoint, 'exit_checks':account.exit_checks})
                    results[str(bps)] = result
                    if not isinstance(exc, (ValueError, KeyError, ArithmeticError)):
                        persist('case_results.json', results)
                        raise
                results[str(bps)] = result
                persist('case_results.json', results)
    except BaseException as exc:
        original = exc; error = {'error_type':type(exc).__name__, 'error':str(exc)}
    changed = []
    for path, h in inputs.items():
        try:
            if file_sha(path) != h:
                changed.append(path)
        except BaseException as exc:
            changed.append(path)
            if original is None:
                original = exc
                error = {'error_type':type(exc).__name__, 'error':str(exc)}
    persist('inputs-after.json', {'consumed_files':len(inputs), 'changed_or_missing':changed, 'unchanged':not changed})
    result = {'status':'PREFLIGHT_ONLY_NO_ACCOUNT_VALUATION' if preflight else 'CONTINUOUS_ACCOUNT_DIAGNOSTIC_RETAINED',
        'request_sha256':expected, 'window':[START, END], 'results_by_extra_bps':results,
        'pending_cost_cases':[] if preflight else [str(b) for b in r['extra_cost_bps'] if str(b) not in results],
        'original_error':error, 'persistence_errors':persistence, 'changed_inputs':changed,
        'complete':error is None and not changed and not persistence and (preflight or all(
            results.get(str(b),{}).get('status') == 'RAW_DAILY_PROXY_COMPLETE_PENDING_SEPARATE_LEDGER_QA' for b in r['extra_cost_bps'])),
        'historical_observed_arrival_verified':False, 'opening_liquidity_verified':False,
        'full_october_complete':False, 'sealed_2026_evidence':False,
        'separate_ledger_QA_passed':False, 'objective_achieved':False}
    persist('summary.json', result)
    if persistence:
        result['complete'] = False
        persist('finalization-error.json', result)
    if original is not None:
        raise original
    if final_error is not None:
        raise final_error
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','source-root','output-dir'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--source-preflight-only', action='store_true')
    a = parser.parse_args(argv)
    result = execute(Path(a.request), a.expected_request_sha256, Path(__file__).resolve().parents[1],
                     Path(a.source_root), Path(a.output_dir), a.source_preflight_only)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
