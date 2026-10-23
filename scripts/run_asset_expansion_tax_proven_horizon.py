"""One authenticated2026 tax proof; frozen investments/account core unchanged."""
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
from scripts import run_asset_expansion_raw_horizon as v1
from stock_rsi.data import digest
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
PLAN = 'docs/research/asset-expansion-2026-tax-proven-account-plan-2026-10-23.md'
OUTPUT = 'asset-expansion-tax-proven-account-20261023'
REVIEW = 'experiments/qlib/asset-expansion-2026-tax-source-reviewed.json'
REVIEW_SHA = 'ba0d2e73589d7973b9ac082216590351692dd9dec8981592e36039dd65799178'
PDF = 'SH603737-1225328631.pdf'
PDF_SHA = 'f6b3f28129ccf65adf1d3a1be7fba7c1c6a7eb062550b84e6605072cdb6ea0e0'
ROW_SHA = '0c8930d524a9a657993f8fa516adf68f7abc0ddf2a023df6ab26b3027bc9e479'
STRICT = 'asset-expansion-continuous-account-20261023'
NEW_METHODS = ('scripts/run_asset_expansion_tax_proven_horizon.py',
               'tests/test_asset_expansion_tax_proven_horizon.py', PLAN)


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(clean(value), indent=2) + '\n')


def checked_review(repo, base):
    private = base/'asset-expansion-SH603737-tax-source-review-v2-20261023.json'
    if file_sha(repo/REVIEW) != REVIEW_SHA or file_sha(private) != REVIEW_SHA:
        raise ValueError('exact independently checked primary receipt required')
    r = read(repo/REVIEW)
    facts = r['primary_facts']
    if (r['status'] != 'CACHED_ISSUER_TAX_TERMS_AND_BOTH_STRICT_FAILURES_CHECKED'
            or r['changed_inputs'] or r['pages'] != 4 or r['both_extractors_all_pages_checked'] is not True
            or r['primary_sha256'] != PDF_SHA or len(r['all_bound_sha256']) != 1118
            or facts != {'instrument':'SH603737','notice_number':'2026-030','announced':'2026-05-26',
                'recorded':'2026-05-29','ex_date':'2026-06-01','listed':'2026-06-01','pay_date':'2026-06-01',
                'gross_cash_per_share':'0.068','capital_per_share':'0.2',
                'issuer_explicit_share_premium_and_no_tax_statement':True,'statutory_tax_certification':False}):
        raise ValueError('specific complete issuer event proof required')
    for name, h in r['all_bound_sha256'].items():
        if file_sha(name) != h:
            raise ValueError('reviewed source ancestry changed')
    if file_sha(base/r['primary_file']) != PDF_SHA:
        raise ValueError('reviewed primary PDF changed')
    return r


