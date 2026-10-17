"""Raw inputs for a frozen development lead; every new query ends in 2025.

Existing immutable packets can be explicitly reused after clipping. Their
original hashes and later-byte provenance are preserved, never called PIT.
"""
import argparse
import copy
import json
import math
import socket
from datetime import date,datetime,timezone
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_low_risk_raw_account_data import (
    BAR_FIELDS,DIVIDEND_FIELDS,ADJUST_FIELDS,source_code,validate_bars,validate_dividends,query_rows,
)

START,END='2023-12-29','2025-12-31'


def target_codes(targets):
    if not isinstance(targets,dict) or not targets:raise ValueError('nonempty frozen targets required')
    codes=set()
    for day,payload in targets.items():
        if not '2024-01-02'<=day<=END or date.fromisoformat(day).isoformat()!=day:
            raise ValueError('capture target outside development cutoff')
        prior=payload['as_of'];weights=payload['weights']
        if not START<=prior<day or date.fromisoformat(prior).isoformat()!=prior or not weights:
            raise ValueError('target must be visible before execution')
        if any(type(w) not in (int,float) or not math.isfinite(w) or w<=0 for w in weights.values()) or math.fsum(weights.values())>1+1e-10:
            raise ValueError('positive long-only target weights required')
        for code in weights:source_code(code);codes.add(code)
    return sorted(codes)


