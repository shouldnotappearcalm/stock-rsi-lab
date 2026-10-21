"""Append source observations to a fixed Oct20 cutoff; never execute a strategy."""
import copy
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json
from scripts.capture_illiquidity_raw_development import calendar_diagnostic, unwrap_vendor_response
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS, numeric, source_code
from scripts.fundamental_query_journal import QueryJournal, digest, file_sha

START, OLD_END, TAIL_END, END = '2023-12-29', '2026-10-13', '2026-10-16', '2026-10-20'
FIRST = '2026-10-14'


def canonical_day(value):
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError('canonical source date required')
    return value


def validate_bars20(code, fields, rows):
    if tuple(fields) != BAR_FIELDS:
        raise ValueError('unadjusted bar schema changed')
    result = []
    for values in rows:
        if len(values) != len(fields):
            raise ValueError('bar column count changed')
        r = dict(zip(fields, values))
        if (r['code'] != source_code(code) or not START <= canonical_day(r['date']) <= END
                or r['adjustflag'] != '3' or r['tradestatus'] not in ('0', '1') or r['isST'] not in ('0', '1')):
            raise ValueError('bar issuer, cutoff or historical state changed')
        for k in ('open', 'high', 'low', 'close', 'preclose', 'volume', 'amount'):
            if r[k] and numeric(r[k]) < 0:
                raise ValueError('negative source amount')
        if r['tradestatus'] == '1':
            if any(not r[k] or numeric(r[k]) <= 0 for k in ('open', 'high', 'low', 'close', 'preclose', 'volume')):
                raise ValueError('trading bar lacks prices or volume')
            if (numeric(r['high']) < max(numeric(r['open']), numeric(r['close']))
                    or numeric(r['low']) > min(numeric(r['open']), numeric(r['close']))):
                raise ValueError('OHLC bounds inconsistent')
        result.append(r)
    if [r['date'] for r in result] != sorted({r['date'] for r in result}):
        raise ValueError('ordered unique source bars required')
    return result


def validate_dividends20(code, fields, rows, year=2026):
    if tuple(fields) != DIVIDEND_FIELDS:
        raise ValueError('distribution schema changed')
    result, excluded, identities = [], [], set()
    for values in rows:
        if len(values) != len(fields):
            raise ValueError('distribution column count changed')
        r = dict(zip(fields, values))
        if r['code'] != source_code(code):
            raise ValueError('distribution issuer changed')
        at = r['dividOperateDate']
        if not at:
            excluded.append({'reason': 'MISSING_OPERATE_DATE', 'record': r})
            continue
        if int(canonical_day(at)[:4]) != year:
            raise ValueError('distribution operation year changed')
        if at > END or at < START:
            excluded.append({'reason': 'AFTER_CAPTURE_CUTOFF' if at > END else 'BEFORE_CAPTURE_WINDOW', 'record': r})
            continue
        for k in ('dividCashPsBeforeTax', 'dividStocksPs', 'dividReserveToStockPs'):
            if r[k] and numeric(r[k]) < 0:
                raise ValueError('negative distribution ratio')
        key = digest(r)
        if key in identities:
            raise ValueError('duplicate distribution record')
        identities.add(key)
        result.append(r)
    return result, excluded


def validate_adjustments20(code, fields, rows):
    if tuple(fields) != ADJUST_FIELDS:
        raise ValueError('adjustment schema changed')
    result = []
    for values in rows:
        if len(values) != len(fields):
            raise ValueError('adjustment column count changed')
        r = dict(zip(fields, values))
        if r['code'] != source_code(code) or not FIRST <= canonical_day(r['dividOperateDate']) <= END:
            raise ValueError('adjustment outside requested issuer/window')
        if any(not r[k] or numeric(r[k]) <= 0 for k in ADJUST_FIELDS[2:]):
            raise ValueError('positive adjustment factors required')
        result.append(r)
    if len(result) != len({digest(r) for r in result}):
        raise ValueError('duplicate adjustment')
    return result


