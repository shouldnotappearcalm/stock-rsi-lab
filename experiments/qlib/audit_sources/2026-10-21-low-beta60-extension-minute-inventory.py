"""Independent read-only potential minute-source inventory, without an account."""
import argparse
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
base = Path(args.source_root)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text())
digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
raw = base / 'low-beta60-raw-extension-20261021'
assert sha(raw / 'manifest.json') == '10f645719228d50c439e166bbfe65959b5ff517668c2ecc8ffc4fca4e1680ea7'
m = read(raw / 'manifest.json')
assert sha(base / 'low-beta60-raw-extension-independent-audit-20261021.json') == '8e13fb42e914d36ce220b785d563125a6b2529de8c62bf3c1bbaf3f62a53277c'
target = base / 'low-beta60-calendar-extension-formations-20261021/targets.json'
assert sha(target) == m['target_sha256']
targets = read(target)['low_beta60']
bars = {}
for code, h in m['per_code_sha256'].items():
    path = raw / 'codes' / (code + '.json')
    assert sha(path) == h
    bars[code] = {r['date']: r for r in read(path)['bars']}
active, skipped, seen = [], [], set()
for day, t in sorted(targets.items()):
    assert '2024-01-02' <= day <= '2026-10-13' and t['as_of'] < day
    seen.update(t['weights'])
    for code in sorted(seen):
        row = bars[code][day]
        if row['tradestatus'] == '0':
            skipped.append({'instrument': code, 'day': day, 'reason': 'SOURCE_HALT',
                            'actual_inventory_proven_zero': False, 'synthetic_price_created': False})
        else:
            assert row['tradestatus'] == '1'
            active.append([code, day])
repo = Path(__file__).resolve().parents[3]
original = read(repo / 'experiments/qlib/low-beta60-minute-gap-identities.json')
assert [p for p in active if p[1] < '2026'] == original['active_requests']
assert [p for p in skipped if p['day'] < '2026'] == original['nonexecuting_source_intervals']
sources = ('low-beta60-minutes-dev-20261021', 'tdx-fixed-order-history-20261017',
           'intraday-prefix-tape-20261017', 'return-family-minutes-dev-20261017',
           'reversal-minutes-full-20261017', 'szse-value-minutes-dev-20261017',
           'szse-value-minutes-full-20261017', 'illiquidity-minutes-dev-20261021',
           'low-risk-execution-tape-20261017', 'low-risk-feedback-tape-additions-20261017')
index = {}
manifests = {}
for s in sources:
    manifests[s] = read(base / s / 'manifest.json')
    for name, h in manifests[s]['per_session_sha256'].items():
        assert Path(name).name == name
        index.setdefault(name, []).append({'root': s, 'sha256': h})
labels = [f'{hour:02d}:{minute:02d}' for hour in (9, 10, 11, 13, 14, 15) for minute in range(60)
          if '09:31' <= f'{hour:02d}:{minute:02d}' <= '11:30' or '13:01' <= f'{hour:02d}:{minute:02d}' <= '15:00']


def inspect(code, day, packet):
    assert packet['instrument'] == code and packet['requested_day'] == day
    record = packet.get('methods', {}).get('minutes.history', packet)
    assert record['status'] == 'RESPONSE_CAPTURED'
    v = record['response']
    assert v['exchange'] == code[:2].lower() and v['code'] == code[2:] and v['trading_date'] == day
    assert type(v['market_id']) is int and v['market_id'] == (1 if code.startswith('SH') else 0)
    points = v['points']
    assert len(points) == 240
    row = bars[code][day]
    assert row['tradestatus'] == '1' and row['isST'] == '0'
    signature = []
    for i, (p, label) in enumerate(zip(points, labels)):
        assert type(p['index']) is int and p['index'] == i and p['time_label'] == label
        assert p['time'] == day + 'T' + label + ':00+08:00'
        price, volume = p['price_milli'], p['volume']
        assert type(price) is type(volume) is int and min(price, volume) >= 0
        assert Decimal(str(p['price'])) == Decimal(price) / 1000
        if volume:
            assert price > 0 and price % 10 == 0
            assert Decimal(row['low']) <= Decimal(price) / 1000 <= Decimal(row['high'])
        signature.append([p['time'], price, volume])
    assert Decimal(points[-1]['price_milli']) / 1000 == Decimal(row['close'])
    daily = Decimal(row['volume'])
    assert daily > 0 and daily == int(daily)
    assert sum(max(0, p['volume'] * 100 - 100) for p in points) <= daily
    return {'signature_sha256': digest(signature), 'points': 240,
        'nearest_hand_total_matches': sum(p['volume'] for p in points) == (daily / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)}


