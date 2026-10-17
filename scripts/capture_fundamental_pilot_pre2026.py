"""Bounded data-only valuation/financial pilot; no returns or stock selection.

Historical pubDate is a vendor claim, not proof of unmodified financial vintages.
All raw responses remain separate from schema-valid and quarantined views.
"""
import argparse
import calendar
import fcntl
import json
import socket
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.fundamental_query_journal import QueryJournal, write_packet_once
from scripts.audit_cninfo_report_admission import fixed_sample
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_low_risk_raw_account_data import source_code, query_rows

START, END = '2023-12-29', '2025-12-31'
QUARTERS = ((2023, 3), (2023, 4), *((2024, q) for q in range(1, 5)), *((2025, q) for q in range(1, 4)))
DAILY_FIELDS = ('date', 'code', 'close', 'volume', 'amount', 'turn', 'peTTM', 'pbMRQ',
                'psTTM', 'pcfNcfTTM', 'tradestatus', 'isST', 'adjustflag')
PROFIT_FIELDS = ('code', 'pubDate', 'statDate', 'roeAvg', 'npMargin', 'gpMargin', 'netProfit',
                 'epsTTM', 'MBRevenue', 'totalShare', 'liqaShare')
METHOD_FILES = ('scripts/capture_fundamental_pilot_pre2026.py', 'scripts/audit_cninfo_report_admission.py',
                'scripts/capture_cninfo_csi500_reports_pre2026.py', 'scripts/capture_low_risk_raw_account_data.py',
                'scripts/fundamental_query_journal.py')


def finite(value):
    result = Decimal(value)
    if not result.is_finite(): raise ValueError('finite source numeric required')
    return result


def exact_day(value):
    if date.fromisoformat(value).isoformat() != value: raise ValueError('canonical date required')
    return value


def validate_daily(instrument, fields, rows, expected_days):
    if tuple(fields) != DAILY_FIELDS: raise ValueError('daily valuation schema changed')
    result = []
    for values in rows:
        if len(values) != len(fields): raise ValueError('daily row length changed')
        r = dict(zip(fields, values))
        if (r['code'] != source_code(instrument) or not START <= exact_day(r['date']) <= END
                or r['adjustflag'] != '3' or r['tradestatus'] not in ('0', '1') or r['isST'] not in ('0', '1')):
            raise ValueError('wrong daily identity, date, adjustment or status')
        for key in ('close', 'volume', 'amount', 'turn', 'peTTM', 'pbMRQ', 'psTTM', 'pcfNcfTTM'):
            if r[key]:
                v = finite(r[key])
                if key in ('close', 'volume', 'amount', 'turn') and v < 0: raise ValueError('negative market quantity')
        if r['tradestatus'] == '1' and (not r['close'] or finite(r['close']) <= 0
                                      or not r['volume'] or finite(r['volume']) <= 0):
            raise ValueError('active day lacks positive close or volume')
        result.append(r)
    if [r['date'] for r in result] != list(expected_days): raise ValueError('incomplete or duplicate explicit sessions')
    return result


