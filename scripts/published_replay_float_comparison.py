"""Narrow cross-process f64 comparison; exact trades/market inputs remain required."""
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

MAX_ULPS = 8


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    with Path(path).open() as f: return list(csv.DictReader(f))


def ulps(a, b):
    a, b = float(a), float(b)
    if not all(math.isfinite(x) and x >= 0 for x in (a, b)): raise ValueError('finite nonnegative replay account values required')
    return abs(struct.unpack('>Q', struct.pack('>d', a))[0] - struct.unpack('>Q', struct.pack('>d', b))[0])


def snapshot_hash_valid(row):
    payload = {k: v for k, v in row.items() if k != 'snapshot_sha256'}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest() == row['snapshot_sha256']


def compare_original(short, long):
    """Only original-vs-rerun NAV/weights may differ by <=8 representable values.

    Four positive account terms (cash + three fixed holdings) summed in
    different hash iteration orders can have a few ULPs of roundoff. There is
    no currency/return percentage tolerance and no change to any calculation.
    """
    short, long = Path(short), Path(long); changed = 0; maximum = 0; checked = 0
    allowed = {'days.csv': {'account_value'}, 'orders.csv': set(), 'holdings.csv': {'weight'}}
    for name, permitted in allowed.items():
        a = rows(short / name); b = [r for r in rows(long / name) if r['session'] <= '2025-12-31']
        if len(a) != len(b): raise ValueError('original replay row count changed')
        for x, y in zip(a, b):
            if set(x) != set(y): raise ValueError('original replay schema changed')
            for k in x:
                if x[k] == y[k]: continue
                if k not in permitted: raise ValueError('original replay non-roundoff field changed: ' + name + '/' + k)
                distance = ulps(x[k], y[k])
                if distance > MAX_ULPS: raise ValueError('original replay exceeds machine roundoff bound')
                maximum = max(maximum, distance); changed += 1
            checked += 1
    a = read(short / 'decision_intents.json'); b = [r for r in read(long / 'decision_intents.json') if r['execution_session'] <= '2025-12-31']
    if len(a) != len(b): raise ValueError('original snapshot count changed')
    for x, y in zip(a, b):
        if not snapshot_hash_valid(x) or not snapshot_hash_valid(y): raise ValueError('each snapshot must authenticate its own exact bytes')
        for k in set(x) | set(y):
            if k == 'snapshot_sha256': continue
            if x.get(k) == y.get(k): continue
            if k != 'equity_at_decision': raise ValueError('original snapshot market/account/order evidence changed: ' + k)
            distance = ulps(x[k], y[k])
            if distance > MAX_ULPS: raise ValueError('original decision NAV exceeds machine roundoff bound')
            maximum = max(maximum, distance); changed += 1
    return {'original_csv_rows_checked': checked, 'original_snapshots_checked': len(a), 'machine_roundoff_fields': changed,
            'max_ulp_distance': maximum, 'ulp_bound': MAX_ULPS, 'all_orders_and_market_history_exact': True,
            'changes_account_calculations_or_trades': False}