def dependency_contract(repo, base):
    contract = v1.dependency_contract(repo, base)
    r = checked_review(repo, base)
    paths = {Path(p):h for p,h in r['all_bound_sha256'].items()}
    paths[repo/REVIEW] = REVIEW_SHA
    paths[base/'asset-expansion-SH603737-tax-source-review-v2-20261023.json'] = REVIEW_SHA
    for name in NEW_METHODS:
        paths[repo/name] = file_sha(repo/name)
    for path, h in paths.items():
        path = path.resolve()
        for kind, parent in (('repo',repo.resolve()),('source',base.resolve())):
            if path.is_relative_to(parent):
                contract[kind+'/'+str(path.relative_to(parent))] = h
                break
        else:
            raise ValueError('review binding outside declared roots')
    return contract


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
    if (r['status'] != 'FROZEN_ONE_TAX_PROOF_UNCHANGED_ACCOUNT_THROUGH20261021'
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


def prove_one_event(packets, calendar, events, receipts, doc):
    expected = {'instrument':'SH603737','day':'2026-05-26','file':PDF,'sha256':PDF_SHA}
    if doc != expected:
        raise ValueError('exact reviewed issuer/date/PDF required')
    rows = [r for r in packets['SH603737']['distributions'] if r['dividOperateDate'] == '2026-06-01']
    if len(rows) != 1 or digest(rows[0]) != ROW_SHA:
        raise ValueError('exact original source economics required')
    new, new_receipts = compile_distribution_events(packets, {'documents':[doc],
        'capital_tax':{'SH603737|2026-06-01':{'verified_exempt':True,'source_file':PDF,'source_sha256':PDF_SHA}},
        'cash_overrides':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[]}, calendar)
    if len(new) != len(events) or len(new_receipts) != len(receipts):
        raise ValueError('event universe changed')
    mapping = {}
    for old, proven, before, after in zip(events,new,receipts,new_receipts):
        if old.instrument == 'SH603737' and old.ex_date.isoformat() == '2026-06-01':
            a = asdict(old); b = asdict(proven)
            a.pop('event_id'); b.pop('event_id')
            if a.pop('capital_tax_exempt_verified') is not False or b.pop('capital_tax_exempt_verified') is not True or a != b:
                raise ValueError('proof changed event economics or timing')
            x = dict(before); y = dict(after)
            for row in (x,y):
                for field in ('event_id','primary_source_sha256','requires_zero_record_ownership_if_tax_unverified'):
                    row.pop(field)
            if (x != y or before['primary_source_sha256'] != [] or after['primary_source_sha256'] != [PDF_SHA]
                    or after['requires_zero_record_ownership_if_tax_unverified'] is not False):
                raise ValueError('proof changed original source receipt')
            mapping[old.event_id] = proven.event_id
        elif old != proven or before != after:
            raise ValueError('unrelated event changed')
    if len(mapping) != 1:
        raise ValueError('exactly one proof/identity change required')
    return new, new_receipts, mapping


def load_sources(repo, base):
    calendar, packets, lifecycles, targets, events, receipts, restorations, old_ids = v1.load_sources(repo, base)
    checked_review(repo, base)
    events, receipts, mapping = prove_one_event(packets, calendar, events, receipts,
        {'instrument':'SH603737','day':'2026-05-26','file':PDF,'sha256':PDF_SHA})
    if len(events) != 141 or sum(x['requires_zero_record_ownership_if_tax_unverified'] for x in receipts) != 3:
        raise ValueError('complete141 events and exactly3 unverified noncash events required')
    old_events = read(base/OLD_ACCOUNT/'source_projection.json')['events']
    if clean([asdict(e) for e in events if e.event_id in old_ids]) != old_events:
        raise ValueError('original79 identities changed')
    return calendar, packets, lifecycles, targets, events, receipts, restorations, old_ids, mapping


def verify_partial(current, expected, mapping):
    projected = copy.deepcopy(expected)
    projected['entitlements'] = {mapping.get(k,k):v for k,v in projected['entitlements'].items()}
    for row in projected['corporate_ledger']:
        row['event_id'] = mapping.get(row['event_id'],row['event_id'])
    if clean(current) != projected:
        raise ValueError('prior partial account state differs before tax-proven event')
    return True


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


class ObservedAccount(v1.ObservedAccount):
    def __init__(self, *args, expected_partial, event_id_map, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_partial = expected_partial; self.event_id_map = event_id_map
        self.partial_verified = False

    def start_day(self, day):
        if day == date(2026,6,1):
            verify_partial(account_state(self), self.expected_partial, self.event_id_map)
            self.partial_verified = True
        if day > date(2026,6,1) and not self.partial_verified:
            raise ValueError('advancement without prior partial-state verification')
        super().start_day(day)


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


def verify_capital_credit(case, account, mapping):
    eid = next(iter(mapping.values()))
    entries = [x for x in case['corporate_ledger'] if x['event_id'] == eid]
    registered = [x for x in entries if x['kind'] == 'RECORD_DATE_OWNERSHIP']
    ex = [x for x in entries if x['kind'] == 'EX_DATE_ENTITLEMENT']
    listed = [x for x in entries if x['kind'] == 'CAPITAL_SHARES_LISTED']
    claims = [x for x in account.stock_claims if x['event_id'] == eid]
    if (len(registered) != 1 or registered[0]['quantity'] != 2700 or len(ex) != 1
            or ex[0]['registered_quantity'] != 2700 or ex[0]['capital_shares'] != 540
            or len(listed) != 1 or listed[0]['quantity'] != 540
            or len(claims) != 1 or claims[0]['quantity'] != 540 or claims[0]['credited'] is not True):
        raise ValueError('actual authenticated integer credit differs from frozen partial trajectory')
    return {'event_id':eid,'recorded_quantity':2700,'capital_shares':540,'credited_once':True}


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
        calendar, packets, lifecycles, targets, events, receipts, restorations, old_ids, mapping = load_sources(repo, base)
        persist('source_projection.json', {'events':[asdict(e) for e in events], 'event_receipts':receipts,
            'restoration_receipts':restorations, 'old_event_ids':sorted(old_ids), 'event_id_map':mapping})
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
                        expected_partial=read(base/STRICT/str(bps)/'failed_account_state.json')['account'], event_id_map=mapping,
                        broker_factory=partial(ExecutionCostBroker, extra_cost_bps=bps), **kw)
                    holders.append(account)
                    return account
                try:
                    case = simulate_fixed_targets(calendar, bars, events, targets, r['initial_CNY'],
                        lifecycles=lifecycles, account_factory=factory, policy_id=CANDIDATE)
                    artifacts = write_case(folder, case)
                    prefix = verify_prefix(case, expected_old, old_ids, old_codes)
                    account = holders[0]
                    if account.prefix_checkpoint is None or len(account.exit_checks) != 136 or not account.partial_verified:
                        raise ValueError('complete prefix and post-exit state evidence required')
                    zero = []
                    for e in events:
                        if (e.capital_per_share and not e.capital_tax_exempt_verified
                                or e.stock_per_share and not e.stock_tax_basis_verified):
                            q = case['ownership'][e.recorded.isoformat()].get(e.instrument, 0)
                            if q != 0:
                                raise ValueError('unverified noncash must prove zero registered ownership')
                            zero.append({'event_id':e.event_id, 'recorded':e.recorded, 'actual_owned_shares':q})
                    capital = verify_capital_credit(case, account, mapping)
                    persist(str(bps)+'/account_observations.json', {'checkpoint':account.prefix_checkpoint,
                        'exit_checks':account.exit_checks, 'final_state':account_state(account),
                        'prefix_checks':prefix, 'unverified_noncash_zero_inventory':zero,
                        'prior_partial_state_verified':account.partial_verified, 'verified_capital_credit':capital})
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
