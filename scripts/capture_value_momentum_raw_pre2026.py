"""Fixed composite sources only; reuse exact pre2026 packets and journal7fresh codes."""
import argparse
import fcntl
import json
import socket
from importlib.metadata import version
from pathlib import Path
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_frozen_target_development_data import target_codes
from scripts.capture_budgeted_residual_raw_pre2026 import validate_packet,load_reuse_packet,fetch_packet
from scripts.capture_illiquidity_raw_development import calendar_diagnostic,read_vendor_response
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,source_code
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

START,END='2023-12-29','2025-12-31'
FRESH_CODES=('SZ000021','SZ000032','SZ001389','SZ001696','SZ002156','SZ002312','SZ002429')
SOURCE_NAMES=('low-beta60-raw-dev-20261021','budgeted-residual-raw-dev-20261021',
    'illiquidity-raw-source-continuation-20261020','return-families-raw-dev-20261017','szse-value-raw-dev-20261017')
METHOD_FILES=('scripts/capture_value_momentum_raw_pre2026.py','scripts/capture_budgeted_residual_raw_pre2026.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_frozen_target_development_data.py',
    'scripts/capture_illiquidity_raw_development.py','scripts/capture_low_risk_raw_account_data.py','scripts/fundamental_query_journal.py')
SCREEN_FILES=('experiments/qlib/szse-value-momentum-pre2026-results.json',
    'experiments/qlib/szse-value-momentum-independent-audit.json','experiments/qlib/szse-value-momentum-raw-source-inventory.json')


def check_scope(r):
    if (r['status']!='FROZEN_VALUE_MOMENTUM_RAW_SOURCE_REQUEST' or r['candidate']!='szse_value_momentum_equal'
            or r['window']!=[START,END] or r['fresh_codes']!=list(FRESH_CODES)
            or len(r['codes'])!=103 or len(set(r['codes']))!=103 or len(r['reuse_routes'])!=96
            or set(r['codes'])!=set(r['reuse_routes'])|set(r['fresh_codes'])
            or set(r['reuse_routes'])&set(r['fresh_codes'])
            or [x['directory'] for x in r['reuse_sources']]!=list(SOURCE_NAMES)
            or any(type(r[k]) is not int or r[k]!=v for k,v in (
                ('maximum_new_query_reservations',28),('max_attempts_per_query',1),
                ('maximum_consecutive_failed_fresh_codes',3),('maximum_cross_restart_administrative_login_attempts',3),
                ('socket_timeout_seconds',20)))):
        raise ValueError('fixed103-name96reuse7fresh pre2026scope and28-query ceiling required')