def load_dividend_reuse(capture_dir, packet, expected_old_request_sha):
    """Authenticate original request/reservation/response bytes and current-year scope."""
    base = Path(capture_dir).resolve()
    receipt = packet['source_query_receipts']['dividend2026']
    paths = {}
    for key in ('request', 'reserved', 'response'):
        name = receipt[key + '_file']
        p = (base / name).resolve()
        if Path(name).is_absolute() or not p.is_relative_to(base) or file_sha(p) != receipt[key + '_sha256']:
            raise ValueError('reused dividend artifact bytes/path changed')
        paths[key] = p
    identity = json.loads(paths['request'].read_text())
    expected = {'source': 'BaoStock', 'instrument': packet['instrument'], 'component': 'dividend2026',
                'parameters': {'year': '2026', 'yearType': 'operate'},
                'low_beta60_extension_request_sha256': expected_old_request_sha}
    key = digest(identity)
    if identity != expected or paths['request'] != base / 'queries' / key / 'request.json':
        raise ValueError('full-year original dividend query identity changed')
    if (paths['reserved'] != paths['request'].parent / 'reserved-1.json'
            or paths['response'] != paths['request'].parent / 'response-1.json'):
        raise ValueError('single-attempt dividend chain required')
    reservation = json.loads(paths['reserved'].read_text())
    response = json.loads(paths['response'].read_text())
    if (reservation['identity_sha256'] != key or reservation['attempt'] != 1
            or response['identity_sha256'] != key or response['status'] != 'CAPTURED'
            or response['reservation_sha256'] != file_sha(paths['reserved'])
            or response['payload_sha256'] != digest(response['payload'])):
        raise ValueError('reused dividend reservation/response chain changed')
    at = datetime.fromisoformat(response['payload']['captured_at_utc'])
    if at.tzinfo is None or at < datetime(2026, 10, 20, 7, tzinfo=timezone.utc):
        raise ValueError('dividend response predates unconditional cutoff close')
    data = unwrap_vendor_response(response['payload'])
    validate_dividends20(packet['instrument'], data['fields'], data['rows'])
    return {'instrument': packet['instrument'], 'data': data, 'origin_directory': str(base),
            'receipt': copy.deepcopy(receipt), 'captured_at_utc': at.isoformat(), 'original_request_sha256': expected_old_request_sha}


def _rows(records, fields):
    return [[r[k] for k in fields] for r in records]


def _same_records(a, b):
    return sorted(digest(r) for r in a) == sorted(digest(r) for r in b)


def _preflight(originals, tails, reused, sessions):
    if not originals or len(originals) > 79 or not set(tails) <= set(originals) or not set(reused) <= set(originals):
        raise ValueError('bounded known source identities required')
    if not sessions or sessions != sorted(set(sessions)) or sessions[-1] != OLD_END:
        raise ValueError('ordered original source calendar required')
    for d in sessions:
        canonical_day(d)
    for code, old in originals.items():
        source_code(code)
        if old['instrument'] != code or old['window'] != [START, OLD_END]:
            raise ValueError('original packet identity changed')
        validate_bars20(code, BAR_FIELDS, _rows(old['bars'], BAR_FIELDS))
        if not calendar_diagnostic(old['bars'], sessions)['full_explicit_calendar_covered']:
            raise ValueError('original source calendar prefix incomplete')
        for year in (2024, 2025, 2026):
            rows = [r for r in old['distributions'] if r['dividOperateDate'][:4] == str(year)]
            accepted, excluded = validate_dividends20(code, DIVIDEND_FIELDS, _rows(rows, DIVIDEND_FIELDS), year)
            if accepted != rows or excluded or any(r['dividOperateDate'] > OLD_END for r in rows):
                raise ValueError('original accepted distributions changed')
        if code in tails:
            t = tails[code]
            validate_bars20(code, BAR_FIELDS, _rows(t['bars'], BAR_FIELDS))
            if [r['date'] for r in t['bars']] != ['2026-10-14', '2026-10-15', '2026-10-16']:
                raise ValueError('complete authenticated three-day cache tail required')
            a, q = validate_dividends20(code, DIVIDEND_FIELDS, _rows(t['distributions'], DIVIDEND_FIELDS))
            if q or any(not FIRST <= r['dividOperateDate'] <= TAIL_END for r in a):
                raise ValueError('cached distribution outside tail')
            validate_adjustments20(code, ADJUST_FIELDS, _rows(t['adjustments'], ADJUST_FIELDS))
        if code in reused:
            v = reused[code]
            if v['instrument'] != code:
                raise ValueError('reused dividend issuer changed')
            validate_dividends20(code, v['data']['fields'], v['data']['rows'])


