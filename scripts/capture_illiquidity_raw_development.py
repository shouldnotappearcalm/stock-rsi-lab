"""Capture sources before admission, retaining incomplete responses and query budget.

This does not certify missing sessions, create prices or change investment rules.
Original failed capture and all75 checkpoints remain immutable.
"""
import argparse
import fcntl
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_frozen_target_development_data import target_codes
from scripts.capture_low_risk_raw_account_data import (
    BAR_FIELDS,ADJUST_FIELDS,source_code,validate_bars,validate_dividends,
)
from scripts.fundamental_query_journal import QueryJournal

START,END='2023-12-29','2025-12-31'


def preserve_response(journal,identity,fetch,validate):
    payload,receipt=journal.query(identity,fetch)
    return validate(payload),receipt


def read_vendor_response(response):
    record={'initial_error_code':response.error_code,'initial_error_msg':response.error_msg,
        'fields':None if response.fields is None else list(response.fields),
        'rows':[],'iteration_error_type':None,'iteration_error':None}
    if response.error_code=='0':
        try:
            while response.next():record['rows'].append(response.get_row_data())
        except Exception as exc:
            record.update(iteration_error_type=type(exc).__name__,iteration_error=str(exc))
    record.update(final_error_code=response.error_code,final_error_msg=response.error_msg)
    return ['provider_response'],[record]


def unwrap_vendor_response(payload):
    if payload['fields']!=['provider_response'] or len(payload['rows'])!=1:
        raise ValueError('source response envelope changed')
    record=payload['rows'][0]
    if record['initial_error_code']!='0' or record['final_error_code']!='0' or record['iteration_error_type'] is not None:
        raise RuntimeError('provider response error retained in query journal')
    return {'fields':record['fields'],'rows':record['rows']}