reused, missing, rejected, conflicts, matches = {}, [], [], [], {}
for code, day in active:
    name = code + '-' + day + '.json'
    choices = []
    for origin in index.get(name, []):
        p = base / origin['root'] / 'sessions' / name
        assert sha(p) == origin['sha256']
        choice = dict(origin)
        packet = read(p)
        if origin['root'] in ('low-risk-execution-tape-20261017', 'low-risk-feedback-tape-additions-20261017'):
            assert packet['instrument'] == code and packet['session'] == day
            choice.update(status='OUTSIDE_FROZEN_ONE_MINUTE_CONTRACT',
                          source_format='DIRECT_VENDOR_FIVE_MINUTE_OHLC_BARS',
                          reason='Cannot reconstruct frozen five one-minute samples from a five-minute OHLC bar')
            choices.append(choice)
            continue
        try:
            choice.update(inspect(code, day, packet), status='RECONSTRUCTED_SIGNATURE_PASSES_NOT_ADMITTED')
        except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
            choice.update(status='SOURCE_REJECTED', error_type=type(exc).__name__, error=str(exc))
        choices.append(choice)
    matches[name] = choices
    candidates = [c for c in choices if c['status'] != 'OUTSIDE_FROZEN_ONE_MINUTE_CONTRACT']
    if not candidates:
        missing.append([code, day])
        continue
    if len({c['signature_sha256'] for c in choices if 'signature_sha256' in c}) > 1:
        conflicts.append([code, day])
    if candidates[0]['status'] == 'SOURCE_REJECTED':
        rejected.append([code, day])
    else:
        reused[name] = {'root': candidates[0]['root'], 'sha256': candidates[0]['sha256']}
old_capture = read(base / sources[0] / 'manifest.json')
assert all(reused[n] == {'root': sources[0], 'sha256': h} for n, h in old_capture['per_session_sha256'].items())
result = {'status': 'LOW_BETA60_CONTINUOUS_POTENTIAL_MINUTE_SOURCE_INVENTORY_ONLY',
    'inventory_code_sha256': sha(__file__), 'raw_manifest_sha256': sha(raw / 'manifest.json'),
    'target_sha256': sha(target), 'window': ['2024-01-02', '2026-10-13'],
    'source_priority_fixed_before_inventory': list(sources),
    'source_manifest_sha256': {s: sha(base / s / 'manifest.json') for s in sources},
    'active_requests': active, 'nonexecuting_source_intervals': skipped, 'required_active_pairs': len(active),
    'original_pre2026_required_pairs': 1332, 'original1332_source_bytes_and_route_preserved': True,
    'required2026_pairs': sum(d > '2025-12-31' for _, d in active),
    'cached_passing_pairs': len(reused), 'uncached_pairs': len(missing), 'rejected_cached_pairs': rejected,
    'all_matching_cached_sources': sum(len(cs) for cs in matches.values()),
    'all_one_minute_cached_source_rejections': sum(c['status'] == 'SOURCE_REJECTED' for cs in matches.values() for c in cs),
    'matching_five_minute_OHLC_sources_outside_contract': sum(c['status'] == 'OUTSIDE_FROZEN_ONE_MINUTE_CONTRACT' for cs in matches.values() for c in cs),
    'cross_cache_signature_conflicts': conflicts, 'reused_session_provenance': reused, 'uncached_requests': missing,
    'all_matching_cached_source_inspections': matches, 'new_network_queries': 0,
    'admitted_for_reconstructed_execution': False, 'source_calendar_complete_October': False,
    'queue_and_impact_calibrated': False, 'historical_arrival_verified': False,
    'portfolio_returns_computed': False, 'objective_achieved': False}
with Path(args.output).open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print('potentialminute pairs', len(active), 'cached passing', len(reused), 'uncached', len(missing),
      'rejected', len(rejected), 'conflicts', len(conflicts), 'original1332bytes preserved;no network/ROI')
