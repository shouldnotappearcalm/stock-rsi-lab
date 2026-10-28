"""Separate CSV, source-price and snapshot QA for both fixed 2026 candidates.

Same researcher; ledger arithmetic reuses the previously fixed signed-SELL
checker. No signal, account, strategy or Qlib execution module is imported.
"""
import argparse
from collections import defaultdict
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct

from scripts.audit_published_strategies import audit_case
from scripts.audit_published_strategy_execution import order_evidence


def need(value, why):
    if not value: raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(folder):
    root = Path(folder)
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def rows(path):
    with Path(path).open() as f: return list(csv.DictReader(f))


def near(a, b, why):
    need(math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-7), why)


def independent_periods(day_rows, initial=1000000):
    previous = Fraction(initial); current = {}; last = ''
    for d in day_rows:
        need(d['session'] > last, 'unique ordered period rows'); last = d['session']; year = last[:4]
        nav = Fraction(d['account_value']); stock = Fraction(d['stock_value']); fee = Fraction(d['cost'])
        need(nav > 0 and fee >= 0, 'solvent finite account')
        if year not in current: current[year] = {'base': previous, 'peak': previous, 'dd': Fraction(0), 'exposure': Fraction(0), 'fees': Fraction(0), 'sessions': 0, 'orders': 0}
        p = current[year]; p['peak'] = max(p['peak'], nav); p['dd'] = min(p['dd'], nav / p['peak'] - 1)
        p['exposure'] += stock / nav; p['fees'] += fee; p['sessions'] += 1; p['orders'] += int(d['orders']); p['last'] = nav; previous = nav
    return {y: {'baseline_CNY': float(p['base']), 'ending_nav_CNY': float(p['last']),
                'net_return_pct': float((p['last'] / p['base'] - 1) * 100),
                'average_exposure_pct': float(p['exposure'] / p['sessions'] * 100),
                'max_drawdown_pct': float(p['dd'] * 100), 'sessions': p['sessions'], 'orders': p['orders'],
                'cost_CNY': float(p['fees']), 'cost_pct_start_nav': float(p['fees'] / p['base'] * 100)} for y, p in current.items()}


def assert_prefix(short, long):
    for name in ('days.csv', 'orders.csv', 'holdings.csv'):
        need(rows(short / name) == [r for r in rows(long / name) if r['session'] <= '2025-12-31'], 'identical same-version historical CSV prefix')
    need(read(short / 'decision_intents.json') == [r for r in read(long / 'decision_intents.json') if r['execution_session'] <= '2025-12-31'], 'identical historical snapshots before 2026')


