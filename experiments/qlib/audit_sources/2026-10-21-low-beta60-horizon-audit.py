"""Read-only stdlib reconstruction from raw journals, independent of capture code."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_bytes())
canonical = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
same = lambda a, b: sorted(map(canonical, a)) == sorted(map(canonical, b))


def verify_assembly(packet, old, tail, daily, annual, excluded, adjustments, sessions):
    assert packet['instrument'] == old['instrument']
    assert packet['window'] == ['2023-12-29', '2026-10-20']
    assert packet['bars'] == old['bars'] + tail['bars'] + daily
    assert [r['date'] for r in packet['bars']] == sessions
    assert same([r for r in annual if r['dividOperateDate'] <= '2026-10-13'],
                [r for r in old['distributions'] if r['dividOperateDate'].startswith('2026')])
    assert all(r in annual for r in tail['distributions'])
    assert packet['distributions'] == old['distributions'] + [r for r in annual if r['dividOperateDate'] > '2026-10-13']
    assert packet['adjustments'] == old['adjustments'] + adjustments
    promoted, retained = [], []
    for q in old['quarantine']:
        at = q['record'].get('dividOperateDate', '')
        if '2026-10-13' < at <= '2026-10-20':
            assert q['record'] in annual
            promoted.append(q)
        else:
            retained.append(q)
    for q in excluded:
        if q not in retained: retained.append(q)
    assert packet['quarantine'] == retained
    assert packet['promoted_original_quarantine'] == promoted


def response(root, receipt, identity):
    files = {}
    for kind in ('request', 'reserved', 'response'):
        name = receipt[kind + '_file']; p = (root / name).resolve()
        assert not Path(name).is_absolute() and p.is_relative_to(root.resolve())
        assert sha(p) == receipt[kind + '_sha256']
        files[kind] = p
    key = canonical(identity)
    assert files['request'] == root.resolve() / 'queries' / key / 'request.json'
    assert files['reserved'] == files['request'].parent / 'reserved-1.json'
    assert files['response'] == files['request'].parent / 'response-1.json'
    assert read(files['request']) == identity
    r, data = read(files['reserved']), read(files['response'])
    assert r['identity_sha256'] == key and r['attempt'] == 1
    assert data['identity_sha256'] == key and data['status'] == 'CAPTURED'
    assert data['reservation_sha256'] == sha(files['reserved'])
    assert data['payload_sha256'] == canonical(data['payload'])
    p = data['payload']; at = datetime.fromisoformat(p['captured_at_utc'])
    assert at.tzinfo is not None and at >= datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    assert p['fields'] == ['provider_response'] and len(p['rows']) == 1
    wire = p['rows'][0]
    assert wire['initial_error_code'] == wire['final_error_code'] == '0'
    assert wire['iteration_error_type'] is None and wire['iteration_error'] is None
    assert all(len(row) == len(wire['fields']) for row in wire['rows'])
    return [dict(zip(wire['fields'], row)) for row in wire['rows']]


def audit(base, repo, out, plan_path, expected_plan_sha):
    assert sha(plan_path) == expected_plan_sha and sha(out / 'request.json') == expected_plan_sha
    plan = read(plan_path)
    for key, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
        for name, expected in plan[key].items(): assert sha(root / name) == expected
    manifest = read(out / 'manifest.json')
    assert manifest['capture_complete'] is True and manifest['names'] == manifest['requested_names'] == 79
    assert not manifest['errors_sha256'] and not manifest['pending_codes'] and not manifest['abnormal_termination']
    assert not manifest['portfolio_returns_computed'] and not manifest['admitted_for_account_replay']
    assert manifest['query_reservations_consumed'] == manifest['maximum_source_reservations'] == 214
    assert len(list((out / 'queries').glob('*/reserved-*.json'))) == 214
    assert len(list((out / 'queries').glob('*/response-*.json'))) == 214
    assert not list(out.rglob('reserved-2.json'))
    assert len(list(out.glob('login-reserved-*.json'))) == 1
    for name, expected in manifest['administrative_receipts_sha256'].items(): assert sha(out / name) == expected
    assert read(out / 'login-response-1.json')['error_code'] == '0'
    assert read(out / 'logout-response.json')['error_code'] == '0'
    assert sha(out / 'calendar.json') == manifest['calendar_sha256']
    cal = read(out / 'calendar.json'); oldroot = base / 'low-beta60-raw-extension-20261021'
    oldcal = read(oldroot / 'calendar.json')['sessions']
    def new_response(code, component, parameters, receipt):
        return response(out, receipt, {'source': 'BaoStock', 'instrument': code, 'component': component,
            'parameters': parameters, 'low_beta60_horizon_request_sha256': expected_plan_sha})
    calendar_rows = new_response('CN_STOCK_CALENDAR', 'calendar', {'start_date': '2026-10-14', 'end_date': '2026-10-20'}, cal['source_query_receipt'])
    assert [r['calendar_date'] for r in calendar_rows] == [f'2026-10-{i}' for i in range(14, 21)]
    assert all(r['is_trading_day'] in ('0', '1') for r in calendar_rows)
    added = [r['calendar_date'] for r in calendar_rows if r['is_trading_day'] == '1']
    assert added[-1] == '2026-10-20' and cal['sessions'] == oldcal + added
    assert cal['new_calendar_rows'] == [[r['calendar_date'], r['is_trading_day']] for r in calendar_rows]
    old_request_sha = sha(repo / 'experiments/qlib/low-beta60-raw-extension-source-request-v2.json')
    totals = dict.fromkeys(('bars', 'distributions', 'adjustments', 'quarantine', 'promoted_original_quarantine'), 0)
    new_dividends, used = [], [cal['source_query_receipt']['request_file']]
    for code in plan['codes']:
        f = out / 'codes' / (code + '.json'); assert sha(f) == manifest['per_code_sha256'][code]
        p = read(f); oldfile = oldroot / 'codes' / (code + '.json')
        assert sha(oldfile) == plan['original_packet_sha256'][code]
        old = read(oldfile); assert p['original_packet_semantic_sha256'] == canonical(old) and p['request_sha256'] == expected_plan_sha
        tail = {'bars': [], 'distributions': [], 'adjustments': []}
        route = plan['reuse_tail_routes'].get(code)
        if route:
            cf = base / route['source_directory'] / 'codes' / (code + '.json')
            assert sha(cf) == route['packet_sha256']; cached = read(cf)
            tail = {k: [r for r in cached[k] if r[field] > '2026-10-13'] for k, field in
                (('bars', 'date'), ('distributions', 'dividOperateDate'), ('adjustments', 'dividOperateDate'))}
        receipts = p['source_query_receipts']; start = '2026-10-17' if route else '2026-10-14'
        daily = new_response(code, 'daily', {'start_date': start, 'end_date': '2026-10-20', 'frequency': 'd', 'adjustflag': '3'}, receipts['daily'])
        assert [r['date'] for r in daily] == [d for d in added if d >= start]
        assert all(r['code'] == code[:2].lower() + '.' + code[2:] and r['adjustflag'] == '3' for r in daily)
        if code in plan['reuse_dividend_codes']:
            rec = old['source_query_receipts']['dividend2026']
            annual = response(oldroot, rec, {'source': 'BaoStock', 'instrument': code, 'component': 'dividend2026',
                'parameters': {'year': '2026', 'yearType': 'operate'}, 'low_beta60_extension_request_sha256': old_request_sha})
            assert p['reused_dividend_response']['receipt'] == rec and 'dividend2026' not in receipts
        else:
            annual = new_response(code, 'dividend2026', {'year': '2026', 'yearType': 'operate'}, receipts['dividend2026'])
            assert p['reused_dividend_response'] is None
        accepted, excluded = [], []
        for r in annual:
            assert r['code'] == code[:2].lower() + '.' + code[2:]
            at = r['dividOperateDate']
            if not at: excluded.append({'reason': 'MISSING_OPERATE_DATE', 'record': r})
            elif at > '2026-10-20': excluded.append({'reason': 'AFTER_CAPTURE_CUTOFF', 'record': r})
            elif at < '2023-12-29': excluded.append({'reason': 'BEFORE_CAPTURE_WINDOW', 'record': r})
            else:
                assert at.startswith('2026-'); accepted.append(r)
        adjustments = new_response(code, 'adjustments', {'start_date': '2026-10-14', 'end_date': '2026-10-20'}, receipts['adjustments'])
        assert all(r['code'] == code[:2].lower() + '.' + code[2:] and '2026-10-14' <= r['dividOperateDate'] <= '2026-10-20' for r in adjustments)
        if route: assert same(tail['adjustments'], [r for r in adjustments if r['dividOperateDate'] <= '2026-10-16'])
        verify_assembly(p, old, tail, daily, accepted, excluded, adjustments, cal['sessions'])
        new_dividends += [{'instrument': code, 'record': r} for r in accepted if r['dividOperateDate'] > '2026-10-13']
        for k in totals: totals[k] += len(p[k])
        used += [r['request_file'] for r in receipts.values()]
    assert totals == manifest['totals'] and len(used) == len(set(used)) == 214
    assert set(used) == {str(p.relative_to(out)) for p in (out / 'queries').glob('*/request.json')}
    return {'status': 'INDEPENDENTLY_RECONSTRUCTED_FIXED_OCT20_RAW_SOURCES_NO_ROI',
        'audit_code_sha256': sha(__file__), 'request_sha256': expected_plan_sha, 'manifest_sha256': sha(out / 'manifest.json'),
        'verified_names': 79, 'original_sessions_per_name': len(oldcal), 'extended_sessions_per_name': len(cal['sessions']),
        'observed_new_trading_sessions': added, 'appended_daily_bars': 79 * len(added), 'cached_tail_bars': 55 * 3,
        'fresh_daily_response_bars': 79 * len(added) - 55 * 3,
        'new_logical_queries': 214, 'reused_full_year_dividend_responses': 24, 'totals': totals,
        'new_post_Oct13_dividends': new_dividends, 'all_old_prefixes_unchanged': True,
        'portfolio_returns_computed': False, 'admitted_for_account_replay': False,
        'historical_arrival_verified': False, 'full_October_complete': False, 'objective_achieved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'repo-root', 'capture-dir', 'request', 'expected-request-sha256', 'output'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args()
    result = audit(Path(a.source_root), Path(a.repo_root), Path(a.capture_dir), Path(a.request), a.expected_request_sha256)
    with Path(a.output).open('x') as stream: json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print('independent source reconstruction', result['verified_names'], 'names', result['new_logical_queries'], 'queries')
