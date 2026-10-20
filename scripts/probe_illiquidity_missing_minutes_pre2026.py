"""Six frozen source probes only; preserve prior rejected packets and validators."""
import argparse
from decimal import Decimal
import fcntl
from importlib.metadata import version
import json
from pathlib import Path
import socket

from scripts.capture_illiquidity_raw_development import read_vendor_response,unwrap_vendor_response
from scripts.capture_low_risk_execution_tape import FIELDS,validate_minutes
from scripts.fundamental_query_journal import QueryJournal,digest,file_sha,write_packet_once
from scripts.illiquidity_minute_sources import query_minute_packet


def persist_then_logout(journal,identity,fetch,logout):
    try:
        return journal.query(identity,fetch)
    finally:
        # Cleanup happens only after the source response/error has been persisted.
        try:logout()
        except Exception as exc:
            path=journal.root/'queries'/digest(identity)/'logout-error.json'
            write_packet_once(path,{'error_type':type(exc).__name__,'error':str(exc)})


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','raw-data-dir','prior-capture-dir','output-dir'):p.add_argument('--'+n,required=True)
    args=p.parse_args(argv);root=Path(__file__).resolve().parents[1]
    requestfile=Path(args.request)
    if file_sha(requestfile)!=args.expected_request_sha256:raise ValueError('frozen missing-source probe request changed')
    request=json.loads(requestfile.read_text())
    if (request['status']!='FROZEN_SIX_PRE2026_MISSING_SOURCE_PROBES'
            or any(file_sha(root/n)!=h for n,h in request['method_code_sha256'].items())
            or any(version(n)!=v for n,v in request['package_versions'].items())):raise ValueError('probe method or packages changed')
    raw,prior,out=map(Path,(args.raw_data_dir,args.prior_capture_dir,args.output_dir))
    if file_sha(prior/'manifest.json')!=request['prior_capture_manifest_sha256']:raise ValueError('original source capture changed')
    if out.exists():raise ValueError('source probe output already exists')
    pairs=request['missing_pairs'];controls=request['control_pairs']
    if len(pairs)!=2 or len(controls)!=2 or len(request['queries'])!=6:raise ValueError('exact six source queries required')
    daily={}
    for code,day in [*pairs,*controls]:
        path=raw/'codes'/(code+'.json')
        if file_sha(path)!=request['raw_packet_sha256'][code]:raise ValueError('original raw quote packet changed')
        rows=[r for r in json.loads(path.read_text())['bars'] if r['date']==day]
        if len(rows)!=1 or rows[0]['tradestatus']!='1':raise ValueError('active explicit reference session required')
        if not '2024-01-02'<=day<='2025-12-31':raise ValueError('future source probe forbidden')
        daily[(code,day)]=rows[0]
    for code,day in pairs:
        path=prior/'sessions'/(code+'-'+day+'.json')
        if file_sha(path)!=request['original_failure_sha256'][code+'|'+day]:raise ValueError('original minute failure changed')
    out.mkdir(parents=True);socket.setdefaulttimeout(20);results=[]
    with (out/'capture.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);journal=QueryJournal(out,max_queries=6,max_attempts=1)
        for item in request['queries']:
            method,code,day=item['method'],item['instrument'],item['day']
            row={'method':method,'instrument':code,'day':day,'role':item['role']}
            if method=='minutes.history':
                def fetch():
                    from eltdx import TdxClient,to_jsonable
                    with TdxClient(host=item['host'],timeout=3,heartbeat_interval=None,probe_hosts=False,
                        pool_size=1,server_count=1,connections_per_server=1) as client:
                        return to_jsonable(client.minutes.history(code.lower(),day,include_raw=True))
                packet=query_minute_packet(journal,code,day,item['host'],fetch)
                row.update(status=packet['status'],error=packet.get('error'),host=item['host'])
            elif method=='query_history_k_data_plus':
                identity={'method':method,'instrument':code,'day':day,'frequency':'5','adjustflag':'3','fields':list(FIELDS)}
                import baostock as bs
                def fetch_bao():
                    if bs.login().error_code!='0':raise RuntimeError('source login failed')
                    return read_vendor_response(bs.query_history_k_data_plus(code[:2].lower()+'.'+code[2:],','.join(FIELDS),
                        start_date=day,end_date=day,frequency='5',adjustflag='3'))
                try:
                    payload,receipt=persist_then_logout(journal,identity,fetch_bao,bs.logout)
                    packet={'instrument':code,'requested_day':day,'status':'PROVIDER_ENVELOPE_CAPTURED','payload':payload,'query_receipt':receipt}
                    decoded=unwrap_vendor_response(payload);rows,complete=validate_minutes(code,day,decoded['fields'],decoded['rows'])
                    ref=daily[(code,day)]
                    checks={'complete_48_labels':complete,'first_open_matches':bool(rows) and Decimal(rows[0]['open'])==Decimal(ref['open']),
                        'highest_matches':bool(rows) and max(Decimal(r['high']) for r in rows)==Decimal(ref['high']),
                        'lowest_matches':bool(rows) and min(Decimal(r['low']) for r in rows)==Decimal(ref['low']),
                        'last_close_matches':bool(rows) and Decimal(rows[-1]['close'])==Decimal(ref['close']),
                        'total_volume_matches':bool(rows) and sum(Decimal(r['volume']) for r in rows)==Decimal(ref['volume'])}
                    row.update(status='RESPONSE_CAPTURED',source_checks=checks,strict_reported_5min_OHLCV_check_passes=all(checks.values()),
                        total_5min_volume=str(sum(Decimal(r['volume']) for r in rows)),daily_volume=ref['volume'])
                except (ValueError,RuntimeError,KeyError) as exc:
                    packet={'instrument':code,'requested_day':day,'status':'SOURCE_OR_VALIDATION_FAILED','error_type':type(exc).__name__,'error':str(exc)}
                    row.update(status=packet['status'],error=packet['error'],strict_reported_5min_OHLCV_check_passes=False)
            else:raise ValueError('unregistered source endpoint')
            filename=str(len(results)+1)+'.json';write_packet_once(out/filename,packet)
            row.update(file=filename,sha256=file_sha(out/filename));results.append(row);print(json.dumps(row),flush=True)
        result={'status':'ILLIQUIDITY_SIX_PRE2026_SOURCE_PROBES_COMPLETE','request_sha256':file_sha(requestfile),
            'prior_capture_manifest_sha256':file_sha(prior/'manifest.json'),'results':results,
            'query_reservations':len(list((out/'queries').glob('*/reserved-*.json'))),
            'query_responses_preserved':len(list((out/'queries').glob('*/response-*.json'))),
            'query_artifact_sha256':{str(p.relative_to(out)):file_sha(p) for p in sorted((out/'queries').rglob('*.json'))},
            'previous_source_packets_modified':False,'five_minute_validator_or_criteria_changed':False,
            'one_minute_series_created':False,'source_is_a_fill_verification':False,'admitted_for_reconstructed_execution':False,
            'portfolio_returns_computed':False,'2026_market_values_queried':False,'objective_achieved':False}
        write_packet_once(out/'manifest.json',result);print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
