"""Bounded raw-source assembly. No source admission, account replay or ROI."""
import copy
import hashlib
import json
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_illiquidity_raw_development import calendar_diagnostic, preserve_response, unwrap_vendor_response
from scripts.capture_low_risk_raw_account_data import (
    BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS, source_code, validate_bars, validate_dividends,
)
from scripts.fundamental_query_journal import QueryJournal
from scripts.inventory_low_beta60_sources import core_fingerprint

START, END, PRE_END = '2023-12-29', '2026-10-13', '2025-12-31'


def assemble_packet(code, source, original, sessions):
    if source['instrument'] != code:
        raise ValueError('raw source security changed')
    result = {'instrument': code, 'window': [START, END]}
    for key, field in (('bars', 'date'), ('distributions', 'dividOperateDate'), ('adjustments', 'dividOperateDate')):
        rows = [r for r in source[key] if START <= r[field] <= END]
        if original is not None:
            if original['instrument'] != code or original['window'] != [START, PRE_END]:
                raise ValueError('original pre2026 identity changed')
            prefix = [r for r in rows if r[field] <= PRE_END]
            if source['window'][0] <= START:
                same = (core_fingerprint({'bars': prefix}) == core_fingerprint(original) if key == 'bars'
                        else prefix == original[key])
                if not same:
                    raise ValueError('cached pre2026 prefix changed: ' + key)
            rows = copy.deepcopy(original[key]) + [r for r in rows if r[field] > PRE_END]
        result[key] = copy.deepcopy(rows)
    result['quarantine'] = copy.deepcopy(original.get('quarantine', []) if original else [])
    result['quarantine'].extend(copy.deepcopy([q for q in source.get('quarantine', [])
        if not q['record'].get('dividOperateDate') or q['record']['dividOperateDate'] > PRE_END]))
    validate_bars(code, BAR_FIELDS, [[r[k] for k in BAR_FIELDS] for r in result['bars']])
    if not calendar_diagnostic(result['bars'], sessions)['full_explicit_calendar_covered']:
        raise ValueError('full explicit source calendar required; no row synthesis')
    for year in (2024, 2025, 2026):
        rows = [r for r in result['distributions'] if r['dividOperateDate'][:4] == str(year)]
        accepted, excluded = validate_dividends(code, DIVIDEND_FIELDS, [[r[k] for k in DIVIDEND_FIELDS] for r in rows], year)
        if accepted != rows or excluded:
            raise ValueError('accepted distribution schema or window changed')
    if any(r['code'] != source_code(code) or not START <= r['dividOperateDate'] <= END for r in result['adjustments']):
        raise ValueError('adjustment outside source security/window')
    return result


def fetch_packet(journal, code, request_sha, fetch, original):
    start = '2026-01-01' if original is not None else START
    receipts = {}

    def get(component, parameters):
        data, receipts[component] = preserve_response(journal,
            {'source': 'BaoStock', 'instrument': code, 'component': component, 'parameters': parameters,
             'low_beta60_extension_request_sha256': request_sha},
            lambda: fetch(code, component, parameters), unwrap_vendor_response)
        return data

    d = get('daily', {'start_date': start, 'end_date': END, 'frequency': 'd', 'adjustflag': '3'})
    bars = validate_bars(code, d['fields'], d['rows'])
    if any(not start <= r['date'] <= END for r in bars):
        raise ValueError('daily response exceeded requested source window')
    distributions, quarantine = [], []
    for year in ((2026,) if original is not None else (2024, 2025, 2026)):
        d = get('dividend' + str(year), {'year': str(year), 'yearType': 'operate'})
        accepted, excluded = validate_dividends(code, d['fields'], d['rows'], year)
        distributions.extend(r for r in accepted if r['dividOperateDate'] <= END)
        quarantine.extend(excluded)
        quarantine.extend({'reason': 'AFTER_EXTENSION_CUTOFF', 'record': r}
                          for r in accepted if r['dividOperateDate'] > END)
    a = get('adjustments', {'start_date': start, 'end_date': END})
    if tuple(a['fields']) != ADJUST_FIELDS or any(len(r) != len(ADJUST_FIELDS) for r in a['rows']):
        raise ValueError('adjustment schema changed')
    adjustments = [dict(zip(a['fields'], row)) for row in a['rows']]
    if any(r['code'] != source_code(code) or not start <= r['dividOperateDate'] <= END for r in adjustments):
        raise ValueError('adjustment response exceeded security/window')
    return {'instrument': code, 'window': [start, END], 'bars': bars, 'distributions': distributions,
            'adjustments': adjustments, 'quarantine': quarantine, 'source_query_receipts': receipts}


