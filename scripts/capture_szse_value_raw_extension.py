"""Append fixed 2026 raw inputs while preserving every development record."""
import argparse
import copy
import json
import math
import socket
from datetime import date,datetime,timezone
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_low_risk_raw_account_data import (
    BAR_FIELDS,ADJUST_FIELDS,source_code,validate_bars,validate_dividends,query_rows,
)

START,END,FIRST='2023-12-29','2026-10-16','2026-01-01'
METHOD_FILES=('scripts/capture_szse_value_raw_extension.py','scripts/capture_low_risk_raw_account_data.py',
              'scripts/capture_cninfo_csi500_reports_pre2026.py')


def full_target_codes(targets):
    if not isinstance(targets,dict) or not targets:raise ValueError('fixed targets required')
    codes=set()
    for day,target in targets.items():
        if not '2024-01-02'<=day<=END or date.fromisoformat(day).isoformat()!=day:
            raise ValueError('target outside frozen cutoff')
        if not START<=target['as_of']<day or date.fromisoformat(target['as_of']).isoformat()!=target['as_of']:
            raise ValueError('prior formation date required')
        weights=target['weights']
        if (not weights or any(type(w) not in (int,float) or not math.isfinite(w) or w<=0 for w in weights.values())
                or math.fsum(weights.values())>1+1e-10):raise ValueError('positive long-only weights required')
        for code in weights:source_code(code);codes.add(code)
    return sorted(codes)


def assert_development_prefix(development,extended):
    if development['instrument']!=extended['instrument']:raise ValueError('development prefix security changed')
    for key,field in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        if [r for r in extended[key] if r[field]<FIRST]!=development[key]:
            raise ValueError('development '+key+' prefix changed')
    earlier=[r for r in extended['quarantine'] if not r['record'].get('dividOperateDate') or r['record']['dividOperateDate']<FIRST]
    if earlier!=development['quarantine']:raise ValueError('development quarantine prefix changed')


def append_2026(development,suffix):
    if development['instrument']!=suffix['instrument']:raise ValueError('suffix security mismatch')
    result=copy.deepcopy(development);result['window']=[START,END]
    for key,field in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        if any(not FIRST<=r[field]<=END for r in suffix[key]):raise ValueError('suffix crossed frozen year/window')
        result[key].extend(copy.deepcopy(suffix[key]))
    result['quarantine'].extend(copy.deepcopy(suffix['quarantine']))
    assert_development_prefix(development,result)
    return result