def calendar_diagnostic(rows,sessions):
    days=[r['date'] for r in rows]
    if days!=sorted(set(days)) or any(d not in sessions for d in days):
        raise ValueError('source dates outside unique ordered explicit calendar')
    return {'full_explicit_calendar_covered':days==sessions,'observed_rows':len(rows),
        'first_observed_session':days[0] if days else None,
        'last_observed_session':days[-1] if days else None,
        'missing_sessions':[d for d in sessions if d not in set(days)],
        'missing_sessions_classified_as_prelisting':False,'synthetic_source_rows_created':0}


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','targets','checkpoint-dir','reuse-dir','output-dir'):
        p.add_argument('--'+name,required=True)
    args=p.parse_args(argv);request_path=Path(args.request)
    if sha256_file(request_path)!=args.expected_request_sha256:raise ValueError('request changed')
    r=json.loads(request_path.read_text());root=Path(__file__).resolve().parents[1]
    if r['status']!='FROZEN_ILLIQUIDITY_SOURCE_CONTINUATION_BEFORE_NEW_QUERIES' or r['window']!=[START,END]:
        raise ValueError('wrong source continuation protocol')
    for file,h in r['method_code_sha256'].items():
        if sha256_file(root/file)!=h:raise ValueError('source method changed')
    if version('baostock')!=r['package_version']:raise ValueError('source client version changed')
    if sha256_file(args.targets)!=r['target_sha256']:raise ValueError('targets changed')
    targets=json.loads(Path(args.targets).read_text());codes=target_codes(targets)
    if codes!=r['codes']:raise ValueError('complete original universe required')
    previous,reuse,out=map(Path,(args.checkpoint_dir,args.reuse_dir,args.output_dir))
    for path,key in ((previous/'request.json','previous_request_sha256'),(previous/'progress.json','previous_progress_sha256'),
                     (previous/'calendar.json','calendar_sha256'),(reuse/'manifest.json','reuse_manifest_sha256')):
        if sha256_file(path)!=r[key]:raise ValueError('immutable source checkpoint changed')
    completed=json.loads((previous/'progress.json').read_text())
    old=json.loads((reuse/'manifest.json').read_text());sessions=json.loads((previous/'calendar.json').read_text())['sessions']
    if len(completed)!=75 or sessions[0]!=START or sessions[-1]!=END or len(sessions)!=486:
        raise ValueError('original checkpoint/calendar identity changed')
    fresh=[c for c in codes if c not in completed and c not in old['per_code_sha256']]
    if fresh!=r['fresh_codes'] or len(fresh)*4!=r['maximum_new_query_reservations']:
        raise ValueError('remaining source budget/universe changed')
    out.mkdir(parents=True,exist_ok=True)
    lock=(out/'capture.lock').open('a+')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    bs=None
    try:
        if (out/'request.json').exists():
            if (out/'request.json').read_bytes()!=request_path.read_bytes():raise ValueError('continuation checkpoint request changed')
        else:
            (out/'codes').mkdir();(out/'request.json').write_bytes(request_path.read_bytes())
            (out/'calendar.json').write_bytes((previous/'calendar.json').read_bytes());atomic_json(out/'progress.json',{})
        if sha256_file(out/'calendar.json')!=r['calendar_sha256']:raise ValueError('continuation calendar changed')
        progress=json.loads((out/'progress.json').read_text());journal=QueryJournal(out,max_queries=r['maximum_new_query_reservations'],max_attempts=1)
        for code,h in progress.items():
            if code not in codes or sha256_file(out/'codes'/(code+'.json'))!=h:raise ValueError('continuation packet changed')
        if any(c not in progress for c in fresh):
            import baostock as bs
            socket.setdefaulttimeout(20)
            if bs.login().error_code!='0':raise RuntimeError('source login failed')
        for number,code in enumerate(codes,1):
            if code in progress:continue
            path=out/'codes'/(code+'.json')
            if path.exists():raise ValueError('uncheckpointed packet preserved; inspect before resume')
            if code in completed or code in old['per_code_sha256']:
                origin=previous if code in completed else reuse
                expected=completed[code] if code in completed else old['per_code_sha256'][code]
                source=origin/'codes'/(code+'.json')
                if sha256_file(source)!=expected:raise ValueError('reused original packet changed')
                packet=json.loads(source.read_text());route='BYTE_IDENTICAL_CHECKPOINT_OR_PRIOR_REUSE'
                data=source.read_bytes()
            else:
                symbol=source_code(code);payloads={};receipts={}
                components=[('daily',{'start_date':START,'end_date':END,'frequency':'d','adjustflag':'3'},
                    lambda:read_vendor_response(bs.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),start_date=START,end_date=END,frequency='d',adjustflag='3'))),
                    ('dividend2024',{'year':'2024','yearType':'operate'},lambda:read_vendor_response(bs.query_dividend_data(symbol,year='2024',yearType='operate'))),
                    ('dividend2025',{'year':'2025','yearType':'operate'},lambda:read_vendor_response(bs.query_dividend_data(symbol,year='2025',yearType='operate'))),
                    ('adjustments',{'start_date':START,'end_date':END},lambda:read_vendor_response(bs.query_adjust_factor(symbol,start_date=START,end_date=END)))]
                for component,parameters,fetch in components:
                    payloads[component],receipts[component]=preserve_response(journal,
                        {'source':'BaoStock','instrument':code,'component':component,'parameters':parameters,
                         'continuation_request_sha256':args.expected_request_sha256},fetch,unwrap_vendor_response)
                daily=payloads['daily'];bars=validate_bars(code,daily['fields'],daily['rows'])
                distributions=[];quarantine=[]
                for year in (2024,2025):
                    payload=payloads['dividend'+str(year)]
                    accepted,excluded=validate_dividends(code,payload['fields'],payload['rows'],year)
                    distributions.extend(accepted);quarantine.extend(excluded)
                adjustment=payloads['adjustments']
                if tuple(adjustment['fields'])!=ADJUST_FIELDS:raise ValueError('adjustment schema changed')
                adjustments=[dict(zip(adjustment['fields'],v)) for v in adjustment['rows']]
                if any(v['code']!=symbol or not START<=v['dividOperateDate']<=END for v in adjustments):
                    raise ValueError('adjustment outside development cutoff')
                packet={'instrument':code,'window':[START,END],'bars':bars,'distributions':distributions,
                    'quarantine':quarantine,'adjustments':adjustments,'source_query_receipts':receipts,
                    'provenance':{'kind':'JOURNALED_PRE2026_SOURCE_QUERY','query_end':END,
                        'calendar_complete_not_assumed':True,'original_failed_capture_unchanged':True}}
                data=(json.dumps(packet,indent=2)+'\n').encode();route='JOURNALED_PRE2026_SOURCE_QUERY'
            if packet['instrument']!=code or packet['window']!=[START,END]:raise ValueError('packet identity changed')
            if any(not START<=v['date']<=END for v in packet['bars']):raise ValueError('bar outside development cutoff')
            calendar_diagnostic(packet['bars'],sessions)
            path.write_bytes(data);progress[code]=sha256_file(path);atomic_json(out/'progress.json',progress)
            if number%15==0 or number==len(codes):print('captured source',number,'/',len(codes),code,route,flush=True)
        calendars={};totals={'bar_rows':0,'distributions':0,'adjustments':0,'quarantines':0}
        for code in codes:
            packet=json.loads((out/'codes'/(code+'.json')).read_text());calendars[code]=calendar_diagnostic(packet['bars'],sessions)
            for key,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):
                totals[key]+=len(packet[field])
        manifest={'status':'ILLIQUIDITY_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE','window':[START,END],
            'names':len(codes),'totals':totals,'request_sha256':args.expected_request_sha256,
            'target_sha256':r['target_sha256'],'calendar_sha256':sha256_file(out/'calendar.json'),
            'per_code_sha256':progress,'calendar_diagnostics':calendars,
            'maximum_new_query_reservations':r['maximum_new_query_reservations'],
            'query_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
            'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
            'original_failed_capture_unchanged':True,'missing_rows_synthesized':False,
            'admitted_for_account_replay':False,'new_2026_market_queries':False,
            'historical_arrival_verified':False,'portfolio_return_computed':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
        print('source capture complete; incomplete calendars',sum(not v['full_explicit_calendar_covered'] for v in calendars.values()),flush=True)
    finally:
        if bs is not None:bs.logout()
        lock.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