def authenticate_reuse(path,code,expected_sha,sessions):
    packet,diagnostic=load_reuse_packet(path,code,expected_sha,sessions)
    if not diagnostic['full_explicit_calendar_covered']:
        raise ValueError('preexisting reuse requires full explicit source calendar')
    return packet,diagnostic


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','targets','source-root','output-dir'):
        p.add_argument('--'+n,required=True)
    p.add_argument('--preflight-only',action='store_true')
    args=p.parse_args(argv);requestfile=Path(args.request);repo=Path(__file__).resolve().parents[1]
    if sha256_file(requestfile)!=args.expected_request_sha256:raise ValueError('raw capture request changed')
    r=json.loads(requestfile.read_text())
    check_scope(r)
    if (r['status']!='FROZEN_VALUE_MOMENTUM_RAW_SOURCE_REQUEST' or r['window']!=[START,END]
            or r['max_attempts_per_query']!=1 or r['maximum_consecutive_failed_fresh_codes']!=3
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())
            or version('baostock')!=r['baostock_version']):raise ValueError('raw capture method changed')
    expected_screens=set(SCREEN_FILES)
    if set(r['screen_files_sha256'])!=expected_screens or any(sha256_file(repo/n)!=h for n,h in r['screen_files_sha256'].items()):
        raise ValueError('audited development screen or fixed source inventory changed')
    audit=json.loads((repo/SCREEN_FILES[1]).read_text())
    inventory=json.loads((repo/SCREEN_FILES[2]).read_text())
    if (audit['development_gate_passes_independently'] is not True
            or audit['selected_development_lead']!='szse_value_momentum_equal'
            or inventory['conflicting_codes'] or inventory['names']!=103
            or inventory['missing_codes']!=list(FRESH_CODES)
            or inventory['target_sha256']!=r['target_sha256']):
        raise ValueError('passed composite and unchanged unconflicted source inventory required')
    if (r['protocol_file']!='docs/research/szse-value-momentum-raw-source-plan-2026-10-21.md'
            or sha256_file(repo/r['protocol_file'])!=r['protocol_sha256']):raise ValueError('frozen source protocol changed')
    if sha256_file(args.targets)!=r['target_sha256']:raise ValueError('fixed target file changed')
    targets=json.loads(Path(args.targets).read_text())['szse_value_momentum_equal'];codes=target_codes(targets)
    if codes!=r['codes'] or len(targets)!=24:raise ValueError('complete fixed universe and monthly schedule required')
    source=Path(args.source_root);sources={};sessions=None;routes={}
    for item in r['reuse_sources']:
        name=item['directory']
        if Path(name).name!=name or name in sources:raise ValueError('invalid source directory identity')
        directory=source/name
        if sha256_file(directory/'manifest.json')!=item['manifest_sha256']:raise ValueError('reuse manifest changed')
        manifest=json.loads((directory/'manifest.json').read_text())
        if manifest['window']!=[START,END] or sha256_file(directory/'calendar.json')!=manifest['calendar_sha256']:
            raise ValueError('reuse source window/calendar changed')
        current=json.loads((directory/'calendar.json').read_text())['sessions']
        if current!=sorted(set(current)) or len(current)!=486 or current[0]!=START or current[-1]!=END:
            raise ValueError('explicit complete development calendar required')
        if sessions is not None and current!=sessions:raise ValueError('reuse exchange calendars disagree')
        sessions=current;sources[name]=(directory,manifest)
        for code in codes:
            if code not in routes and code in manifest['per_code_sha256']:
                routes[code]={'directory':name,'packet_sha256':manifest['per_code_sha256'][code]}
    fresh=[c for c in codes if c not in routes]
    if (routes!=r['reuse_routes'] or fresh!=r['fresh_codes'] or len(fresh)*4!=r['maximum_new_query_reservations']):
        raise ValueError('fixed routing or new source budget changed')
    # Authenticate every reused input before opening any source connection.
    for code,route in routes.items():
        authenticate_reuse(sources[route['directory']][0]/'codes'/(code+'.json'),code,route['packet_sha256'],sessions)
    if args.preflight_only:
        print('source preflight103names96reuse7fresh28queryceiling; no output or network',flush=True);return 0
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if (out/'request.json').exists():
            if (out/'request.json').read_bytes()!=requestfile.read_bytes():raise ValueError('checkpoint request changed')
        else:
            (out/'codes').mkdir();(out/'request.json').write_bytes(requestfile.read_bytes())
            atomic_json(out/'calendar.json',{'sessions':sessions,'source_calendars':{
                name:manifest['calendar_sha256'] for name,(_,manifest) in sources.items()}})
            atomic_json(out/'progress.json',{});atomic_json(out/'errors.json',{})
        expected_calendar={'sessions':sessions,'source_calendars':{
            name:manifest['calendar_sha256'] for name,(_,manifest) in sources.items()}}
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
            path.write_bytes(original.read_bytes());progress[code]=sha256_file(path);atomic_json(out/'progress.json',progress)
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
        manifest={'status':'VALUE_MOMENTUM_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE','window':[START,END],
            'requested_names':len(codes),'names':len(progress),'totals':totals,'request_sha256':args.expected_request_sha256,
            'target_sha256':r['target_sha256'],'calendar_sha256':sha256_file(out/'calendar.json'),
            'per_code_sha256':progress,'errors_sha256':errors,'calendar_diagnostics':calendars,
            'reuse_routes':routes,'fresh_codes':fresh,'maximum_new_query_reservations':r['maximum_new_query_reservations'],
            'query_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
            'pending_codes':[c for c in codes if c not in progress and c not in errors],
            'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
            'missing_rows_synthesized':False,'admitted_for_account_replay':False,'new_2026_market_queries':False,
            'corporate_action_completeness_verified':False,'SDK_decoded_responses_not_TCP_wire':True,
            'raw_quarantine_or_provenance_may_reference_later_dates':True,
            'historical_arrival_verified':False,'portfolio_return_computed':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
        print('raw source capture complete',len(progress),'/',len(codes),'errors',len(errors),flush=True)
        return 0 if len(progress)==len(codes) else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