def validate_profit(instrument, year, quarter, fields, rows):
    if (year, quarter) not in QUARTERS: raise ValueError('financial query outside fixed pre2026 pilot')
    if tuple(fields) != PROFIT_FIELDS: raise ValueError('quarterly profit schema changed')
    month = quarter*3
    period = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    valid, quarantine, seen = [], [], set()
    for values in rows:
        if len(values) != len(fields): raise ValueError('profit row length changed')
        r = dict(zip(fields, values))
        if r['code'] != source_code(instrument) or r['statDate'] != period:
            raise ValueError('wrong quarterly identity or fiscal period')
        for key in PROFIT_FIELDS[3:]:
            if r[key]: finite(r[key])
        key = (r['code'], r['pubDate'], r['statDate'])
        if key in seen: raise ValueError('ambiguous duplicate financial vintage identity')
        seen.add(key)
        reason = None
        if not r['pubDate']: reason = 'MISSING_PUBLICATION_DATE'
        elif exact_day(r['pubDate']) > END: reason = 'PUBLICATION_AFTER_DEVELOPMENT_CUTOFF'
        elif r['pubDate'] < period: reason = 'PUBLICATION_BEFORE_PERIOD_END'
        if reason: quarantine.append({'reason': reason, 'record': r})
        else: valid.append(r)
    return valid, quarantine


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('request', 'expected-request-sha256', 'csi500-instruments', 'calendar-file', 'report-dir', 'output-dir'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv); request_file = Path(args.request); root = Path(__file__).resolve().parents[1]
    if sha256_file(request_file) != args.expected_request_sha256: raise ValueError('capture request changed')
    req = json.loads(request_file.read_text())
    if (req['window'] != [START, END] or req['quarters'] != [list(q) for q in QUARTERS]
            or req['max_query_attempt_reservations'] != 240 or req['per_query_max_attempts'] != 2
            or set(req['method_sha256']) != set(METHOD_FILES)
            or any(sha256_file(root/n) != h for n, h in req['method_sha256'].items())):
        raise ValueError('capture method or boundary changed')
    sample_file = root/'experiments/qlib/cninfo-report-admission-2026-10-16.json'
    if sha256_file(sample_file) != req['original_sample_manifest_sha256']: raise ValueError('original sample changed')
    if (sha256_file(args.csi500_instruments) != req['membership_sha256']
            or sha256_file(args.calendar_file) != req['calendar_sha256']): raise ValueError('source membership/calendar changed')
    codes = fixed_sample(Path(args.csi500_instruments).read_text())
    if codes != req['codes'] or codes != json.loads(sample_file.read_text())['fixed_sample']:
        raise ValueError('fixed sample changed')
    reports = Path(args.report_dir)
    if sha256_file(reports/'manifest.json') != req['cninfo_manifest_sha256']: raise ValueError('source report metadata changed')
    cm = json.loads((reports/'manifest.json').read_text())
    for code in codes:
        if sha256_file(reports/'codes'/(code+'.json')) != cm['per_code_sha256'][code]: raise ValueError('original report packet changed')
    days = [d for d in Path(args.calendar_file).read_text().splitlines() if START <= d <= END]
    if not days or days[0] != START or days[-1] != END: raise ValueError('complete explicit window required')
    out = Path(args.output_dir)
    if args.resume:
        if (out/'request.json').read_bytes() != request_file.read_bytes(): raise ValueError('resume request changed')
    else:
        if out.exists(): raise ValueError('capture output already exists')
        (out/'codes').mkdir(parents=True); (out/'request.json').write_bytes(request_file.read_bytes())
        atomic_json(out/'progress.json', {})
    with (out/'capture.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return capture_sources(out, codes, days, req, args.expected_request_sha256)


def capture_sources(out, codes, days, req, request_sha256):
    progress = json.loads((out/'progress.json').read_text())
    for code, h in progress.items():
        if code not in codes or sha256_file(out/'codes'/(code+'.json')) != h:
            raise ValueError('checkpoint source changed')
        packet = json.loads((out/'codes'/(code+'.json')).read_text())
        for receipt in packet['source_query_receipts']:
            for key in ('request', 'reserved', 'response'):
                relative = Path(receipt[key+'_file'])
                if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'queries':
                    raise ValueError('checkpoint journal path invalid')
                if sha256_file(out/relative) != receipt[key+'_sha256']:
                    raise ValueError('checkpoint query source changed')
    # No source request may precede detection of an unregistered existing packet.
    for code in codes:
        if code not in progress and (out/'codes'/(code+'.json')).exists():
            raise ValueError('unregistered existing source packet; preserve and independently recover before network: '+code)
    fresh = [c for c in codes if c not in progress]
    journal = QueryJournal(out, max_queries=req['max_query_attempt_reservations'],
                           max_attempts=req['per_query_max_attempts'])
    if fresh:
        import baostock as bs
        socket.setdefaulttimeout(20)
        login = bs.login()
        if login.error_code != '0': raise RuntimeError('public source login failed: '+login.error_msg)
        try:
            for code in fresh:
                identity = {'method': 'query_history_k_data_plus', 'code': source_code(code),
                            'fields': list(DAILY_FIELDS), 'start': START, 'end': END, 'adjustflag': '3', 'frequency': 'd'}
                raw, receipt = journal.query(identity, lambda: query_rows(bs.query_history_k_data_plus(
                    source_code(code), ','.join(DAILY_FIELDS), start_date=START, end_date=END, frequency='d', adjustflag='3')))
                daily = validate_daily(code, raw['fields'], raw['rows'], days)
                packet = {'instrument': code, 'captured_at_utc': raw['captured_at_utc'],
                          'raw_daily': {'fields': raw['fields'], 'rows': raw['rows']}, 'daily': daily,
                          'raw_quarters': [], 'financial': [], 'quarantine': [], 'source_query_receipts': [receipt]}
                for year, quarter in QUARTERS:
                    identity = {'method': 'query_profit_data', 'code': source_code(code), 'year': year, 'quarter': quarter}
                    raw, receipt = journal.query(identity, lambda: query_rows(
                        bs.query_profit_data(source_code(code), year=year, quarter=quarter)))
                    packet['raw_quarters'].append({'year': year, 'quarter': quarter, 'fields': raw['fields'], 'rows': raw['rows']})
                    packet['source_query_receipts'].append(receipt)
                    valid, quarantine = validate_profit(code, year, quarter, raw['fields'], raw['rows'])
                    packet['financial'].extend(valid); packet['quarantine'].extend(quarantine)
                packet['historical_arrival_verified'] = False
                packet['financial_version_history_complete'] = False
                path = out/'codes'/(code+'.json'); write_packet_once(path, packet)
                progress[code] = sha256_file(path); atomic_json(out/'progress.json', progress)
                print('fundamental pilot captured '+code+' '+str(len(progress))+'/'+str(len(codes)), flush=True)
        finally:
            bs.logout()
    packets = [json.loads((out/'codes'/(code+'.json')).read_text()) for code in codes]
    counts = {p['instrument']: {'daily_rows': len(p['daily']), 'financial_rows': len(p['financial']),
        'quarantined_rows': len(p['quarantine']), 'raw_quarter_responses': len(p['raw_quarters']),
        'nonempty_peTTM_days': sum(bool(r['peTTM']) for r in p['daily'])} for p in packets}
    manifest = {'status': 'FUNDAMENTAL_PILOT_CAPTURE_COMPLETE_NOT_ADMITTED_FOR_STRATEGY',
        'request_sha256': request_sha256, 'window': [START, END], 'codes': codes,
        'per_code_sha256': progress, 'counts': counts, 'quarters': [list(q) for q in QUARTERS],
        'query_attempt_reservations': len(list(out.rglob('reserved-*.json'))),
        'max_query_attempt_reservations': req['max_query_attempt_reservations'],
        'journal_artifact_sha256': {str(p.relative_to(out)): sha256_file(p) for p in sorted((out/'queries').rglob('*.json'))},
        'financial_units': {'netProfit': 'CNY', 'MBRevenue': 'CNY', 'totalShare': 'shares', 'epsTTM': 'CNY/share'},
        'historical_arrival_verified': False, 'financial_version_history_complete': False,
        '2026_market_or_return_values_queried': False, 'strategy_return_computed': False,
        'investment_factor_admitted': False, 'objective_achieved': False}
    atomic_json(out/'manifest.json', manifest)
    print('fundamental pilot capture complete; not admitted for strategy', flush=True)
    return 0


if __name__ == '__main__': raise SystemExit(main())