def capture_horizon(out, originals, tails, reused_dividends, old_sessions, fetch, *, request_bytes, maximum_queries):
    out = Path(out)
    budget = 1 + 3 * len(originals) - len(reused_dividends)
    if type(maximum_queries) is not int or maximum_queries != budget or maximum_queries > 214 or out.exists():
        raise ValueError('fixed exact source budget and unused output required')
    _preflight(originals, tails, reused_dividends, old_sessions)
    request_sha = hashlib.sha256(request_bytes).hexdigest()
    (out / 'codes').mkdir(parents=True)
    (out / 'request.json').write_bytes(request_bytes)
    journal = QueryJournal(out, max_queries=budget, max_attempts=1)
    progress, errors, calendar_receipt = {}, {}, None
    codes = sorted(originals)
    sessions = list(old_sessions)
    stopped, abnormal, consecutive = False, False, 0

    def get(code, component, parameters):
        payload, receipt = journal.query({'source': 'BaoStock', 'instrument': code, 'component': component,
            'parameters': parameters, 'low_beta60_horizon_request_sha256': request_sha},
            lambda: fetch(code, component, parameters))
        return unwrap_vendor_response(payload), receipt

    def error(code, exc):
        (out / 'errors').mkdir(exist_ok=True)
        p = out / 'errors' / (code + '.json')
        atomic_json(p, {'instrument': code, 'error_type': type(exc).__name__, 'error': str(exc)})
        errors[code] = file_sha(p)

    try:
        try:
            data, calendar_receipt = get('CN_STOCK_CALENDAR', 'calendar', {'start_date': FIRST, 'end_date': END})
            expected_days = [(date.fromisoformat(FIRST) + timedelta(days=i)).isoformat() for i in range(7)]
            rows = data['rows']
            if (data['fields'] != ['calendar_date', 'is_trading_day']
                    or any(len(r) != 2 or r[1] not in ('0', '1') for r in rows)
                    or [r[0] for r in rows] != expected_days or rows[-1][1] != '1'):
                raise ValueError('complete observed calendar flags through fixed cutoff required')
            added = [r[0] for r in rows if r[1] == '1']
            if tails and [d for d in added if d <= TAIL_END] != ['2026-10-14', '2026-10-15', '2026-10-16']:
                raise ValueError('observed calendar disagrees with cached tail')
            sessions += added
            atomic_json(out / 'calendar.json', {'sessions': sessions, 'new_calendar_rows': rows, 'source_query_receipt': calendar_receipt})
        except Exception as exc:
            error('__calendar__', exc)
        if '__calendar__' not in errors:
            for code in codes:
                try:
                    receipts = {}
                    start = '2026-10-17' if code in tails else FIRST
                    d, receipts['daily'] = get(code, 'daily', {'start_date': start, 'end_date': END, 'frequency': 'd', 'adjustflag': '3'})
                    bars = validate_bars20(code, d['fields'], d['rows'])
                    if [r['date'] for r in bars] != [s for s in added if s >= start]:
                        raise ValueError('new daily rows do not cover observed calendar exactly')
                    if code in reused_dividends:
                        d = reused_dividends[code]['data']
                    else:
                        d, receipts['dividend2026'] = get(code, 'dividend2026', {'year': '2026', 'yearType': 'operate'})
                    distributions, quarantine = validate_dividends20(code, d['fields'], d['rows'])
                    old = originals[code]
                    if not _same_records([r for r in distributions if r['dividOperateDate'] <= OLD_END],
                                         [r for r in old['distributions'] if r['dividOperateDate'].startswith('2026')]):
                        raise ValueError('fresh full-year distribution prefix disagrees with original')
                    tail = tails.get(code, {'bars': [], 'distributions': [], 'adjustments': []})
                    if any(r not in distributions for r in tail['distributions']):
                        raise ValueError('cached dividend missing from full-year response')
                    d, receipts['adjustments'] = get(code, 'adjustments', {'start_date': FIRST, 'end_date': END})
                    adjustments = validate_adjustments20(code, d['fields'], d['rows'])
                    if not _same_records(tail['adjustments'], [r for r in adjustments if r['dividOperateDate'] <= TAIL_END]) and code in tails:
                        raise ValueError('cached adjustment tail changed')
                    promoted, retained = [], []
                    for q in old.get('quarantine', []):
                        at = q['record'].get('dividOperateDate', '')
                        if OLD_END < at <= END:
                            if q['record'] not in distributions:
                                raise ValueError('eligible original quarantine lacks accepted source confirmation')
                            promoted.append(copy.deepcopy(q))
                        else:
                            retained.append(copy.deepcopy(q))
                    for q in quarantine:
                        if q not in retained:
                            retained.append(q)
                    packet = {'instrument': code, 'window': [START, END],
                        'bars': copy.deepcopy(old['bars'] + tail['bars']) + bars,
                        'distributions': copy.deepcopy(old['distributions']) + [r for r in distributions if r['dividOperateDate'] > OLD_END],
                        'adjustments': copy.deepcopy(old['adjustments']) + adjustments,
                        'quarantine': retained, 'promoted_original_quarantine': promoted,
                        'source_query_receipts': receipts, 'original_packet_semantic_sha256': digest(old),
                        'reused_dividend_response': copy.deepcopy(reused_dividends.get(code)),
                        'request_sha256': request_sha}
                    if not calendar_diagnostic(packet['bars'], sessions)['full_explicit_calendar_covered']:
                        raise ValueError('assembled calendar incomplete')
                    path = out / 'codes' / (code + '.json')
                    atomic_json(path, packet)
                    progress[code] = file_sha(path)
                    consecutive = 0
                except Exception as exc:
                    error(code, exc)
                    consecutive += 1
                atomic_json(out / 'progress.json', progress)
                atomic_json(out / 'errors.json', errors)
                print('horizon source', code, 'saved', len(progress), 'errors', len(errors), flush=True)
                if consecutive >= 3:
                    stopped = True
                    break
    except BaseException:
        abnormal = True
        raise
    finally:
        packets = [json.loads((out / 'codes' / (c + '.json')).read_text()) for c in progress]
        manifest = {'status': 'LOW_BETA60_OCT20_SOURCE_CAPTURE_ADMISSION_SEPARATE', 'window': [START, END],
            'requested_names': len(codes), 'names': len(progress), 'per_code_sha256': progress, 'errors_sha256': errors,
            'pending_codes': [c for c in codes if c not in progress and c not in errors],
            'capture_complete': len(progress) == len(codes) and not errors and not abnormal,
            'stopped_after_three_failed_codes': stopped, 'abnormal_termination': abnormal,
            'maximum_source_reservations': budget, 'query_reservations_consumed': len(list(out.rglob('reserved-*.json'))),
            'request_sha256': request_sha, 'calendar_sha256': file_sha(out / 'calendar.json') if (out / 'calendar.json').exists() else None,
            'reused_dividend_codes': sorted(reused_dividends), 'cached_tail_codes': sorted(tails),
            'totals': {k: sum(len(p[k]) for p in packets) for k in ('bars', 'distributions', 'adjustments', 'quarantine', 'promoted_original_quarantine')},
            'portfolio_returns_computed': False, 'admitted_for_account_replay': False, 'historical_observed_arrival_verified': False,
            'full_October_complete': False, 'objective_achieved': False}
        atomic_json(out / 'progress.json', progress)
        atomic_json(out / 'errors.json', errors)
        atomic_json(out / 'manifest.json', manifest)
    return manifest
