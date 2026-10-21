"""Separate conditional archive interpretation; never overrides the old gate.

Premises: original prices lie on the stated cent grid, public floats are exact
binary32 promotions, and a minute label denotes either its start or its end.
The publisher has not certified those premises or historical arrival. This
module produces engineering scenario inputs, not authenticated market events.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
import math
import struct

from stock_rsi.archive_minute_probe import compare_session, need
from stock_rsi.calendar import SHANGHAI
from stock_rsi.data import digest
from stock_rsi.time import iso

CONTRACT = 'BINARY32_UNIQUE_CENT_CLOCK_INTERSECTION_V1'


def _float(bits):
    return struct.unpack('>f', struct.pack('>I', bits))[0]


def _ceil(value):
    return -(-value.numerator // value.denominator)


def inverse_binary32_cent(value):
    """Find the unique cent integer in an exact IEEE754 rounding preimage.

    Uses rational midpoints and tie-to-even, then verifies bitwise roundtrip.
    No price-dependent epsilon or nearest-cent fallback. Multiple candidates,
    arbitrary binary64 values, negative zero and unsupported extremes fail.
    """
    need(type(value) is float and math.isfinite(value) and value >= 0,
         'finite nonnegative published float required')
    try:
        packed = struct.pack('>f', value)
    except OverflowError:
        raise ValueError('outside finite binary32 representation') from None
    bits = struct.unpack('>I', packed)[0]
    need(_float(bits) == value and bits < 0x7f7fffff,
         'exact nonnegative finite binary32 promotion required')
    if bits == 0:
        return Decimal('0.00')
    current = Fraction.from_float(value)
    lower = (Fraction.from_float(_float(bits - 1)) + current) / 2
    upper = (current + Fraction.from_float(_float(bits + 1))) / 2
    first, last = _ceil(lower * 100), (upper * 100).__floor__()
    need(last - first <= 2, 'binary32 preimage admits multiple cent prices')
    candidates = []
    for cents in range(first, last + 1):
        exact = Fraction(cents, 100)
        if lower < exact < upper or (bits % 2 == 0 and exact in (lower, upper)):
            candidates.append(cents)
    need(len(candidates) == 1, 'exactly one cent-grid preimage required')
    price = Decimal(candidates[0]).scaleb(-2)
    need(struct.pack('>f', float(price)) == packed, 'cent-grid bitwise roundtrip failed')
    return price


def _closing_labels():
    return [f'{h:02d}:{m:02d}' for h in (9,10,11,13,14,15) for m in range(60)
            if '09:31' <= f'{h:02d}:{m:02d}' <= '11:30'
            or '13:01' <= f'{h:02d}:{m:02d}' <= '15:00']


def archive_scenario_windows(code, day, rows, daily):
    """Retain all241 source rows; use only192 unambiguous interior labels.

    A label t can describe [t-1,t] or [t,t+1]. Only labels with both intervals
    contained in the fixed five-minute window contribute volume/prices. Thus
    every selected row is complete by its window end in either interpretation.
    Boundary/auction rows remain in the audit and whole-day reconciliation.
    """
    original = compare_session(code, day.isoformat(), rows, daily)
    labels = ['09:30'] + _closing_labels()
    need(original['labels'] == labels and original['source_checks']['total_volume_matches'],
         'all241 source labels and exact original daily volume required')
    decoded, bylabel = [], {}
    for row in rows:
        values = {key: inverse_binary32_cent(row[key]) for key in ('open','high','low','close')}
        need(values['low'] <= min(values['open'], values['close'])
             <= max(values['open'], values['close']) <= values['high'], 'decoded OHLC order changed')
        item = {'timestamp': row['timestamp'].isoformat(),
                'raw_price_binary32_bits': {k: struct.pack('>f', row[k]).hex() for k in values},
                'decoded_cent_prices': {k: str(v) for k,v in values.items()},
                'volume_shares': row['volume']}
        decoded.append(item)
        bylabel[row['timestamp'].strftime('%H:%M')] = (row, values, item)
    for key, value in {'open': Decimal(decoded[0]['decoded_cent_prices']['open']),
                       'high': max(Decimal(r['decoded_cent_prices']['high']) for r in decoded),
                       'low': min(Decimal(r['decoded_cent_prices']['low']) for r in decoded),
                       'close': Decimal(decoded[-1]['decoded_cent_prices']['close'])}.items():
        need(value == Decimal(daily[key]), 'decoded OHLC differs from unchanged original daily source')
    ends = [label for label in _closing_labels() if int(label[-2:]) % 5 == 0]
    windows, used = [], set()
    for label in ends:
        end = datetime.fromisoformat(day.isoformat() + 'T' + label).replace(tzinfo=SHANGHAI)
        start = end - timedelta(minutes=5)
        selected = [(start + timedelta(minutes=i)).strftime('%H:%M') for i in (1,2,3,4)]
        block = [bylabel[t] for t in selected]
        need(not (set(selected) & used), 'a source minute cannot fund multiple windows')
        used.update(selected)
        traded = [values for row,values,_ in block if row['volume'] > 0]
        evidence = {'contract': CONTRACT, 'security_id': code, 'day': day.isoformat(),
                    'start': iso(start), 'end': iso(end), 'selected_rows': [r for _,_,r in block]}
        windows.append({'security_id': code, 'start': iso(start), 'end': iso(end),
                        'available_at': iso(end), 'volume_lower_shares': sum(r['volume'] for r,_,_ in block),
                        'buy_price': str(max(v['high'] for v in traded)) if traded else None,
                        'sell_price': str(min(v['low'] for v in traded)) if traded else None,
                        'evidence_id': digest(evidence)})
    excluded = [{'timestamp': r['timestamp'], 'volume_shares': r['volume_shares'],
                 'reason': 'BOUNDARY_OR_OPENING_LABEL_NOT_USED_FOR_EXECUTION'}
                for r in decoded if r['timestamp'][11:16] not in used]
    total = sum(row['volume'] for row in rows)
    retained = sum(w['volume_lower_shares'] for w in windows)
    need(len(windows) == 48 and len(used) == 192 and len(excluded) == 49
         and retained + sum(r['volume_shares'] for r in excluded) == total,
         'complete minute classification and share-volume conservation required')
    return {'contract': CONTRACT, 'instrument': code, 'day': day.isoformat(), 'windows': windows,
            'decoded_price_audit': decoded, 'unused_for_execution': excluded,
            'original_source_comparison': original, 'whole_day_volume_shares': total,
            'safe_window_volume_shares': retained,
            'conditional_clock_hypotheses': ['LABEL_IS_INTERVAL_START', 'LABEL_IS_INTERVAL_END'],
            'price_grid_and_binary32_encoding_are_explicit_premises': True,
            'source_rows_rewritten_or_discarded': False,
            'original_source_admission_overridden': False,
            'authenticated_provider_or_interval_semantics': False,
            'historical_arrival_verified': False,
            'admitted_for_original_reconstructed_execution': False}