def clipped_packet(packet):
    result={'instrument':packet['instrument'],'window':[START,END]}
    for key,field in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        result[key]=copy.deepcopy([row for row in packet[key] if START<=row[field]<=END])
    result['quarantine']=copy.deepcopy([row for row in packet['quarantine']
        if not row['record'].get('dividOperateDate') or START<=row['record']['dividOperateDate']<=END])
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','targets','reuse-dir','output-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args(argv)
    if sha256_file(args.request)!=args.expected_request_sha256:raise ValueError('capture request changed')
    request=json.loads(Path(args.request).read_text());reuse=Path(args.reuse_dir);out=Path(args.output_dir)
    if (request['window']!=[START,END] or request['capture_code_sha256']!=sha256_file(__file__)
            or request['shared_validation_sha256']!=sha256_file(Path(__file__).with_name('capture_low_risk_raw_account_data.py'))
            or sha256_file(args.targets)!=request['target_sha256']
            or sha256_file(reuse/'manifest.json')!=request['reuse_manifest_sha256']):raise ValueError('frozen input or capture method changed')
    codes=target_codes(json.loads(Path(args.targets).read_text()))
    if codes!=request['codes']:raise ValueError('capture universe changed')
    old=json.loads((reuse/'manifest.json').read_text())
    if sha256_file(reuse/'calendar.json')!=old['calendar_sha256']:raise ValueError('reused calendar changed')
    calendar=json.loads((reuse/'calendar.json').read_text())
    sessions=[day for day in calendar['sessions'] if START<=day<=END]
    if sessions[0]!=START or sessions[-1]!=END:raise ValueError('complete explicit development calendar required')
    expected_calendar={'sessions':sessions,'origin_sha256':old['calendar_sha256'],'clipped_to':[START,END]}
    if args.resume:
        if (out/'request.json').read_bytes()!=Path(args.request).read_bytes():raise ValueError('capture checkpoint request changed')
        if not (out/'calendar.json').is_file() or json.loads((out/'calendar.json').read_text())!=expected_calendar:
            raise ValueError('capture checkpoint calendar changed')
    else:
        if out.exists():raise ValueError('capture output already exists')
        (out/'codes').mkdir(parents=True);(out/'request.json').write_bytes(Path(args.request).read_bytes())
        atomic_json(out/'calendar.json',expected_calendar)
        atomic_json(out/'progress.json',{})
    progress=json.loads((out/'progress.json').read_text())
    for code,expected in progress.items():
        if code not in codes or sha256_file(out/'codes'/(code+'.json'))!=expected:raise ValueError('capture checkpoint bytes changed')
    fresh=[code for code in codes if code not in old['per_code_sha256'] and code not in progress]
    bs=None
    if fresh:
        import baostock as bs
        socket.setdefaulttimeout(20)
        login=bs.login()
        if login.error_code!='0':raise RuntimeError('raw development login failed')
    try:
        for index,code in enumerate(codes,1):
            if code in progress:continue
            path=out/'codes'/(code+'.json')
            if path.exists():raise ValueError('uncommitted capture checkpoint; preserve and inspect before retry')
            if code in old['per_code_sha256']:
                original=reuse/'codes'/(code+'.json');expected=old['per_code_sha256'][code]
                if sha256_file(original)!=expected:raise ValueError('reused security packet changed')
                saved=json.loads(original.read_text())
                if saved['instrument']!=code:raise ValueError('reused source identity changed')
                packet=clipped_packet(saved)
                packet['provenance']={'kind':'EXPLICIT_CLIPPED_REUSE','original_sha256':expected,
                    'original_window':saved['window'],'source_contains_later_bytes':saved['window'][1]>END}
            else:
                symbol=source_code(code)
                fields,rows=query_rows(bs.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),start_date=START,end_date=END,frequency='d',adjustflag='3'))
                bars=validate_bars(code,fields,rows)
                if any(row['date']>END for row in bars):raise ValueError('provider crossed development cutoff')
                distributions=[];quarantine=[]
                for year in (2024,2025):
                    fields,rows=query_rows(bs.query_dividend_data(symbol,year=str(year),yearType='operate'))
                    accepted,excluded=validate_dividends(code,fields,rows,year)
                    if any(row['dividOperateDate']>END for row in accepted):raise ValueError('future development distribution')
                    distributions.extend(accepted);quarantine.extend(excluded)
                fields,rows=query_rows(bs.query_adjust_factor(symbol,start_date=START,end_date=END))
                if tuple(fields)!=ADJUST_FIELDS:raise ValueError('corporate adjustment schema changed')
                adjustments=[dict(zip(fields,row)) for row in rows]
                if any(r['code']!=symbol or not START<=r['dividOperateDate']<=END for r in adjustments):raise ValueError('adjustment outside development cutoff')
                packet={'instrument':code,'window':[START,END],'bars':bars,'distributions':distributions,
                    'quarantine':quarantine,'adjustments':adjustments,'provenance':{'kind':'NEW_CUTOFF_BOUNDED_QUERY',
                    'observed_at':datetime.now(timezone.utc).isoformat(),'query_end':END}}
            # Calendar and schema admission is complete before checkpointing either route.
            validate_bars(code,BAR_FIELDS,[[r[k] for k in BAR_FIELDS] for r in packet['bars']])
            if [r['date'] for r in packet['bars']]!=sessions:raise ValueError('raw security calendar coverage incomplete')
            atomic_json(path,packet);progress[code]=sha256_file(path);atomic_json(out/'progress.json',progress)
            print(json.dumps({'captured':index,'total':len(codes),'instrument':code,'route':packet['provenance']['kind']}),flush=True)
    finally:
        if bs is not None:bs.logout()
    assert set(progress)==set(codes)
    totals={'bar_rows':0,'distributions':0,'adjustments':0,'quarantines':0}
    for code in codes:
        packet=json.loads((out/'codes'/(code+'.json')).read_text())
        for key,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):
            totals[key]+=len(packet[field])
    manifest={'status':'FROZEN_TARGET_DEVELOPMENT_INPUTS_CAPTURED','window':[START,END],'names':len(codes),
        'request_sha256':args.expected_request_sha256,'target_sha256':request['target_sha256'],
        'capture_code_sha256':request['capture_code_sha256'],'calendar_sha256':sha256_file(out/'calendar.json'),
        'per_code_sha256':progress,'totals':totals,'source':'BaoStock unadjusted daily shares/cash and distributions',
        'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
        'new_2026_market_queries':False,'reused_original_cache_may_contain_later_bytes':True,
        'decision_data_clipped_before_2026':True,'historical_arrival_verified':False,'objective_achieved':False}
    atomic_json(out/'manifest.json',manifest);print('development raw capture complete',len(codes),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
