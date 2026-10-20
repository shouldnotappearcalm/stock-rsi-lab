"""Stdlib source reconstruction; no project imports, portfolio or network."""
import argparse
import copy
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser()
for name in ('source-root', 'capture-dir', 'output'):
    parser.add_argument('--' + name, required=True)
args = parser.parse_args()
base, capture = Path(args.source_root), Path(args.capture_dir)
repo = Path(__file__).resolve().parents[3]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text())
digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
reqfile = repo / 'experiments/qlib/low-beta60-raw-extension-source-request-v2.json'
assert sha(reqfile) == '2b1f1b7e5b797cf71a0a28880d4ee4e11885825576d1fab6012b6072a4c81c5f'
request = read(reqfile)
for key, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
    assert all(sha(root / f) == h for f, h in request[key].items())
assert (capture / 'request.json').read_bytes() == reqfile.read_bytes()
m = read(capture / 'manifest.json')
assert m['request_sha256'] == sha(reqfile) and m['window'] == ['2023-12-29', '2026-10-13']
assert m['names'] == m['requested_names'] == 79 and not m['errors_sha256'] and not m['pending_codes']
assert m['maximum_source_reservations'] == m['query_reservations_consumed'] == 76
assert m['method_code_sha256'] == request['method_code_sha256'] and m['target_sha256'] == request['target_sha256']
assert sha(capture / 'calendar.json') == m['calendar_sha256']
sessions = read(capture / 'calendar.json')['sessions']
assert sessions == [d for d in read(base / 'low-risk-raw-account-data-20261017/calendar.json')['sessions']
                    if '2023-12-29' <= d <= '2026-10-13']
assert len(sessions) == 671
BAR = ('date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST')
DIV = ('code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate',
       'dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax',
       'dividStocksPs','dividCashStock','dividReserveToStockPs')
ADJ = ('code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor')
query_files = {}
components = {}


def source(code, component, parameters):
    identity = {'source': 'BaoStock', 'instrument': code, 'component': component,
                'parameters': parameters, 'low_beta60_extension_request_sha256': sha(reqfile)}
    key = digest(identity)
    folder = capture / 'queries' / key
    assert read(folder / 'request.json') == identity
    reserved, response = read(folder / 'reserved-1.json'), read(folder / 'response-1.json')
    assert reserved['identity_sha256'] == key and reserved['attempt'] == 1
    assert response['identity_sha256'] == key and response['reservation_sha256'] == sha(folder / 'reserved-1.json')
    assert response['status'] == 'CAPTURED' and digest(response['payload']) == response['payload_sha256']
    payload = response['payload']
    assert payload['fields'] == ['provider_response'] and len(payload['rows']) == 1
    record = payload['rows'][0]
    assert record['initial_error_code'] == record['final_error_code'] == '0' and record['iteration_error_type'] is None
    files = {'request_file': 'queries/' + key + '/request.json',
             'reserved_file': 'queries/' + key + '/reserved-1.json',
             'response_file': 'queries/' + key + '/response-1.json'}
    receipt = {**files, **{n.replace('_file', '_sha256'): sha(capture / f) for n, f in files.items()}}
    query_files[key] = {f.name: sha(f) for f in folder.iterdir()}
    assert set(query_files[key]) == {'request.json', 'reserved-1.json', 'response-1.json'}
    components[code + '/' + component] = receipt
    return record


def number(text):
    value = Decimal(text)
    assert value.is_finite() and value >= 0
    return value


def core(rows):
    return [[r['date'], r['code'], *[str(Decimal(r[f]).normalize()) if r[f] else ''
             for f in ('open', 'high', 'low', 'close', 'preclose', 'volume', 'amount')], r['tradestatus'], r['isST']] for r in rows]


