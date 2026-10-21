"""Bounded price-delay raw sources, with authenticated clipped cache lineage.

Only SDK-decoded source responses are journaled; this is not TCP wire capture.
No corporate-action admission, portfolio ROI or 2026 query is performed."""
import argparse
import fcntl
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_frozen_target_development_data import target_codes,clipped_packet
from scripts.inventory_price_delay_sources_pre2026 import core_fingerprint
from scripts.capture_budgeted_residual_raw_pre2026 import validate_packet,load_reuse_packet,fetch_packet
from scripts.capture_illiquidity_raw_development import (
    calendar_diagnostic,read_vendor_response,
)
from scripts.capture_low_risk_raw_account_data import (
    BAR_FIELDS,source_code,
)
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

START,END='2023-12-29','2025-12-31'
METHOD_FILES=('scripts/capture_price_delay_raw_pre2026.py',
    'scripts/capture_budgeted_residual_raw_pre2026.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_frozen_target_development_data.py',
    'scripts/capture_illiquidity_raw_development.py','scripts/capture_low_risk_raw_account_data.py',
    'scripts/fundamental_query_journal.py','scripts/inventory_price_delay_sources_pre2026.py')
SCREEN_FILES=('experiments/qlib/price-delay-pre2026-development-results.json',
    'experiments/qlib/price-delay-pre2026-account-independent-review.json',
    'experiments/qlib/price-delay-pre2026-gap-supplement-verification.json',
    'experiments/qlib/price-delay-pre2026-raw-source-inventory.json',
    'experiments/qlib/price-delay-gap-supplement-independent-review.json')


