"""Local-only admission of a complete historical minute source prefix."""
import argparse,json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from scripts.capture_low_beta60_minutes_pre2026 import METHOD_FILES as CAPTURE_METHODS,authenticate,valid_pair
from scripts.fundamental_query_journal import digest,file_sha
from scripts.tdx_history_checks import inspect_minutes
from stock_rsi.intraday_tape import aggregate_minutes

METHOD_FILES=tuple(dict.fromkeys((*CAPTURE_METHODS,'scripts/admit_low_beta60_minutes_pre2026.py',
 'scripts/tdx_history_checks.py','src/stock_rsi/intraday_tape.py')))


def inspect_packet(code,day,packet,daily):
    valid_pair(code,day)
    if (packet['instrument']!=code or packet['requested_day']!=day or daily['date']!=day
            or daily['tradestatus']!='1' or daily['isST']!='0'):
        raise ValueError('source security/date/ordinary active state changed')
    record=packet.get('methods',{}).get('minutes.history',packet)
    if record['status']!='RESPONSE_CAPTURED':raise ValueError('historical minute source unavailable')
    facts=inspect_minutes(code,day,record['response'],daily)
    if not facts['last_close_matches'] or facts['traded_points_outside_daily_range']:
        raise ValueError('historical minute price signature conflicts with raw day')
    windows=aggregate_minutes(code,date.fromisoformat(day),record['response']['points'])
    lower=sum(w['volume_lower_shares'] for w in windows);volume=Decimal(daily['volume'])
    if not volume.is_finite() or volume<=0 or volume!=int(volume) or lower>volume:
        raise ValueError('stressed minute volume exceeds valid whole-day source')
    return {'status':'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE','windows':len(windows),
        'facts':facts,'stressed_volume_lower_shares':lower}