expected = {}
old_sources = {}
for code in request['codes']:
    original = None
    if code in request['original_packet_sha256']:
        p = base / 'low-beta60-raw-dev-20261021/codes' / (code + '.json')
        assert sha(p) == request['original_packet_sha256'][code]
        original = read(p)
        old_sources[code] = original
    if code in request['reuse_routes']:
        route = request['reuse_routes'][code]
        p = base / route['source_directory'] / 'codes' / (code + '.json')
        assert sha(p) == route['packet_sha256']
        packet = read(p)
    else:
        start = '2026-01-01' if original else '2023-12-29'
        data = source(code, 'daily', {'start_date': start, 'end_date': '2026-10-13', 'frequency': 'd', 'adjustflag': '3'})
        assert data['fields'] == list(BAR) and all(len(r) == len(BAR) for r in data['rows'])
        bars = [dict(zip(BAR, row)) for row in data['rows']]
        assert all(start <= r['date'] <= '2026-10-13' for r in bars)
        distributions, quarantine = [], []
        for year in ((2026,) if original else (2024, 2025, 2026)):
            data = source(code, 'dividend' + str(year), {'year': str(year), 'yearType': 'operate'})
            assert data['fields'] == list(DIV) and all(len(r) == len(DIV) for r in data['rows'])
            for raw in data['rows']:
                row = dict(zip(DIV, raw))
                assert row['code'] == code[:2].lower() + '.' + code[2:]
                at = row['dividOperateDate']
                if not at:
                    quarantine.append({'reason': 'MISSING_OPERATE_DATE', 'record': row})
                    continue
                assert date.fromisoformat(at).isoformat() == at and at[:4] == str(year)
                if at > '2026-10-16':
                    quarantine.append({'reason': 'AFTER_CAPTURE_CUTOFF', 'record': row})
                elif at > '2026-10-13':
                    quarantine.append({'reason': 'AFTER_EXTENSION_CUTOFF', 'record': row})
                else:
                    distributions.append(row)
        data = source(code, 'adjustments', {'start_date': start, 'end_date': '2026-10-13'})
        assert data['fields'] == list(ADJ) and all(len(r) == len(ADJ) for r in data['rows'])
        adjustments = [dict(zip(ADJ, row)) for row in data['rows']]
        assert all(start <= r['dividOperateDate'] <= '2026-10-13' for r in adjustments)
        packet = {'instrument': code, 'window': [start, '2026-10-13'], 'bars': bars,
                  'distributions': distributions, 'quarantine': quarantine, 'adjustments': adjustments}
    item = {'instrument': code, 'window': ['2023-12-29', '2026-10-13']}
    for field, clock in (('bars', 'date'), ('distributions', 'dividOperateDate'), ('adjustments', 'dividOperateDate')):
        rows = [r for r in packet[field] if '2023-12-29' <= r[clock] <= '2026-10-13']
        if original:
            prefix = [r for r in rows if r[clock] <= '2025-12-31']
            if packet['window'][0] <= '2023-12-29':
                assert (core(prefix) == core(original['bars']) if field == 'bars' else prefix == original[field])
            rows = copy.deepcopy(original[field]) + [r for r in rows if r[clock] > '2025-12-31']
        item[field] = rows
    item['quarantine'] = copy.deepcopy(original.get('quarantine', []) if original else [])
    item['quarantine'] += [q for q in packet.get('quarantine', []) if not q['record'].get('dividOperateDate')
                           or q['record']['dividOperateDate'] > '2025-12-31']
    expected[code] = item


def verify(packets):
    assert set(packets) == set(expected)
    for code, item in expected.items():
        assert all(packets[code][k] == v for k, v in item.items())
        assert [r['date'] for r in item['bars']] == sessions
        for row in item['bars']:
            assert set(row) == set(BAR) and row['code'] == code[:2].lower() + '.' + code[2:]
            assert row['adjustflag'] == '3' and row['tradestatus'] in ('0', '1') and row['isST'] in ('0', '1')
            for key in ('open', 'high', 'low', 'close', 'preclose', 'volume', 'amount'):
                if row[key]:
                    number(row[key])
            if row['tradestatus'] == '1':
                assert all(row[k] and number(row[k]) > 0 for k in ('open','high','low','close','preclose','volume'))
                assert number(row['high']) >= max(number(row['open']), number(row['close']))
                assert number(row['low']) <= min(number(row['open']), number(row['close']))
        for row in item['distributions']:
            assert set(row) == set(DIV) and row['code'] == code[:2].lower() + '.' + code[2:]
            for key in ('dividCashPsBeforeTax', 'dividStocksPs', 'dividReserveToStockPs'):
                if row[key]:
                    number(row[key])
        for row in item['adjustments']:
            assert set(row) == set(ADJ) and row['code'] == code[:2].lower() + '.' + code[2:]
            assert all(number(row[k]) > 0 for k in ADJ[2:])