def fetch_packet(bs,code,start):
    symbol=source_code(code)
    fields,rows=query_rows(bs.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),start_date=start,end_date=END,frequency='d',adjustflag='3'))
    bars=validate_bars(code,fields,rows)
    if any(not start<=r['date']<=END for r in bars):raise ValueError('provider crossed requested bar window')
    distributions=[];quarantine=[]
    for year in ((2026,) if start==FIRST else (2024,2025,2026)):
        fields,rows=query_rows(bs.query_dividend_data(symbol,year=str(year),yearType='operate'))
        accepted,excluded=validate_dividends(code,fields,rows,year)
        distributions.extend(accepted);quarantine.extend(excluded)
    fields,rows=query_rows(bs.query_adjust_factor(symbol,start_date=start,end_date=END))
    if tuple(fields)!=ADJUST_FIELDS:raise ValueError('adjustment schema changed')
    adjustments=[dict(zip(fields,row)) for row in rows]
    if any(r['code']!=symbol or not start<=r['dividOperateDate']<=END for r in adjustments):
        raise ValueError('adjustment outside requested security/window')
    return {'instrument':code,'window':[start,END],'bars':bars,'distributions':distributions,
            'adjustments':adjustments,'quarantine':quarantine}


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','capture-plan','expected-capture-plan-sha256','targets',
                 'development-dir','old-full-dir','output-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1];out=Path(args.output_dir);dev=Path(args.development_dir);old=Path(args.old_full_dir)
    if sha256_file(args.request)!=args.expected_request_sha256 or sha256_file(args.capture_plan)!=args.expected_capture_plan_sha256:
        raise ValueError('frozen capture specification changed')
    request=json.loads(Path(args.request).read_text());plan=json.loads(Path(args.capture_plan).read_text())
    if (plan['status']!='FROZEN_SZSE_VALUE_RAW_EXTENSION_CAPTURE' or plan['input_spec_sha256']!=args.expected_request_sha256
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/n)!=h for n,h in plan['method_code_sha256'].items())
            or request['window']!=[START,END] or sha256_file(args.targets)!=request['target_sha256']
            or sha256_file(dev/'manifest.json')!=request['development_manifest_sha256']
            or sha256_file(old/'manifest.json')!=request['old_full_manifest_sha256']):raise ValueError('capture method/input identity changed')
    codes=full_target_codes(json.loads(Path(args.targets).read_text()));dm=json.loads((dev/'manifest.json').read_text());om=json.loads((old/'manifest.json').read_text())
    expected_routes={'reuse_full_codes':sorted(set(codes)&set(om['per_code_sha256'])),
        'extend_development_codes':sorted(set(codes)&set(dm['per_code_sha256'])-set(om['per_code_sha256'])),
        'new_full_codes':sorted(set(codes)-set(dm['per_code_sha256'])-set(om['per_code_sha256']))}
    if codes!=request['codes'] or any(request[k]!=v for k,v in expected_routes.items()) or not set(dm['per_code_sha256'])<=set(codes):
        raise ValueError('frozen universe/routing changed')
    if sha256_file(old/'calendar.json')!=om['calendar_sha256'] or sha256_file(dev/'calendar.json')!=dm['calendar_sha256']:
        raise ValueError('source calendar changed')
    calendar=json.loads((old/'calendar.json').read_text());sessions=calendar['sessions']
    if (sessions[0]!=START or sessions[-1]!=END or sessions!=sorted(set(sessions))
            or [d for d in sessions if d<FIRST]!=json.loads((dev/'calendar.json').read_text())['sessions']):
        raise ValueError('explicit source calendar/prefix changed')
    if args.resume:
        if ((out/'request.json').read_bytes()!=Path(args.request).read_bytes()
                or (out/'capture-plan.json').read_bytes()!=Path(args.capture_plan).read_bytes()
                or not (out/'calendar.json').is_file() or json.loads((out/'calendar.json').read_text())!=calendar):
            raise ValueError('capture checkpoint plan/calendar changed')
    else:
        if out.exists():raise ValueError('capture output already exists')
        (out/'codes').mkdir(parents=True);(out/'request.json').write_bytes(Path(args.request).read_bytes())
        (out/'capture-plan.json').write_bytes(Path(args.capture_plan).read_bytes());atomic_json(out/'calendar.json',calendar);atomic_json(out/'progress.json',{})
    progress=json.loads((out/'progress.json').read_text())
    for code,h in progress.items():
        if code not in codes or sha256_file(out/'codes'/(code+'.json'))!=h:raise ValueError('capture checkpoint packet changed')
    def load(directory,manifest,code):
        path=directory/'codes'/(code+'.json')
        if sha256_file(path)!=manifest['per_code_sha256'][code]:raise ValueError('immutable source packet changed')
        packet=json.loads(path.read_text())
        if packet['instrument']!=code:raise ValueError('source packet security changed')
        return packet
    pending=[c for c in codes if c not in progress and c not in expected_routes['reuse_full_codes']];bs=None
    if pending:
        import baostock as bs
        socket.setdefaulttimeout(20)
        if bs.login().error_code!='0':raise RuntimeError('raw extension login failed')
    try:
        for index,code in enumerate(codes,1):
            if code in progress:continue
            path=out/'codes'/(code+'.json')
            if path.exists():raise ValueError('uncommitted packet checkpoint; preserve before inspection')
            if code in expected_routes['reuse_full_codes']:
                packet=copy.deepcopy(load(old,om,code));route='IMMUTABLE_FULL_REUSE'
                packet['provenance']={'kind':route,'original_sha256':om['per_code_sha256'][code]}
            elif code in expected_routes['extend_development_codes']:
                packet=append_2026(load(dev,dm,code),fetch_packet(bs,code,FIRST));route='APPEND_2026_ONLY'
                packet['provenance']={'kind':route,'development_sha256':dm['per_code_sha256'][code],'query_start':FIRST,'query_end':END}
            else:
                packet=fetch_packet(bs,code,START);route='NEW_BOUNDED_FULL_CAPTURE'
                packet['provenance']={'kind':route,'query_start':START,'query_end':END}
            if packet['window']!=[START,END] or [r['date'] for r in packet['bars']]!=sessions:raise ValueError('complete raw window required')
            if code in dm['per_code_sha256']:assert_development_prefix(load(dev,dm,code),packet)
            packet['observed_at']=datetime.now(timezone.utc).isoformat();atomic_json(path,packet)
            progress[code]=sha256_file(path);atomic_json(out/'progress.json',progress)
            print(json.dumps({'captured':index,'total':len(codes),'instrument':code,'route':route}),flush=True)
    finally:
        if bs is not None:bs.logout()
    totals={'bars':0,'distributions':0,'adjustments':0,'quarantine':0}
    if set(progress)!=set(codes):raise ValueError('capture incomplete')
    for code in codes:
        path=out/'codes'/(code+'.json');packet=json.loads(path.read_text())
        if sha256_file(path)!=progress[code] or packet['instrument']!=code or packet['window']!=[START,END]:raise ValueError('final source identity changed')
        validate_bars(code,BAR_FIELDS,[[r[k] for k in BAR_FIELDS] for r in packet['bars']])
        if [r['date'] for r in packet['bars']]!=sessions:raise ValueError('final calendar coverage changed')
        if code in dm['per_code_sha256']:assert_development_prefix(load(dev,dm,code),packet)
        for key in totals:totals[key]+=len(packet[key])
    manifest={'status':'SZSE_VALUE_RAW_EXTENSION_CAPTURED','window':[START,END],'names':len(codes),'totals':totals,
        'target_sha256':request['target_sha256'],'request_sha256':args.expected_request_sha256,
        'capture_plan_sha256':args.expected_capture_plan_sha256,'calendar_sha256':sha256_file(out/'calendar.json'),
        'per_code_sha256':progress,'development_prefix_verified_names':len(dm['per_code_sha256']),
        'source':'BaoStock unadjusted daily shares/cash and distributions','source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
        'historical_arrival_verified':False,'complete_requested_October':False,'policy_changed':False,'objective_achieved':False}
    atomic_json(out/'manifest.json',manifest);print('value raw extension complete',len(codes),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