def load_clipped_reuse(path,code,expected_sha,sessions,source_directory):
    if sha256_file(path)!=expected_sha:raise ValueError('reused packet checksum changed')
    original=json.loads(Path(path).read_text())
    if original['instrument']!=code:raise ValueError('source identity changed')
    if original['window']!=[START,END]:
        raise ValueError('original source window does not cover development cutoff')
    validate_packet(original,code)
    packet=clipped_packet(original)
    validate_packet(packet,code)
    packet['provenance']={'kind':'AUTHENTICATED_CLIPPED_REUSE',
        'original_sha256':expected_sha,'original_source_directory':source_directory,
        'original_window':original['window'],'source_contains_later_bytes':original['window'][1]>END,
        'original_provenance':original.get('provenance'),
        'original_source_query_receipts':original.get('source_query_receipts'),
        'historical_arrival_verified':False,'corporate_action_completeness_verified':False}
    return packet,calendar_diagnostic(packet['bars'],sessions)


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','targets','source-root','output-dir'):
        p.add_argument('--'+n,required=True)
    args=p.parse_args(argv);requestfile=Path(args.request);repo=Path(__file__).resolve().parents[1]
    if sha256_file(requestfile)!=args.expected_request_sha256:raise ValueError('raw capture request changed')
    r=json.loads(requestfile.read_text())
    if (r['status']!='FROZEN_PRICE_DELAY_RAW_SOURCE_REQUEST' or r['window']!=[START,END]
            or r['candidate']!='price_delay_d1' or r['maximum_new_query_reservations']!=88
            or r['max_attempts_per_query']!=1 or r['maximum_consecutive_failed_fresh_codes']!=3
            or r['maximum_cross_restart_administrative_login_attempts']!=3
            or r['socket_timeout_seconds']!=20
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())
            or version('baostock')!=r['baostock_version']):raise ValueError('raw capture method changed')
    if (r['protocol_file']!='docs/research/price-delay-raw-source-plan-2026-10-21.md'
            or sha256_file(repo/r['protocol_file'])!=r['protocol_sha256']):
        raise ValueError('source capture protocol changed')
    if set(r['screen_files_sha256'])!=set(SCREEN_FILES) or any(sha256_file(repo/n)!=h for n,h in r['screen_files_sha256'].items()):
        raise ValueError('development screen evidence changed')
    audit=json.loads((repo/SCREEN_FILES[1]).read_text())
    supplement=json.loads((repo/SCREEN_FILES[2]).read_text())
    if (audit['status']!='PASS_INDEPENDENT_CSV_AUDIT_WITH_SELECTION_BLOCKED'
            or audit['critical_or_important_audit_findings']
            or supplement['supplemental_same_gate_candidate']!='price_delay_d1'
            or supplement['original_summary_sha256']!=audit['summary_sha256']
            or any(r['remaining_unverified'] for r in supplement['checks'].values())):
        raise ValueError('original account audit and supplemental same-gate evidence required')
    inventory=json.loads((repo/SCREEN_FILES[3]).read_text())
    if inventory['raw_core_conflict_codes'] or inventory['candidate']!='price_delay_d1':
        raise ValueError('inventory is conflicted or wrong candidate')
    if sha256_file(args.targets)!=r['target_sha256'] or r['target_sha256']!=inventory['target_sha256']:
        raise ValueError('fixed target file changed')
    targets=json.loads(Path(args.targets).read_text())['price_delay_d1'];codes=target_codes(targets)
    if codes!=r['codes'] or len(codes)!=151 or len(targets)!=24:
        raise ValueError('complete fixed universe and monthly schedule required')
    source=Path(args.source_root);sources={};routes={}
    for name,h in inventory['source_manifests_sha256'].items():
        if Path(name).name!=name:raise ValueError('invalid source directory identity')
        directory=source/name
        if sha256_file(directory/'manifest.json')!=h:raise ValueError('reuse manifest changed')
        sources[name]=(directory,json.loads((directory/'manifest.json').read_text()))
    calendar_path=source/r['reference_calendar_file']
    if (r['reference_calendar_file']!='qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt'
            or sha256_file(calendar_path)!=r['reference_calendar_sha256']
            or r['reference_calendar_sha256']!=inventory['reference_calendar_sha256']):
        raise ValueError('reference exchange calendar changed')
    sessions=[d for d in calendar_path.read_text().splitlines() if START<=d<=END]
    if sessions!=sorted(set(sessions)) or len(sessions)!=486 or sessions[0]!=START or sessions[-1]!=END:
        raise ValueError('explicit complete development calendar required')
    for code in codes:
        item=inventory['items'][code]
        if item['status']=='NO_EXISTING_RAW_PACKET':continue
        if item['status']!='EXISTING_ORIGINALS_AUTHENTICATED_NOT_ADMITTED':
            raise ValueError('source inventory requires conflict review')
        name=item['priority_route'];choice=item['choices'][0]
        if name!=choice['source_directory'] or name not in sources:
            raise ValueError('inventory priority route changed')
        manifest=sources[name][1]
        if manifest['per_code_sha256'][code]!=choice['original_packet_sha256']:
            raise ValueError('inventory packet identity changed')
        routes[code]={'directory':name,'packet_sha256':choice['original_packet_sha256'],
            'pre2026_raw_core_sha256':choice['pre2026_raw_core_sha256']}
    fresh=[c for c in codes if c not in routes]
    if (routes!=r['reuse_routes'] or fresh!=r['fresh_codes'] or fresh!=inventory['fresh_codes'] or len(routes)!=129 or len(fresh)*4!=r['maximum_new_query_reservations']):
        raise ValueError('fixed routing or new source budget changed')
    # Authenticate every reused input before opening any source connection.
    for code,route in routes.items():
        packet,diagnostic=load_clipped_reuse(sources[route['directory']][0]/'codes'/(code+'.json'),code,route['packet_sha256'],sessions,route['directory'])
        if core_fingerprint(packet)!=route['pre2026_raw_core_sha256'] or not diagnostic['full_explicit_calendar_covered']:
            raise ValueError('inventory raw core or full reuse calendar changed')
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if (out/'request.json').exists():
            if (out/'request.json').read_bytes()!=requestfile.read_bytes():raise ValueError('checkpoint request changed')
        else:
            (out/'codes').mkdir();(out/'request.json').write_bytes(requestfile.read_bytes())
            atomic_json(out/'calendar.json',{'sessions':sessions,'origin_sha256':r['reference_calendar_sha256'],'clipped_to':[START,END]})
            atomic_json(out/'progress.json',{});atomic_json(out/'errors.json',{})
        expected_calendar={'sessions':sessions,'origin_sha256':r['reference_calendar_sha256'],'clipped_to':[START,END]}
        if json.loads((out/'calendar.json').read_text())!=expected_calendar:raise ValueError('checkpoint calendar changed')
        progress=json.loads((out/'progress.json').read_text());errors=json.loads((out/'errors.json').read_text())
        if set(progress)&set(errors) or not (set(progress)|set(errors))<=set(codes):raise ValueError('checkpoint universe changed')
        for code,h in progress.items():
            load_reuse_packet(out/'codes'/(code+'.json'),code,h,sessions)
        for code,h in errors.items():
            if sha256_file(out/'errors'/(code+'.json'))!=h:raise ValueError('checkpoint error changed')
        if (out/'stopped.json').exists():raise ValueError('previous three-source-failure stop preserved; no automatic restart')
        for code,route in routes.items():
            if code in progress:continue
            path=out/'codes'/(code+'.json')
            if path.exists():raise ValueError('uncheckpointed source packet preserved')
            original=sources[route['directory']][0]/'codes'/(code+'.json')
            if sha256_file(original)!=route['packet_sha256']:raise ValueError('reuse changed during capture')
            packet,_=load_clipped_reuse(original,code,route['packet_sha256'],sessions,route['directory'])
            atomic_json(path,packet);progress[code]=sha256_file(path);atomic_json(out/'progress.json',progress)
        journal=QueryJournal(out,max_queries=max(1,r['maximum_new_query_reservations']),max_attempts=1)
        bs=None;login_number=None
        try:
            if any(c not in progress and c not in errors for c in fresh):
                import baostock as bs
                socket.setdefaulttimeout(20)
                login_number=len(list(out.glob('login-reserved-*.json')))+1
                if login_number>3:raise ValueError('three cross-restart login attempts exhausted')
                write_packet_once(out/f'login-reserved-{login_number}.json',{'attempt':login_number,'request_sha256':args.expected_request_sha256})
                try:login=bs.login()
                except Exception as exc:
                    write_packet_once(out/f'login-response-{login_number}.json',{'status':'ERROR','error_type':type(exc).__name__,'error':str(exc)});raise
                write_packet_once(out/f'login-response-{login_number}.json',{'error_code':login.error_code,'error_msg':login.error_msg})
                if login.error_code!='0':raise RuntimeError('raw source login failed')
            consecutive=0
            for number,code in enumerate(fresh,1):
                if code in progress:consecutive=0;continue
                if code in errors:consecutive+=1
                else:
                    path=out/'codes'/(code+'.json')
                    if path.exists():raise ValueError('uncheckpointed source response preserved; inspect before resume')
                    symbol=source_code(code)
                    def fetch(component,parameters):
                        if component=='daily':response=bs.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),**parameters)
                        elif component.startswith('dividend'):response=bs.query_dividend_data(symbol,**parameters)
                        else:response=bs.query_adjust_factor(symbol,**parameters)
                        return read_vendor_response(response)
                    try:
                        packet=fetch_packet(journal,code,args.expected_request_sha256,fetch)
                        calendar_diagnostic(packet['bars'],sessions)
                    except Exception as exc:
                        (out/'errors').mkdir(exist_ok=True);error=out/'errors'/(code+'.json')
                        write_packet_once(error,{'instrument':code,'request_sha256':args.expected_request_sha256,
                            'error_type':type(exc).__name__,'error':str(exc),'raw_responses_retained':True})
                        errors[code]=sha256_file(error);atomic_json(out/'errors.json',errors);consecutive+=1
                        print('source error retained',code,type(exc).__name__,flush=True)
                    else:
                        atomic_json(path,packet);progress[code]=sha256_file(path);atomic_json(out/'progress.json',progress);consecutive=0
                if number%10==0 or number==len(fresh):print('fresh sources',number,'/',len(fresh),'success',len(progress),'errors',len(errors),flush=True)
                if consecutive>=3:
                    write_packet_once(out/'stopped.json',{'reason':'THREE_CONSECUTIVE_FAILED_FRESH_CODES','last_instrument':code});break
        finally:
            if bs is not None and login_number is not None:
                try:
                    logout=bs.logout();record={'cleanup_called':True,'error_code':getattr(logout,'error_code',None),'error_msg':getattr(logout,'error_msg',None)}
                except Exception as exc:record={'cleanup_called':True,'error_type':type(exc).__name__,'error':str(exc)}
                write_packet_once(out/f'logout-response-{login_number}.json',record)
        totals={'bar_rows':0,'distributions':0,'adjustments':0,'quarantines':0};calendars={}
        for code,h in progress.items():
            packet,calendars[code]=load_reuse_packet(out/'codes'/(code+'.json'),code,h,sessions)
            for key,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):
                totals[key]+=len(packet[field])
        manifest={'status':'PRICE_DELAY_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE','window':[START,END],
            'requested_names':len(codes),'names':len(progress),'totals':totals,'request_sha256':args.expected_request_sha256,
            'target_sha256':r['target_sha256'],'calendar_sha256':sha256_file(out/'calendar.json'),
            'per_code_sha256':progress,'errors_sha256':errors,'calendar_diagnostics':calendars,
            'reuse_routes':routes,'fresh_codes':fresh,'maximum_new_query_reservations':r['maximum_new_query_reservations'],
            'query_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
            'pending_codes':[c for c in codes if c not in progress and c not in errors],
            'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
            'missing_rows_synthesized':False,'admitted_for_account_replay':False,'new_2026_market_queries':False,
            'historical_arrival_verified':False,'portfolio_return_computed':False,'objective_achieved':False,
            'corporate_action_completeness_verified':False,'original_cache_may_include_later_bytes':False,
            'SDK_decoded_responses_not_TCP_wire':True,'strategy_or_targets_changed':False}
        atomic_json(out/'manifest.json',manifest)
        print('raw source capture complete',len(progress),'/',len(codes),'errors',len(errors),flush=True)
        return 0 if len(progress)==len(codes) else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