actual = {}
for code, expected_sha in m['per_code_sha256'].items():
    p = capture / 'codes' / (code + '.json')
    assert sha(p) == expected_sha
    actual[code] = read(p)
verify(actual)
for code in request['fresh_codes']:
    receipts = {k.split('/')[1]: v for k, v in components.items() if k.startswith(code + '/')}
    assert actual[code]['source_query_receipts'] == receipts
assert len(query_files) == len(list((capture / 'queries').iterdir())) == 76
assert len(list(capture.rglob('reserved-*.json'))) == 76 and not (capture / 'stopped.json').exists()
assert read(capture / 'login-reserved-1.json') == {'attempt': 1, 'request_sha256': sha(reqfile)}
assert read(capture / 'login-response-1.json')['error_code'] == '0'
assert read(capture / 'logout-response.json')['error_code'] == '0'
negative = {}
for label in ('changed_original_pre2026_price', 'missing2026_bar', 'changed_distribution'):
    altered = copy.deepcopy(actual)
    if label == 'changed_original_pre2026_price':
        altered[next(iter(old_sources))]['bars'][0]['close'] = '99999'
    elif label == 'missing2026_bar':
        altered[request['codes'][0]]['bars'].pop()
    else:
        c = next(c for c, p in altered.items() if p['distributions'])
        altered[c]['distributions'][0]['dividCashPsBeforeTax'] = '99999'
    try:
        verify(altered)
    except AssertionError:
        negative[label] = True
    else:
        raise AssertionError('semantic tamper accepted: ' + label)
noncash = [{'instrument': c, **r} for c, p in actual.items() for r in p['distributions']
           if r['dividOperateDate'] > '2025-12-31' and any(r[k] and Decimal(r[k]) > 0 for k in ('dividStocksPs', 'dividReserveToStockPs'))]
totals = {k: sum(len(p[k]) for p in actual.values()) for k in ('bars','distributions','adjustments','quarantine')}
assert totals == m['totals'] and totals['bars'] == 79 * 671
for flag in ('admitted_for_account_replay', 'historical_arrival_verified', 'portfolio_returns_computed', 'objective_achieved'):
    assert m[flag] is False
result = {'status': 'INDEPENDENT79_RAW_PACKET_LINEAGE_AND_69_ORIGINAL_PREFIXES_RECONSTRUCTED',
    'audit_code_sha256': sha(__file__), 'request_sha256': sha(reqfile), 'manifest_sha256': sha(capture / 'manifest.json'),
    'names_reconstructed': 79, 'source_sessions': 671, 'all69_original_row_prefixes_identical': True,
    'cached_routes_reconstructed': 55, 'fresh_codes_reconstructed': 24, 'query_reservations_reconstructed': 76,
    'all_requested_parameters_and_source_receipts_reconstructed': True, 'query_journal_files_sha256': query_files,
    'totals': totals, 'vendor2026_distribution_rows': sum(r['dividOperateDate'] > '2025-12-31' for p in actual.values() for r in p['distributions']),
    'noncash2026_events_requiring_primary_review': noncash,
    'semantic_negative_controls_rejected': negative, 'negative_controls_use_hash_gate': False,
    'imports_project_code': False, 'network_queries': 0, 'source_files_modified': False,
    'admitted_for_account_replay': False, 'historical_arrival_verified': False,
    'full_corporate_actions_certified': False, 'portfolio_returns_computed': False, 'objective_achieved': False}
with Path(args.output).open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print('Independent79 raw sources/69 original prefixes/76 queries reconstructed; three semantic negatives rejected; no ROI')
