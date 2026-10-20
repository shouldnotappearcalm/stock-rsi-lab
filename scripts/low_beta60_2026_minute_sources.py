"""2026-only source extension; old1332packets and investment code are untouched."""
import hashlib
import json
import re
import time
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.fundamental_query_journal import QueryJournal, digest, file_sha, write_packet_once
from scripts.tdx_history_checks import inspect_minutes
from stock_rsi.intraday_tape import aggregate_minutes

END = '2026-10-13'


def valid_pair(code, day):
    try:
        valid = (isinstance(code, str) and re.fullmatch('(SH|SZ)[0-9]{6}', code)
                 and isinstance(day, str) and date.fromisoformat(day).isoformat() == day
                 and '2026-01-01' <= day <= END)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('canonical2026 minute identity within explicit October13cap required')


def query_packet(journal, code, day, host, fetch):
    valid_pair(code, day)
    if journal.max_attempts != 1:
        raise ValueError('one reserved attempt per minute identity required')
    identity = {'method': 'minutes.history', 'instrument': code, 'requested_day': day, 'host': host, 'include_raw': True}
    folder = journal.root / 'queries' / digest(identity)
    try:
        payload, receipt = journal.query(identity, lambda: (['response'], [fetch()]))
    except ValueError as exc:
        if str(exc) != 'source query attempts exhausted: ' + digest(identity):
            raise
        response = json.loads((folder / 'response-1.json').read_text())
        if response['status'] != 'SOURCE_ERROR':
            raise ValueError('source failure outcome not preserved')
        packet = {'instrument': code, 'requested_day': day, 'status': 'REQUEST_FAILED',
                  'error_type': response['error_type'], 'error': response['error'],
                  'query_response_sha256': file_sha(folder / 'response-1.json'),
                  'query_reservation_sha256': file_sha(folder / 'reserved-1.json')}
        verify_receipt(journal.root, code, day, packet, host)
        return packet
    if payload['fields'] != ['response'] or len(payload['rows']) != 1:
        raise ValueError('minute response envelope changed')
    return {'instrument': code, 'requested_day': day, 'status': 'RESPONSE_CAPTURED',
            'response': payload['rows'][0], 'observed_at': payload['captured_at_utc'],
            'query_response_sha256': receipt['response_sha256'], 'query_reservation_sha256': receipt['reserved_sha256']}


def verify_receipt(root, code, day, packet, host):
    valid_pair(code, day)
    identity = {'method': 'minutes.history', 'instrument': code, 'requested_day': day, 'host': host, 'include_raw': True}
    key = digest(identity)
    folder = Path(root) / 'queries' / key
    request = json.loads((folder / 'request.json').read_text())
    reserved = json.loads((folder / 'reserved-1.json').read_text())
    response = json.loads((folder / 'response-1.json').read_text())
    if (request != identity or reserved['identity_sha256'] != key or reserved['attempt'] != 1
            or response['identity_sha256'] != key or response['reservation_sha256'] != file_sha(folder / 'reserved-1.json')
            or packet['instrument'] != code or packet['requested_day'] != day
            or packet['query_reservation_sha256'] != file_sha(folder / 'reserved-1.json')
            or packet['query_response_sha256'] != file_sha(folder / 'response-1.json')):
        raise ValueError('source identity or immutable receipt changed')
    if response['status'] == 'CAPTURED':
        p = response['payload']
        if (packet['status'] != 'RESPONSE_CAPTURED' or digest(p) != response['payload_sha256']
                or p['fields'] != ['response'] or p['rows'] != [packet['response']]
                or packet['observed_at'] != p['captured_at_utc']):
            raise ValueError('source payload differs from preserved response')
    elif response['status'] == 'SOURCE_ERROR':
        if packet['status'] != 'REQUEST_FAILED' or packet['error_type'] != response['error_type'] or packet['error'] != response['error']:
            raise ValueError('source error differs from preserved response')
    else:
        raise ValueError('unknown source response status')


def inspect_packet(code, day, packet, daily):
    valid_pair(code, day)
    if (packet['instrument'] != code or packet['requested_day'] != day or daily['date'] != day
            or daily['tradestatus'] != '1' or daily['isST'] != '0'):
        raise ValueError('ordinary active source security/date mismatch')
    record = packet.get('methods', {}).get('minutes.history', packet)
    if record['status'] != 'RESPONSE_CAPTURED':
        raise ValueError('minute source unavailable')
    facts = inspect_minutes(code, day, record['response'], daily)
    if not facts['last_close_matches'] or facts['traded_points_outside_daily_range']:
        raise ValueError('minute/raw daily price signature mismatch')
    windows = aggregate_minutes(code, date.fromisoformat(day), record['response']['points'])
    lower, volume = sum(w['volume_lower_shares'] for w in windows), Decimal(daily['volume'])
    if not volume.is_finite() or volume <= 0 or volume != int(volume) or lower > volume:
        raise ValueError('minute lower volume exceeds valid daily source')
    return {'status': 'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE', 'windows': len(windows),
            'facts': facts, 'stressed_volume_lower_shares': lower}


