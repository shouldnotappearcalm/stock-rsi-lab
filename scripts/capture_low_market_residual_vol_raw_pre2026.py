"""One bounded pre2026 raw-source capture; no restart, admission or ROI.

SDK import is delayed until authenticated source preflight has completed.
Every financial query uses the inherited immutable one-attempt journal.
"""
import argparse
import hashlib
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_budgeted_residual_raw_pre2026 import (
    METHOD_FILES as SHARED_METHODS, fetch_packet, load_reuse_packet, validate_packet,
)
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_illiquidity_raw_development import calendar_diagnostic, read_vendor_response
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, source_code
from scripts.fundamental_query_journal import QueryJournal, write_packet_once

START, END = '2023-12-29', '2025-12-31'
CANDIDATE = 'low_market_residual_vol_1m'
OUTPUT = 'low-market-residual-vol1m-raw-pre2026-20261021'
ACCOUNT = 'low-market-residual-vol1m-budgeted-pre2026-development-20261021'
TARGET_SHA = '64dd4c589b3661aceb5b103bc336a889f68449089f6ce9c2aff4312a7c8373fc'
PROTOCOL = 'docs/research/low-market-residual-vol1m-raw-source-plan-2026-10-21.md'
INVENTORY = 'experiments/qlib/low-market-residual-vol1m-pre2026-raw-source-inventory.json'
MANDATORY = 'experiments/qlib/low-market-residual-vol1m-pre2026-mandatory-snapshot-inventory.json'
REFERENCE_CALENDAR = 'qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt'
SOURCE_NAMES = ('price-delay-raw-dev-20261021', 'low-beta60-raw-dev-20261021',
    'szse-value-momentum-raw-dev-20261021', 'budgeted-residual-raw-dev-20261021',
    'return-families-raw-dev-20261017', 'szse-value-raw-dev-20261017',
    'illiquidity-raw-source-continuation-20261020')
METHOD_FILES = (*SHARED_METHODS, 'scripts/capture_low_market_residual_vol_raw_pre2026.py')
SCREEN_FILES = ('experiments/qlib/low-market-residual-vol1m-budgeted-pre2026-results.json',
    'experiments/qlib/low-market-residual-vol1m-budgeted-development-independent-audit.json',
    'experiments/qlib/low-market-residual-vol1m-budgeted-pre2026-verification.json')
FINANCIAL_FILES = tuple(f'{bps}/{family}/{name}' for bps in (20, 40)
    for family in ('eligible_equal_weight', 'low_total_vol_1m_control', CANDIDATE)
    for name in ('days.csv', 'decision_intents.json', 'holdings.csv', 'orders.csv',
                 'positions.pkl', 'report.pkl', 'suspension_mark_audit.json'))


def read(path):
    return json.loads(Path(path).read_text())


def check_scope(r):
    fixed = {'status': 'FROZEN_LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCE_REQUEST',
        'candidate': CANDIDATE, 'window': [START, END],
        'maximum_new_query_reservations': 240, 'max_attempts_per_query': 1,
        'maximum_consecutive_failed_fresh_codes': 3,
        'maximum_administrative_login_attempts': 1, 'socket_timeout_seconds': 20,
        'baostock_version': '0.9.4', 'target_sha256': TARGET_SHA,
        'protocol_file': PROTOCOL, 'reference_calendar_file': REFERENCE_CALENDAR}
    if any(r.get(k) != v for k, v in fixed.items()):
        raise ValueError('fixed pre2026 source protocol changed')
    codes, fresh, routes = r['codes'], r['fresh_codes'], r['reuse_routes']
    if (codes != sorted(set(codes)) or len(codes) != 361 or len(routes) != 301
            or fresh != sorted(set(codes) - set(routes)) or len(fresh) != 60
            or [x['directory'] for x in r['reuse_sources']] != list(SOURCE_NAMES)
            or set(r['method_code_sha256']) != set(METHOD_FILES)
            or set(r['screen_files_sha256']) != set(SCREEN_FILES)
            or set(r['immutable_financial_sha256']) != set(FINANCIAL_FILES)):
        raise ValueError('complete fixed universe, routes, or binding scope changed')


