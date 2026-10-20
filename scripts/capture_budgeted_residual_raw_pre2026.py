"""Fixed-universe raw sources; source admission and portfolio ROI are separate."""
import argparse
import fcntl
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_frozen_target_development_data import target_codes
from scripts.capture_illiquidity_raw_development import (
    calendar_diagnostic,preserve_response,read_vendor_response,unwrap_vendor_response,
)
from scripts.capture_low_risk_raw_account_data import (
    BAR_FIELDS,DIVIDEND_FIELDS,ADJUST_FIELDS,source_code,validate_bars,validate_dividends,
)
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

START,END='2023-12-29','2025-12-31'
METHOD_FILES=('scripts/capture_budgeted_residual_raw_pre2026.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_frozen_target_development_data.py',
    'scripts/capture_illiquidity_raw_development.py','scripts/capture_low_risk_raw_account_data.py',
    'scripts/fundamental_query_journal.py')


def validate_packet(packet,code):
    if packet['instrument']!=code or packet['window']!=[START,END]:
        raise ValueError('reuse identity or pre2026 window changed')
    validate_bars(code,BAR_FIELDS,[[r[k] for k in BAR_FIELDS] for r in packet['bars']])
    if any(not START<=r['date']<=END for r in packet['bars']):
        raise ValueError('bar crossed development cutoff')
    for year in (2024,2025):
        rows=[r for r in packet['distributions'] if r['dividOperateDate'][:4]==str(year)]
        validate_dividends(code,DIVIDEND_FIELDS,[[r[k] for k in DIVIDEND_FIELDS] for r in rows],year)
    if any(not START<=r['dividOperateDate']<=END for r in packet['distributions']):
        raise ValueError('distribution crossed development cutoff')
    if any(r['code']!=source_code(code) or not START<=r['dividOperateDate']<=END for r in packet['adjustments']):
        raise ValueError('adjustment crossed development cutoff or security')


def load_reuse_packet(path,code,expected_sha,sessions):
    if sha256_file(path)!=expected_sha:raise ValueError('reused packet checksum changed')
    packet=json.loads(Path(path).read_text());validate_packet(packet,code)
    return packet,calendar_diagnostic(packet['bars'],sessions)


def fetch_packet(journal,code,request_sha,fetch):
    receipts={}
    def get(component,parameters):
        data,receipts[component]=preserve_response(journal,
            {'source':'BaoStock','instrument':code,'component':component,'parameters':parameters,
             'raw_development_request_sha256':request_sha},
            lambda:fetch(component,parameters),unwrap_vendor_response)
        return data
    daily=get('daily',{'start_date':START,'end_date':END,'frequency':'d','adjustflag':'3'})
    bars=validate_bars(code,daily['fields'],daily['rows'])
    if any(not START<=r['date']<=END for r in bars):raise ValueError('provider crossed development cutoff')
    distributions=[];quarantine=[]
    for year in (2024,2025):
        d=get('dividend'+str(year),{'year':str(year),'yearType':'operate'})
        accepted,excluded=validate_dividends(code,d['fields'],d['rows'],year)
        distributions.extend(accepted);quarantine.extend(excluded)
    a=get('adjustments',{'start_date':START,'end_date':END})
    if tuple(a['fields'])!=ADJUST_FIELDS or any(len(r)!=len(ADJUST_FIELDS) for r in a['rows']):
        raise ValueError('adjustment source schema changed')
    packet={'instrument':code,'window':[START,END],'bars':bars,'distributions':distributions,
        'quarantine':quarantine,'adjustments':[dict(zip(a['fields'],r)) for r in a['rows']],
        'source_query_receipts':receipts,'provenance':{'kind':'JOURNALED_PRE2026_RAW_SOURCE',
            'request_sha256':request_sha,'query_end':END,'calendar_complete_not_assumed':True}}
    validate_packet(packet,code)
    return packet


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','targets','source-root','output-dir'):
        p.add_argument('--'+n,required=True)
    args=p.parse_args(argv);requestfile=Path(args.request);repo=Path(__file__).resolve().parents[1]
    if sha256_file(requestfile)!=args.expected_request_sha256:raise ValueError('raw capture request changed')
    r=json.loads(requestfile.read_text())
    if (r['status']!='FROZEN_BUDGETED_RESIDUAL_RAW_SOURCE_REQUEST' or r['window']!=[START,END]
            or r['max_attempts_per_query']!=1 or r['maximum_consecutive_failed_fresh_codes']!=3
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())
            or version('baostock')!=r['baostock_version']):raise ValueError('raw capture method changed')
    expected_screens={'experiments/qlib/budgeted-residual-pre2026-results.json',
        'experiments/qlib/budgeted-residual-pre2026-independent-csv-audit.json'}
    if set(r['screen_files_sha256'])!=expected_screens or any(sha256_file(repo/n)!=h for n,h in r['screen_files_sha256'].items()):
        raise ValueError('development screen evidence changed')
    audit=json.loads((repo/'experiments/qlib/budgeted-residual-pre2026-independent-csv-audit.json').read_text())
    if not audit['development_gate_passes_independently']:raise ValueError('raw capture lead not admitted by development screen')
    if sha256_file(args.targets)!=r['target_sha256']:raise ValueError('fixed target file changed')
    targets=json.loads(Path(args.targets).read_text());codes=target_codes(targets)
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
        load_reuse_packet(sources[route['directory']][0]/'codes'/(code+'.json'),code,route['packet_sha256'],sessions)
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
        manifest={'status':'BUDGETED_RESIDUAL_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE','window':[START,END],
            'requested_names':len(codes),'names':len(progress),'totals':totals,'request_sha256':args.expected_request_sha256,
            'target_sha256':r['target_sha256'],'calendar_sha256':sha256_file(out/'calendar.json'),
            'per_code_sha256':progress,'errors_sha256':errors,'calendar_diagnostics':calendars,
            'reuse_routes':routes,'fresh_codes':fresh,'maximum_new_query_reservations':r['maximum_new_query_reservations'],
            'query_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
            'pending_codes':[c for c in codes if c not in progress and c not in errors],
            'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
            'missing_rows_synthesized':False,'admitted_for_account_replay':False,'new_2026_market_queries':False,
            'historical_arrival_verified':False,'portfolio_return_computed':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
        print('raw source capture complete',len(progress),'/',len(codes),'errors',len(errors),flush=True)
        return 0 if len(progress)==len(codes) else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
