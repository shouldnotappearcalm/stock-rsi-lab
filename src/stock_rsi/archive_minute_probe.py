"""Compare archived bars with frozen daily sources, without admitting fills.

No rounding, timestamp shifting, account, target generation or ROI calculation.
The parser receives only explicitly selected development sessions. A columnar
reader may internally decode other rows; this is not an OS data boundary.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

FIELDS = ('symbol', 'exchange', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover')


def need(value, message):
    if not value:
        raise ValueError(message)


def validate_pairs(pairs):
    need(type(pairs) is list and bool(pairs), 'explicit development pairs required')
    need(all(type(p) is list and len(p) == 2 and type(p[0]) is str and type(p[1]) is str
             for p in pairs), 'canonical instrument/session pairs required')
    need(pairs == sorted(pairs) and len({tuple(p) for p in pairs}) == len(pairs),
         'sorted unique pairs required')
    for code, day in pairs:
        parsed = date.fromisoformat(day)
        need(parsed.isoformat() == day and '2024-01-01' <= day <= '2025-12-31'
             and code in ('SH603056', 'SZ002505'), 'only fixed missing development sources allowed')


def selected_parquet_rows(path, pairs):
    """Arrow filters precede Python row materialization; retain original floats.

    The whole immutable object can contain later years. Arrow can decode a
    mixed row group internally; no claim of physical future-data isolation.
    """
    validate_pairs(pairs)
    import pyarrow.parquet as pq
    filters = []
    for _, day in pairs:
        start = datetime.fromisoformat(day)
        filters.append([('timestamp', '>=', start), ('timestamp', '<', start + timedelta(days=1))])
    table = pq.read_table(path, columns=list(FIELDS), filters=filters)
    rows = table.to_pylist()
    wanted = {day for _, day in pairs}
    need(all(type(r['timestamp']) is datetime and r['timestamp'].tzinfo is None
             and r['timestamp'].date().isoformat() in wanted for r in rows),
         'unrequested or aware archive timestamp returned by reader')
    return rows


def compare_session(code, day, rows, daily):
    validate_pairs([[code, day]])
    need(daily['date'] == day and daily['tradestatus'] == '1', 'bound active daily source required')
    need(type(rows) is list and bool(rows), 'archive session missing')
    labels, values, volumes = [], [], []
    for row in rows:
        need(set(row) == set(FIELDS) and row['symbol'] == code[2:] and row['exchange'] == code[:2],
             'archive fields or instrument differ')
        at = row['timestamp']
        need(type(at) is datetime and at.tzinfo is None and at.date().isoformat() == day
             and at.second == at.microsecond == 0, 'source minute clock differs')
        label = at.strftime('%H:%M')
        need('09:30' <= label <= '11:30' or '13:00' <= label <= '15:00', 'outside explicit session')
        labels.append(label)
        prices = {k: Decimal(str(row[k])) for k in ('open', 'high', 'low', 'close')}
        need(all(v.is_finite() and v >= 0 for v in prices.values()), 'nonfinite/negative source price')
        need(prices['low'] <= min(prices['open'], prices['close'])
             <= max(prices['open'], prices['close']) <= prices['high'], 'inconsistent source OHLC')
        volume = row['volume']
        need(type(volume) is int and volume >= 0, 'integer nonnegative share volume required')
        need(not volume or min(prices.values()) > 0, 'positive-volume zero price')
        turnover = Decimal(str(row['turnover']))
        need(turnover.is_finite() and turnover >= 0, 'nonfinite/negative source turnover')
        values.append(prices)
        volumes.append(volume)
    need(labels == sorted(set(labels)), 'unsorted/duplicate minute labels')
    end_labels = [f'{h:02d}:{m:02d}' for h in (9, 10, 11, 13, 14, 15) for m in range(60)
                  if '09:31' <= f'{h:02d}:{m:02d}' <= '11:30'
                  or '13:01' <= f'{h:02d}:{m:02d}' <= '15:00']
    # All price checks are exact Decimal comparisons of the published float
    # text. A near-cent archive value is a failed comparison, never rounded.
    checks = {
        'exact_existing_240_end_labels': labels == end_labels,
        'all_prices_exact_cent_without_rounding': all(v == v.quantize(Decimal('.01'))
                                                     for item in values for v in item.values()),
        'first_open_matches': values[0]['open'] == Decimal(daily['open']),
        'highest_matches': max(p['high'] for p in values) == Decimal(daily['high']),
        'lowest_matches': min(p['low'] for p in values) == Decimal(daily['low']),
        'last_close_matches': values[-1]['close'] == Decimal(daily['close']),
        'total_volume_matches': sum(volumes) == Decimal(daily['volume']),
    }
    return {'instrument': code, 'day': day, 'rows': len(rows), 'first_label': labels[0],
            'last_label': labels[-1], 'labels': labels, 'source_checks': checks,
            'archive_total_volume_shares': sum(volumes), 'daily_volume_shares': daily['volume'],
            'all_numeric_and_existing_label_checks_pass': all(checks.values()),
            'upstream_providers_independently_authenticated': False,
            'minute_interval_semantics_authenticated': False,
            'admitted_for_reconstructed_execution': False}