def check_case(provider, case, config, metric, initial=1000000):
    calendar = (provider / 'calendars/day.txt').read_text().splitlines(); indices = {d: i for i, d in enumerate(calendar)}
    sessions = [d for d in calendar if d >= '2024-01-02']; cache = {}
    def value(code, field, day):
        key = (code, field)
        if key not in cache:
            raw = (provider / 'features' / code.lower() / (field + '.day.bin')).read_bytes()
            vals = struct.unpack('<' + str(len(raw) // 4) + 'f', raw); cache[key] = (int(vals[0]), vals[1:])
        start, vals = cache[key]; offset = indices[day] - start
        val = vals[offset] if 0 <= offset < len(vals) else float('nan')
        return val if math.isfinite(val) else None
    ledger = audit_case(case, metric, sessions, initial)
    day_rows = rows(case / 'days.csv'); history = read(case / 'decision_intents.json'); need(len(history) == len(sessions), 'all daily wakes retained')
    by_day = {d['session']: d for d in day_rows}; holdings = rows(case / 'holdings.csv'); by_hold = defaultdict(dict)
    for h in holdings:
        by_hold[h['session']][h['instrument']] = float(h['normalized_units'])
        near(h['normalized_price'], value(h['instrument'], 'close', h['session']), 'literal source close mark')
    literal = 0; by_intent = {}
    for execution, intent in zip(sessions, history):
        asof = calendar[indices[execution] - 1]; by_intent[execution] = intent
        need(intent['execution_session'] == execution and intent['as_of'] == asof + 'T15:05:00+08:00', 'next actual session after 15:05 wake')
        need(intent['latest_decision_price_read'] == asof and intent['execution_exchange_queried_for_decision'] is False, 'no execution-day market in decision')
        payload = {k: v for k, v in intent.items() if k != 'snapshot_sha256'}
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        need(hashlib.sha256(raw).hexdigest() == intent['snapshot_sha256'], 'literal snapshot hash')
        prior = by_day.get(asof)
        near(intent['equity_at_decision'], float(prior['account_value']) if prior else initial, 'actual prior NAV')
        near(intent['cash_at_decision'], float(prior['cash']) if prior else initial, 'actual prior cash')
        need(set(intent['holdings_at_decision']) == set(by_hold.get(asof, {})), 'actual prior holdings identities')
        for c, q in by_hold.get(asof, {}).items(): near(intent['holdings_at_decision'][c], q, 'actual prior owned units')
        for c in config['symbols']:
            expected = []
            for d in reversed(calendar[:indices[execution]]):
                vol, price = value(c, 'volume', d), value(c, 'close', d)
                if vol is not None and vol > 0 and price is not None and price > 0:
                    expected.append([d, price])
                    if len(expected) == config['history']: break
            expected.reverse(); need(expected == intent['histories'][c], 'all literal historical indicator inputs')
            need(all(d <= asof for d, _ in expected), 'no future history observations')
            literal += len(expected)
            near(intent['known_closes'][c], value(c, 'close', asof), 'known close')
            near(intent['known_factors'][c], value(c, 'factor', asof), 'known factor')
        budget = sum(o['normalized_units'] * intent['known_closes'][o['instrument']] for o in intent['orders'] if o['side'] == 'BUY')
        need(budget <= max(0., intent['cash_at_decision'] - .05 * intent['equity_at_decision']) + .01, 'same prior cash budget, no unfilled proceeds')
        for o in intent['orders']:
            need(intent['observations'][o['instrument']]['action'] == o['side'], 'order agrees with recorded indicator')
            if o['side'] == 'SELL': near(o['normalized_units'], intent['holdings_at_decision'][o['instrument']], 'full known-inventory exit')
    orders = rows(case / 'orders.csv'); max_volume = 0.
    extra = int(case.parent.name)
    for o in orders:
        evidence = order_evidence(o, by_intent[o['session']], value(o['instrument'], 'open', o['session']), value(o['instrument'], 'volume', o['session']))
        need(evidence['requested_size_bound_passes'], 'no fill larger than requested')
        max_volume = max(max_volume, evidence['volume_fraction'])
        notional = abs(float(o['signed_trade_value'])); fee = float(o['cost'])
        near(fee, max(5, notional * ((5 if o['side'] == 'BUY' else 15) + extra) / 10000) if notional else 0, 'unchanged side fees and stress')
    periods = independent_periods(day_rows, initial)
    need(set(periods) == set(metric['per_year']), 'all complete evaluated years')
    for year, vals in periods.items():
        for key, val in vals.items(): near(val, metric['per_year'][year][key], 'independent period metric ' + year + '/' + key)
    return {**ledger, 'periods': periods, 'snapshots_checked': len(history), 'literal_history_values_checked': literal,
            'strict_size_bound_passes': True, 'max_normalized_whole_day_volume_fraction': max_volume}


def audit(root, data, old_run, request, expected, folder):
    need(sha(request) == expected, 'frozen request hash')
    req = read(request); terminal = read(folder / 'terminal.json'); before = tree(folder)
    need(terminal['complete'] is True and terminal['all_inputs_unchanged'] is True and terminal['request_sha256'] == expected, 'complete unchanged forward experiment')
    need(terminal['candidates'] == ['macd', 'rsi'] and terminal['average_exposure_is_hard_gate'] is False, 'human fixed two-candidate scope; no exposure gate')
    need(terminal['2026_results_used_to_change_rules'] is False and terminal['raw_share_or_investment_qualified'] is False, 'frozen application, explicit evidence boundary')
    need(before == {**terminal['artifact_sha256'], 'terminal.json': sha(folder / 'terminal.json')}, 'whole actual output closure')
    def unchanged():
        return (tree(data) == req['data_sha256'] and all(sha(root / n) == h for n, h in {**req['method_sha256'], **req['public_sha256']}.items())
                and all(sha(old_run / n) == h for n, h in req['original_case_sha256'].items()))
    need(unchanged(), 'all frozen inputs before audit')
    results = {}
    for label, metric in terminal['results'].items():
        phase, extra, name = label.split('/'); provider = data / ('pre2026' if phase == 'baseline' else 'through2026')
        results[label] = check_case(provider, folder / label, req['configs'][name], metric)
        if phase == 'baseline' and req['source_historical_prefixes_identical']: assert_prefix(old_run / extra / name, folder / label)
        if phase == 'forward': assert_prefix(folder / 'baseline' / extra / name, folder / label)
    need(len(results) == 8, 'all baseline and forward accounts; no winner-only report')
    need(unchanged() and tree(folder) == before, 'all inputs and outputs unchanged after audit')
    return {'status': 'PASS_EIGHT_CONTINUOUS_ACCOUNTS_SOURCE_SNAPSHOTS_AND_YEAR2026_BASELINES',
            'request_sha256': expected, 'terminal_sha256': sha(folder / 'terminal.json'), 'cases': results,
            'all_inputs_outputs_unchanged': True, 'both_candidates_reported': True, 'no_yearly_account_reset': True,
            'average_exposure_is_hard_gate': False, 'same_researcher_not_independent_assurance': True,
            'raw_share_or_investment_qualified': False}


def main():
    p = argparse.ArgumentParser()
    for n in ('data', 'old-run', 'request', 'expected-sha256', 'run-dir', 'out'): p.add_argument('--' + n, required=True)
    a = p.parse_args(); root = Path(__file__).resolve().parents[1]
    result = audit(root, Path(a.data), Path(a.old_run), Path(a.request), a.expected_sha256, Path(a.run_dir))
    with Path(a.out).open('x') as f: f.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(result['status'])


if __name__ == '__main__': main()
