"""Additional source-price/execution QA without rerunning any investment account."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct


def need(value, message):
    if not value: raise ValueError(message)


def close(a, b, message):
    need(math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-5), message)


def order_evidence(order, intent, open_price, volume):
    selected = [x for x in intent['orders'] if x['instrument'] == order['instrument'] and x['side'] == order['side']]
    need(len(selected) == 1, 'executed order must have one prior-close intention')
    expected = selected[0]
    close(abs(float(order['requested_normalized_units'])), expected['normalized_units'], 'requested units match prior decision')
    units = abs(float(order['filled_normalized_units']))
    bound_passes = units <= expected['normalized_units'] + 1e-5
    if units:
        close(order['normalized_price'], open_price, 'literal source open price')
        need(volume is not None and volume > 0 and units <= volume, 'necessary whole-day capacity')
    return {'volume_fraction': units / volume if units else 0., 'requested_size_bound_passes': bound_passes,
            'excess_normalized_units': max(0., units - expected['normalized_units'])}


def validate_order(order, intent, open_price, volume):
    evidence = order_evidence(order, intent, open_price, volume)
    need(evidence['requested_size_bound_passes'], 'execution cannot exceed prior requested size')
    return evidence['volume_fraction']


def audit(provider, folder, proof_path):
    provider, folder = Path(provider), Path(folder)
    proof = json.loads(Path(proof_path).read_text()); terminal = json.loads((folder / 'terminal.json').read_text())
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    need(proof['terminal_sha256'] == sha(folder / 'terminal.json') and proof['all_inputs_outputs_unchanged'] is True, 'successful frozen CSV/window audit required')
    calendar = (provider / 'calendars/day.txt').read_text().splitlines(); indices = {d: i for i, d in enumerate(calendar)}; cache = {}
    need(calendar[-1] == '2025-12-31', 'pre2026 quote reader only')
    def value(c, f, d):
        if (c, f) not in cache:
            raw = (provider / 'features' / c.lower() / (f + '.day.bin')).read_bytes()
            v = struct.unpack('<' + str(len(raw) // 4) + 'f', raw); cache[c, f] = (int(v[0]), v[1:])
        start, data = cache[c, f]; offset = indices[d] - start
        return data[offset] if 0 <= offset < len(data) and math.isfinite(data[offset]) else None
    def rows(p):
        with p.open() as f: return list(csv.DictReader(f))
    checked = {}; all_anomalies = []
    for label in terminal['results']:
        case = folder / label; intents = json.loads((case / 'decision_intents.json').read_text()); by = {i['execution_session']: i for i in intents}
        orders = rows(case / 'orders.csv'); holdings = rows(case / 'holdings.csv'); fractions = []; anomalies = []
        for o in orders:
            evidence = order_evidence(o, by[o['session']], value(o['instrument'], 'open', o['session']), value(o['instrument'], 'volume', o['session']))
            fractions.append(evidence['volume_fraction'])
            if not evidence['requested_size_bound_passes']:
                anomaly = {'case': label, 'session': o['session'], 'instrument': o['instrument'],
                    'excess_normalized_units': evidence['excess_normalized_units'],
                    'excess_raw_share_equivalent': evidence['excess_normalized_units'] * value(o['instrument'], 'factor', o['session'])}
                anomalies.append(anomaly); all_anomalies.append(anomaly)
        for h in holdings:
            close(h['normalized_price'], value(h['instrument'], 'close', h['session']), 'literal source close mark')
        for i in intents:
            notional = sum(o['normalized_units'] * i['known_closes'][o['instrument']] for o in i['orders'] if o['side'] == 'BUY')
            need(notional <= max(0, i['cash_at_decision'] - .05 * i['equity_at_decision']) + .01, 'no execution-day sale proceeds or excess prior cash budget')
            for o in i['orders']:
                need(i['observations'][o['instrument']]['action'] == o['side'], 'order agrees with visible indicator action')
                if o['side'] == 'SELL': close(o['normalized_units'], i['holdings_at_decision'][o['instrument']], 'full known-inventory exit')
        checked[label] = {'orders_checked': len(orders), 'source_close_marks_checked': len(holdings),
                          'prior_close_budgets_checked': len(intents), 'max_whole_day_normalized_volume_fraction': max(fractions, default=0),
                          'strict_request_size_bound_passes': not anomalies, 'size_overshoot_anomalies': anomalies}
    need(proof['terminal_sha256'] == sha(folder / 'terminal.json'), 'same terminal after execution audit')
    return {'status': 'SOURCE_PRICES_MATCH_BUT_REQUEST_SIZE_BOUND_FAILS' if all_anomalies else 'PASS_LITERAL_SOURCE_OPENS_CLOSES_PRIOR_INTENTS_AND_CAPACITY_NOT_RAW_ACCOUNT_QUALIFICATION',
            'strict_execution_qualification_passes': not all_anomalies, 'size_overshoot_count': len(all_anomalies),
            'max_excess_raw_share_equivalent': max((a['excess_raw_share_equivalent'] for a in all_anomalies), default=0),
            'cases': checked, 'terminal_sha256': proof['terminal_sha256'], '2026_values_read': False,
            'same_researcher_not_independent_assurance': True, 'portfolio_rerun': False}


def main():
    p = argparse.ArgumentParser()
    for name in ('provider', 'run-dir', 'csv-proof', 'out'): p.add_argument('--' + name, required=True)
    a = p.parse_args(); result = audit(a.provider, a.run_dir, a.csv_proof)
    with Path(a.out).open('x') as f: f.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(result['status'])


if __name__ == '__main__': main()