def capture_packets(out, codes, sessions, originals, cached, request_sha, fetch, *, request_bytes=None):
    """One foreground attempt. Existing output is preserved and never resumed."""
    out = Path(out)
    if out.exists():
        raise ValueError('preserve existing capture; no automatic retry or resume')
    if codes != sorted(set(codes)) or not set(cached) <= set(codes) or not set(originals) <= set(codes):
        raise ValueError('unique sorted fixed source universe required')
    fresh = [c for c in codes if c not in cached]
    budget = sum(3 if c in originals else 5 for c in fresh)
    if budget > 76:
        raise ValueError('absolute76 source reservation budget exceeded')
    if request_bytes is not None and hashlib.sha256(request_bytes).hexdigest() != request_sha:
        raise ValueError('request byte identity changed')
    # Validate every reusable packet before any output or provider query.
    reused = {c: assemble_packet(c, v, originals.get(c), sessions) for c, v in cached.items()}
    out.mkdir(parents=True)
    (out / 'codes').mkdir()
    if request_bytes is not None:
        (out / 'request.json').write_bytes(request_bytes)
    atomic_json(out / 'calendar.json', {'sessions': sessions})
    progress, errors = {}, {}
    atomic_json(out / 'progress.json', progress)
    atomic_json(out / 'errors.json', errors)
    journal = QueryJournal(out, max_queries=max(1, budget), max_attempts=1)

    def save(code, packet):
        path = out / 'codes' / (code + '.json')
        atomic_json(path, packet)
        progress[code] = sha256_file(path)
        atomic_json(out / 'progress.json', progress)

    for code, packet in reused.items():
        packet['provenance'] = {'kind': 'AUTHENTICATED_FULL_CACHE_WITH_ORIGINAL_PREFIX',
                                'request_sha256': request_sha, 'source_query_receipts': cached[code].get('source_query_receipts')}
        save(code, packet)
    consecutive = 0
    for n, code in enumerate(fresh, 1):
        try:
            source = fetch_packet(journal, code, request_sha, fetch, originals.get(code))
            packet = assemble_packet(code, source, originals.get(code), sessions)
            packet['source_query_receipts'] = source['source_query_receipts']
            packet['provenance'] = {'kind': 'ORIGINAL_PRE2026_PLUS_JOURNALED2026' if code in originals else 'JOURNALED_FULL_WINDOW',
                                    'request_sha256': request_sha, 'query_window': source['window']}
            save(code, packet)
        except Exception as exc:
            (out / 'errors').mkdir(exist_ok=True)
            path = out / 'errors' / (code + '.json')
            atomic_json(path, {'instrument': code, 'error_type': type(exc).__name__, 'error': str(exc),
                               'request_sha256': request_sha, 'source_responses_retained': True})
            errors[code] = sha256_file(path)
            atomic_json(out / 'errors.json', errors)
            consecutive += 1
            print('extension source error', code, type(exc).__name__, flush=True)
        else:
            consecutive = 0
        print('raw extension', n, '/', len(fresh), 'saved', len(progress), 'errors', len(errors), flush=True)
        if consecutive >= 3:
            atomic_json(out / 'stopped.json', {'reason': 'THREE_CONSECUTIVE_FAILED_CODES', 'last_instrument': code})
            break
    packets = [json.loads((out / 'codes' / (c + '.json')).read_text()) for c in progress]
    manifest = {'status': 'LOW_BETA60_RAW_EXTENSION_CAPTURED_ADMISSION_SEPARATE', 'window': [START, END],
        'requested_names': len(codes), 'names': len(progress), 'per_code_sha256': progress, 'errors_sha256': errors,
        'pending_codes': [c for c in codes if c not in progress and c not in errors],
        'request_sha256': request_sha, 'calendar_sha256': sha256_file(out / 'calendar.json'),
        'fresh_codes': fresh, 'reused_codes': sorted(cached), 'original_pre2026_prefix_codes': sorted(originals),
        'maximum_source_reservations': budget, 'query_reservations_consumed': len(list(out.rglob('reserved-*.json'))),
        'totals': {k: sum(len(p[k]) for p in packets) for k in ('bars', 'distributions', 'adjustments', 'quarantine')},
        'admitted_for_account_replay': False, 'historical_arrival_verified': False,
        'portfolio_returns_computed': False, 'objective_achieved': False}
    atomic_json(out / 'manifest.json', manifest)
    return manifest