def capture_extension(base, out, reused, fresh, plan, fetch, *, plan_bytes=None):
    base, out = Path(base), Path(out)
    if out.exists():
        raise ValueError('preserve existing source attempt; no automatic resume')
    budget = plan['max_fresh_query_reservations']
    if (type(budget) is not int or not 1 <= budget <= 247 or len(fresh) != budget
            or plan['max_attempts_per_request'] != 1 or plan['stop_after_consecutive_source_failures'] != 3
            or type(plan['inter_query_delay_seconds']) not in (int, float)
            or not 0 <= plan['inter_query_delay_seconds'] <= 1):
        raise ValueError('absolute247 one-attempt source budget and bounded stop required')
    if plan_bytes is not None and json.loads(plan_bytes) != plan:
        raise ValueError('frozen configuration bytes differ')
    names = []
    for code, day in fresh:
        valid_pair(code, day)
        names.append(code + '-' + day + '.json')
    if len(names) != len(set(names)) or set(names) & set(reused):
        raise ValueError('unique disjoint minute source identities required')
    contents = {}
    for name, origin in reused.items():
        if Path(name).name != name or not name.endswith('.json') or Path(origin['root']).name != origin['root']:
            raise ValueError('safe minute source paths required')
        code, day = name[:-5].split('-', 1)
        valid_pair(code, day)
        path = base / origin['root'] / 'sessions' / name
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != origin['sha256']:
            raise ValueError('reused source bytes changed')
        p = json.loads(data)
        record = p.get('methods', {}).get('minutes.history', p)
        if p['instrument'] != code or p['requested_day'] != day or record['status'] != 'RESPONSE_CAPTURED':
            raise ValueError('reused source identity/status changed')
        contents[name] = data
    out.mkdir(parents=True)
    (out / 'sessions').mkdir()
    if plan_bytes is None:
        write_packet_once(out / 'plan.json', plan)
    else:
        (out / 'plan.json').write_bytes(plan_bytes)
    write_packet_once(out / 'capture_request.json', {'reused': reused, 'fresh': fresh})
    journal = QueryJournal(out, max_queries=budget, max_attempts=1)
    hashes, consecutive, stop, abnormal = {}, 0, False, None
    try:
        for name, data in contents.items():
            (out / 'sessions' / name).write_bytes(data)
            hashes[name] = file_sha(out / 'sessions' / name)
        for n, (code, day) in enumerate(fresh, 1):
            packet = query_packet(journal, code, day, plan['host'], lambda: fetch(code, day))
            path = out / 'sessions' / (code + '-' + day + '.json')
            write_packet_once(path, packet)
            hashes[path.name] = file_sha(path)
            consecutive = consecutive + 1 if packet['status'] == 'REQUEST_FAILED' else 0
            if n % 25 == 0 or n == len(fresh):
                print('2026minutes', n, '/', len(fresh), packet['status'], flush=True)
            if consecutive >= 3:
                stop = True
                break
            if plan['inter_query_delay_seconds']:
                time.sleep(plan['inter_query_delay_seconds'])
    except BaseException as exc:
        abnormal = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        statuses = Counter()
        for name in hashes:
            p = json.loads((out / 'sessions' / name).read_text())
            statuses[p.get('methods', {}).get('minutes.history', p)['status']] += 1
        m = {'status': 'LOW_BETA60_2026_MINUTE_EXTENSION_CAPTURE_RECORDED',
            'plan_sha256': file_sha(out / 'plan.json'), 'capture_request_sha256': file_sha(out / 'capture_request.json'),
            'requested': len(reused) + len(fresh), 'captured': len(hashes), 'per_session_sha256': dict(sorted(hashes.items())),
            'reused_session_provenance': reused, 'fresh_query_reservations': len(list(out.rglob('reserved-*.json'))),
            'fresh_query_responses_preserved': len(list(out.rglob('response-*.json'))), 'response_status_counts': dict(statuses),
            'pending_fresh_requests': [[c, d] for c, d in fresh if c + '-' + d + '.json' not in hashes],
            'stopped_after_consecutive_source_failures': stop, 'abnormal_exit': abnormal,
            'complete_capture': len(hashes) == len(reused) + len(fresh),
            'admitted_for_reconstructed_execution': False, 'historical_arrival_verified': False,
            'portfolio_returns_computed': False, 'objective_achieved': False}
        write_packet_once(out / ('capture-snapshot-' + digest(m) + '.json'), m)
        write_packet_once(out / 'manifest.json', m)
    return m