def verify_query_receipt(root,code,day,packet,host):
    valid_pair(code,day)
    identity={'method':'minutes.history','instrument':code,'requested_day':day,'host':host,'include_raw':True}
    key=digest(identity);folder=Path(root)/'queries'/key
    request=json.loads((folder/'request.json').read_text());reservation=json.loads((folder/'reserved-1.json').read_text())
    responsefile=folder/'response-1.json';response=json.loads(responsefile.read_text())
    if (request!=identity or reservation['identity_sha256']!=key or reservation['attempt']!=1
            or response['identity_sha256']!=key or response['reservation_sha256']!=file_sha(folder/'reserved-1.json')
            or packet['instrument']!=code or packet['requested_day']!=day
            or packet['query_reservation_sha256']!=file_sha(folder/'reserved-1.json')
            or packet['query_response_sha256']!=file_sha(responsefile)):
        raise ValueError('fresh minute request/reservation/response receipt changed')
    if response['status']=='CAPTURED':
        payload=response['payload']
        if (packet['status']!='RESPONSE_CAPTURED' or digest(payload)!=response['payload_sha256']
                or payload['fields']!=['response'] or payload['rows']!=[packet['response']]
                or packet['observed_at']!=payload['captured_at_utc']):raise ValueError('fresh decoded packet differs from immutable source response')
    elif response['status']=='SOURCE_ERROR':
        if (packet['status']!='REQUEST_FAILED' or packet['error_type']!=response['error_type']
                or packet['error']!=response['error']):raise ValueError('source failure receipt changed')
    else:raise ValueError('unknown immutable query response status')


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','capture-dir','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);capture=Path(a.capture_dir);out=Path(a.output_dir);repo=Path(__file__).resolve().parents[1]
    if out.exists():raise ValueError('preserve prior minute source admission')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen admission plan changed')
    plan=json.loads(Path(a.plan).read_text())
    if plan['status']!='FROZEN_LOW_BETA60_COMPLETE_MINUTE_SOURCE_ADMISSION' or set(plan['method_code_sha256'])!=set(METHOD_FILES):
        raise ValueError('source-only admission method changed')
    for name,h in plan['method_code_sha256'].items():
        if file_sha(repo/name)!=h:raise ValueError('minute source admission code changed')
    for name,h in plan['public_evidence_sha256'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(repo/name)!=h:raise ValueError('frozen public source evidence changed')
    cp=repo/'experiments/qlib/low-beta60-minute-capture-plan.json';rq=repo/'experiments/qlib/low-beta60-minute-gap-identities.json'
    if (file_sha(cp)!=plan['capture_plan_sha256'] or file_sha(capture/'plan.json')!=file_sha(cp)
            or file_sha(rq)!=plan['request_sha256'] or file_sha(capture/'request.json')!=file_sha(rq)
            or file_sha(capture/'manifest.json')!=plan['capture_manifest_sha256']):raise ValueError('actual capture identity changed')
    capture_plan=json.loads(cp.read_text());request=json.loads(rq.read_text());manifest=json.loads((capture/'manifest.json').read_text())
    reused,fresh=authenticate(base,repo,request,capture_plan)
    config={'reused':reused,'fresh':fresh}
    if (json.loads((capture/'capture_request.json').read_text())!=config
            or manifest['plan_sha256']!=file_sha(cp) or manifest['capture_request_sha256']!=file_sha(capture/'capture_request.json')
            or manifest['requested']!=1332 or manifest['captured']!=len(manifest['per_session_sha256'])
            or manifest['reused_session_provenance']!=reused):raise ValueError('capture partition/manifest changed')
    expected={c+'-'+d+'.json' for c,d in request['active_requests']}
    if not set(manifest['per_session_sha256'])<=expected:raise ValueError('unexpected/future captured session')
    raw=base/'low-beta60-raw-dev-20261021';m=json.loads((raw/'manifest.json').read_text())
    bars={c:{r['date']:r for r in json.loads((raw/'codes'/(c+'.json')).read_text())['bars']} for c in m['per_code_sha256']}
    reservations=list((capture/'queries').glob('*/reserved-*.json'));responses=list((capture/'queries').glob('*/response-*.json'))
    keys={digest({'method':'minutes.history','instrument':c,'requested_day':d,'host':capture_plan['host'],'include_raw':True}) for c,d in fresh}
    if (len(reservations)!=manifest['fresh_query_reservations'] or len(responses)!=manifest['fresh_query_responses_preserved']
            or len(reservations)>493 or any(f.name!='reserved-1.json' or f.parent.name not in keys for f in reservations)
            or any(f.name!='response-1.json' or f.parent.name not in keys for f in responses)):
        raise ValueError('cross-restart logical query budget/identities changed')
    rows=[];captured_status=Counter()
    for code,day in request['active_requests']:
        name=code+'-'+day+'.json';row={'instrument':code,'day':day}
        if name not in manifest['per_session_sha256']:row['status']='SOURCE_NOT_CAPTURED';rows.append(row);continue
        f=capture/'sessions'/name;h=manifest['per_session_sha256'][name]
        if file_sha(f)!=h:raise ValueError('captured minute packet bytes changed')
        packet=json.loads(f.read_text());record=packet.get('methods',{}).get('minutes.history',packet)
        captured_status[record['status']]+=1;row['source_sha256']=h
        if name in reused:
            origin=reused[name]
            if h!=origin['sha256'] or file_sha(base/origin['root']/'sessions'/name)!=h:raise ValueError('reused source bytes changed')
            row['origin']=origin
        else:verify_query_receipt(capture,code,day,packet,capture_plan['host']);row['origin']='FROZEN_FRESH_QUERY'
        try:row.update(inspect_packet(code,day,packet,bars[code][day]))
        except (ValueError,KeyError,ArithmeticError) as exc:row.update(status='SOURCE_REJECTED',error_type=type(exc).__name__,error=str(exc))
        rows.append(row)
    if dict(captured_status)!=manifest['response_status_counts']:raise ValueError('source response status count changed')
    counts=dict(Counter(r['status'] for r in rows));passed=(counts=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1332}
        and manifest['complete_capture'] is True and manifest['abnormal_exit'] is None
        and len(reservations)==len(responses)==493 and not manifest['stopped_after_consecutive_source_failures'])
    out.mkdir(parents=True);(out/'details.json').write_text(json.dumps({'sessions':rows,'nonexecuting_source_intervals':request['nonexecuting_source_intervals']},indent=2)+'\n')
    result={'status':'LOW_BETA60_PRE2026_MINUTE_SOURCE_ADMISSION_COMPLETE','plan_sha256':a.expected_plan_sha256,
        'method_code_sha256':plan['method_code_sha256'],'capture_plan_sha256':file_sha(cp),'capture_manifest_sha256':file_sha(capture/'manifest.json'),
        'request_sha256':file_sha(rq),'raw_manifest_sha256':file_sha(raw/'manifest.json'),'target_sha256':request['target_sha256'],
        'required_active_sessions':1332,'nonexecuting_source_intervals':len(request['nonexecuting_source_intervals']),
        'status_counts':counts,'fresh_reservations':len(reservations),'fresh_responses':len(responses),'reused_packets':len(reused),
        'admitted_for_reconstructed_execution':passed,'details_sha256':file_sha(out/'details.json'),
        'exact_share_total_matches':sum(r.get('facts',{}).get('exact_total_shares_match') is True for r in rows),
        'exact_share_precision_certified':False,'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,
        'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,'portfolio_returns_computed':False,
        'new_2026_market_values_queried':False,'candidate_promoted':False,'objective_achieved':False,
        'exceptions':[r for r in rows if r['status']!='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE']}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('method_code_sha256','exceptions')},indent=2),flush=True)
    return 0 if passed else 2


if __name__=='__main__':raise SystemExit(main())