def _core(packet):
    fields = {k: sorted(packet[k], key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))
              for k in ('bars', 'distributions', 'adjustments')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def verify_known_hashes(known):
    changed = [name for name, h in known.items() if not Path(name).is_file() or sha256_file(name) != h]
    if changed:
        raise ValueError('immutable source/financial input changed: ' + ', '.join(changed))


def authenticate(source, repo, request, targets_path):
    """Authenticate actual immutable bytes before any output or SDK connection."""
    source, repo, targets_path = Path(source), Path(repo), Path(targets_path)
    r = request
    check_scope(r)
    if version('baostock') != r['baostock_version']:
        raise ValueError('fixed SDK version changed')
    known = {}
    def bind(path, expected):
        path = Path(path)
        if sha256_file(path) != expected:
            raise ValueError('bound source artifact changed: ' + str(path))
        known[str(path)] = expected
    for n, h in r['method_code_sha256'].items(): bind(repo / n, h)
    for n, h in r['screen_files_sha256'].items(): bind(repo / n, h)
    bind(repo / PROTOCOL, r['protocol_sha256'])
    bind(repo / INVENTORY, r['inventory_sha256'])
    bind(repo / MANDATORY, r['mandatory_snapshot_inventory_sha256'])
    bind(targets_path, r['target_sha256'])
    inventory, mandatory = read(repo / INVENTORY), read(repo / MANDATORY)
    if (inventory['target_sha256'] != r['target_sha256'] or inventory['target_union_names'] != 361
            or inventory['fully_covered_reuse_names'] != 301 or inventory['cross_cache_normalized_raw_core_conflicts']
            or inventory['selected_reuse'] != r['reuse_routes']
            or inventory['missing_or_incomplete_instruments'] != r['fresh_codes']
            or mandatory['inventory_sha256'] != r['inventory_sha256']
            or mandatory['target_sha256'] != r['target_sha256']
            or mandatory['known_conflict_snapshots'] != 0 or mandatory['covered_snapshots'] != 1478
            or mandatory['unknown_snapshots'] != 362 or mandatory['unknown_treated_as_pass'] is not False):
        raise ValueError('inventory or mandatory snapshot source boundary changed')
    targets = read(targets_path)[CANDIDATE]
    if (len(targets) != 24 or sorted({c for t in targets.values() for c in t['weights']}) != r['codes']
            or any(not START <= t['as_of'] < d <= END for d, t in targets.items())):
        raise ValueError('frozen primary monthly targets changed')
    result, audit, verification = (read(repo / n) for n in SCREEN_FILES)
    summary_path = source / ACCOUNT / 'summary.json'
    bind(summary_path, audit['summary_sha256'])
    summary = read(summary_path)
    financial = {f'{label}/{n}': h for label, item in summary['results_by_extra_bps_and_family'].items()
                 for n, h in item['artifact_sha256'].items()}
    if (audit['status'] != 'PASS_INDEPENDENT_BUDGETED_PRE2026_CSV_ACCOUNT_AUDIT'
            or audit['critical_or_important_audit_findings'] or audit['selected_development_lead'] != CANDIDATE
            or audit['2026_market_data_read'] is not False
            or result['actual_summary_sha256'] != audit['summary_sha256']
            or result['independent_audit_sha256'] != r['screen_files_sha256'][SCREEN_FILES[1]]
            or verification['result_sha256'] != r['screen_files_sha256'][SCREEN_FILES[0]]
            or verification['independent_audit_sha256'] != r['screen_files_sha256'][SCREEN_FILES[1]]
            or verification['status'] != 'PRE2026_NORMALIZED_DAILY_GATE_PASS_REQUIRES_RAW_SHARE_CONFIRMATION'
            or financial != r['immutable_financial_sha256']
            or financial != audit['financial_artifact_hashes_verified']
            or summary['targets_sha256'] != r['target_sha256']
            or summary['selected_development_lead'] != CANDIDATE):
        raise ValueError('audited development and actual42 financial artifacts not bound')
    for n, h in financial.items(): bind(source / ACCOUNT / n, h)
    bind(source / REFERENCE_CALENDAR, r['reference_calendar_sha256'])
    all_dates = (source / REFERENCE_CALENDAR).read_text().splitlines()
    if all_dates != sorted(set(all_dates)) or all_dates[-1] != END:
        raise ValueError('reference physical calendar crossed pre2026 cap')
    sessions = [d for d in all_dates if START <= d <= END]
    if len(sessions) != 486 or sessions[0] != START or sessions[-1] != END:
        raise ValueError('complete486 exchange sessions required')
    registered = inventory['source_directories_checked']
    expected_sources = [{k: x[k] for k in ('directory', 'manifest_sha256', 'calendar_sha256')} for x in registered]
    if r['reuse_sources'] != expected_sources:
        raise ValueError('seven registered source identities changed')
    for entry in registered:
        anchor = entry['audit_anchor']
        for field, hashfield in (('file', 'sha256'), ('authenticated_source_manifest_via_request', 'request_sha256')):
            if field not in anchor:continue
            rel = Path(anchor[field])
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('registered historical audit path escaped repository')
            bind(repo / rel, anchor[hashfield])
    manifests = {}
    for entry in r['reuse_sources']:
        d = source / entry['directory']
        bind(d / 'manifest.json', entry['manifest_sha256'])
        m = read(d / 'manifest.json')
        bind(d / 'calendar.json', entry['calendar_sha256'])
        if (m['window'] != [START, END] or m['calendar_sha256'] != entry['calendar_sha256']
                or read(d / 'calendar.json')['sessions'] != sessions):
            raise ValueError('source calendar/window changed')
        manifests[entry['directory']] = m
    # Authenticate every explicitly registered pre2026 overlap/partial reference;
    # an incomplete option remains incomplete and is never promoted to reuse.
    for code, record in inventory['per_instrument'].items():
        full_cores = set()
        for item in record['all_registered_pre2026_cache_options']:
            name = item['directory']
            expected = f'{name}/codes/{code}.json'
            if name not in manifests or item['file'] != expected:
                raise ValueError('registered overlap source path changed')
            if manifests[name]['per_code_sha256'][code] != item['packet_sha256']:
                raise ValueError('registered overlap packet and manifest disagree')
            bind(source / expected, item['packet_sha256'])
            packet, diagnostic = load_reuse_packet(source / expected, code, item['packet_sha256'], sessions)
            core = _core(packet)
            if core != item['raw_core_sha256'] or diagnostic['full_explicit_calendar_covered'] != item['complete_486_session_calendar']:
                raise ValueError('registered overlap core/calendar changed')
            if diagnostic['full_explicit_calendar_covered']:full_cores.add(core)
        if len(full_cores) > 1:
            raise ValueError('registered complete raw source cores conflict')
    routes = {}
    for code, item in r['reuse_routes'].items():
        expected = f"{item['directory']}/codes/{code}.json"
        if item['file'] != expected or item['directory'] not in manifests:
            raise ValueError('reuse exact packet path changed')
        path = source / expected
        if manifests[item['directory']]['per_code_sha256'][code] != item['packet_sha256']:
            raise ValueError('reuse manifest/packet identity disagrees')
        bind(path, item['packet_sha256'])
        packet, diag = load_reuse_packet(path, code, item['packet_sha256'], sessions)
        if not diag['full_explicit_calendar_covered'] or _core(packet) != item['raw_core_sha256']:
            raise ValueError('full reuse coverage or raw core changed')
        routes[code] = {'path': str(path), 'packet_sha256': item['packet_sha256'],
                        'directory': item['directory'], 'file': item['file']}
    verify_known_hashes(known)
    return {'sessions': sessions, 'reuse_routes': routes, 'known_hashes': known}


def load_sdk():
    import baostock
    return baostock


def _error(exc):
    return {'error_type': type(exc).__name__, 'error': str(exc)}


def capture(r, auth, out, sdk, *, request_bytes, request_sha):
    """Create one fresh terminal capture; every failure preserves collected evidence."""
    out = Path(out)
    if out.exists() or out.is_symlink():
        raise ValueError('existing output is immutable; no restart')
    verify_known_hashes(auth['known_hashes'])
    out.mkdir(parents=True)
    progress, errors, diagnostics = {}, {}, {}
    totals = dict(bar_rows=0, distributions=0, adjustments=0, quarantines=0)
    terminal = None
    login = {'login_attempted': False}
    cleanup = {'login_attempted': False, 'logout_attempted': False, 'error_code': None}
    journal = None
    old_timeout = socket.getdefaulttimeout()
    try:
        (out / 'codes').mkdir(); (out / 'errors').mkdir()
        (out / 'request.json').write_bytes(request_bytes)
        atomic_json(out / 'calendar.json', {'sessions': auth['sessions'],
            'origin_sha256': r.get('reference_calendar_sha256'), 'clipped_to': [START, END]})
        atomic_json(out / 'reuse-routes.json', auth['reuse_routes'])
        atomic_json(out / 'input-before.json', auth['known_hashes'])
        atomic_json(out / 'progress.json', progress); atomic_json(out / 'errors.json', errors)
        for code, route in auth['reuse_routes'].items():
            origin = Path(route['path'])
            if sha256_file(origin) != route['packet_sha256']:
                raise ValueError('reuse changed during capture')
            data = origin.read_bytes()
            if hashlib.sha256(data).hexdigest() != route['packet_sha256']:
                raise ValueError('reuse changed during read')
            packet = json.loads(data); validate_packet(packet, code)
            diagnostics[code] = calendar_diagnostic(packet['bars'], auth['sessions'])
            (out / 'codes' / (code + '.json')).write_bytes(data)
            progress[code] = sha256_file(out / 'codes' / (code + '.json'))
            atomic_json(out / 'progress.json', progress)
            for k, field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[k] += len(packet[field])
        if r['fresh_codes']:
            journal = QueryJournal(out, max_queries=r['maximum_new_query_reservations'], max_attempts=1)
            socket.setdefaulttimeout(20)
            write_packet_once(out / 'login-reserved-1.json', {'attempt': 1, 'request_sha256': request_sha})
            login['login_attempted'] = True; cleanup['login_attempted'] = True
            try:
                response = sdk.login()
                login.update(error_code=getattr(response, 'error_code', None), error_msg=getattr(response, 'error_msg', None))
            except BaseException as exc:
                login.update(_error(exc)); raise
            finally:
                write_packet_once(out / 'login-response-1.json', login)
            if login.get('error_code') != '0':
                raise RuntimeError('source login failed; one attempt retained')
        consecutive = 0
        for code in r['fresh_codes']:
            def fetch(component, parameters):
                symbol = source_code(code)
                if component == 'daily': response = sdk.query_history_k_data_plus(symbol, ','.join(BAR_FIELDS), **parameters)
                elif component.startswith('dividend'): response = sdk.query_dividend_data(symbol, **parameters)
                else: response = sdk.query_adjust_factor(symbol, **parameters)
                return read_vendor_response(response)
            try:
                packet = fetch_packet(journal, code, request_sha, fetch)
                diagnostics[code] = calendar_diagnostic(packet['bars'], auth['sessions'])
                atomic_json(out / 'codes' / (code + '.json'), packet)
                progress[code] = sha256_file(out / 'codes' / (code + '.json'))
                atomic_json(out / 'progress.json', progress)
                for k, field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[k] += len(packet[field])
                consecutive = 0
            except BaseException as exc:
                record = {'instrument': code, 'request_sha256': request_sha, 'raw_responses_retained': True, **_error(exc)}
                write_packet_once(out / 'errors' / (code + '.json'), record)
                errors[code] = sha256_file(out / 'errors' / (code + '.json'))
                atomic_json(out / 'errors.json', errors); consecutive += 1
                if not isinstance(exc, Exception): raise
            if consecutive >= 3:
                write_packet_once(out / 'stopped.json', {'reason': 'THREE_CONSECUTIVE_FAILED_FRESH_CODES', 'last_instrument': code})
                break
    except BaseException as exc:
        terminal = _error(exc)
        write_packet_once(out / 'terminal-error.json', terminal)
    finally:
        if login['login_attempted']:
            cleanup['logout_attempted'] = True
            try:
                response = sdk.logout()
                cleanup.update(error_code=getattr(response,'error_code',None), error_msg=getattr(response,'error_msg',None))
            except BaseException as exc: cleanup.update(_error(exc))
            write_packet_once(out / 'logout-response-1.json', cleanup)
        atomic_json(out / 'cleanup.json', cleanup)
        socket.setdefaulttimeout(old_timeout)
        try:
            verify_known_hashes(auth['known_hashes'])
            post = {'source_inputs_unchanged_after_capture': True}
        except BaseException as exc:
            post = {'source_inputs_unchanged_after_capture': False, **_error(exc)}
        atomic_json(out / 'input-postcheck.json', post)
        reservations = list((out / 'queries').glob('*/reserved-*.json'))
        complete = (set(progress) == set(r['codes']) and not errors and terminal is None
            and post['source_inputs_unchanged_after_capture']
            and (not r['fresh_codes'] or (login.get('error_code') == '0' and cleanup.get('error_code') == '0' and 'error' not in cleanup))
            and len(reservations) == len(r['fresh_codes']) * 4)
        manifest = {'status': 'LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE',
            'window': [START,END], 'requested_names': len(r['codes']), 'names':len(progress),
            'capture_complete':complete, 'all_source_calendars_complete':len(diagnostics)==len(r['codes']) and all(d['full_explicit_calendar_covered'] for d in diagnostics.values()),
            'request_sha256':request_sha, 'target_sha256':r['target_sha256'],
            'calendar_sha256':sha256_file(out/'calendar.json') if (out/'calendar.json').exists() else None,
            'per_code_sha256':progress, 'errors_sha256':errors, 'calendar_diagnostics':diagnostics,
            'totals':totals, 'reuse_routes':auth['reuse_routes'], 'fresh_codes':r['fresh_codes'],
            'maximum_new_query_reservations':r['maximum_new_query_reservations'],
            'query_reservations_consumed':len(reservations),
            'pending_codes':[c for c in r['codes'] if c not in progress and c not in errors],
            'abnormal_exit':terminal, 'cleanup_sha256':sha256_file(out/'cleanup.json'),
            'postcheck_sha256':sha256_file(out/'input-postcheck.json'),
            'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
            'missing_rows_synthesized':False,'admitted_for_account_replay':False,
            'corporate_action_completeness_verified':False,'historical_arrival_verified':False,
            'portfolio_return_computed':False,'new_2026_market_queries':False,
            'SDK_decoded_responses_not_TCP_wire':True,'strategy_or_targets_changed':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
    return 0 if complete else 2


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('request','expected-request-sha256','targets','source-root','output-dir'):p.add_argument('--'+n,required=True)
    p.add_argument('--source-preflight-only',action='store_true');args=p.parse_args(argv)
    out, source = Path(args.output_dir), Path(args.source_root)
    if out.exists() or out.is_symlink():raise ValueError('existing output is immutable; no restart')
    if out.resolve() != (source/OUTPUT).resolve():raise ValueError('fixed new source output directory required')
    request_path=Path(args.request)
    if sha256_file(request_path)!=args.expected_request_sha256:raise ValueError('external request checksum changed')
    raw=request_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_request_sha256:raise ValueError('request changed during read')
    r=json.loads(raw)
    auth=authenticate(source,Path(__file__).resolve().parents[1],r,Path(args.targets))
    auth['known_hashes'][str(request_path)]=args.expected_request_sha256
    if args.source_preflight_only:
        verify_known_hashes(auth['known_hashes']);print('source-only preflight; no output or SDK connection',flush=True);return 0
    # A deferred import failure is captured as a terminal initialization failure.
    class DeferredSDK:
        def __init__(self):self.client=None
        def login(self):self.client=load_sdk();return self.client.login()
        def logout(self):
            if self.client is None:raise RuntimeError('SDK initialization failed; no client to close')
            return self.client.logout()
        def __getattr__(self,name):return getattr(self.client,name)
    return capture(r,auth,out,DeferredSDK(),request_bytes=raw,request_sha=args.expected_request_sha256)


if __name__=='__main__':raise SystemExit(main())
