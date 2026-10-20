"""Bounded pre2026 source capture; no account engine or outcome query."""
import argparse,fcntl,json,re,time
from collections import Counter
from datetime import date
from importlib.metadata import version
from pathlib import Path
from scripts.fundamental_query_journal import QueryJournal,digest,file_sha,write_packet_once
from scripts.illiquidity_minute_sources import authenticate_reused_minutes,prefix_minute_requirements,query_minute_packet

METHOD_FILES=('scripts/capture_low_beta60_minutes_pre2026.py','scripts/fundamental_query_journal.py',
 'scripts/illiquidity_minute_sources.py','src/stock_rsi/lifecycle_source_rows.py',
 'src/stock_rsi/data.py','src/stock_rsi/calendar.py','src/stock_rsi/time.py')


def valid_pair(code,day):
    try:ok=re.fullmatch('(SH|SZ)[0-9]{6}',code) and date.fromisoformat(day).isoformat()==day and '2024-01-02'<=day<='2025-12-31'
    except (TypeError,ValueError):ok=False
    if not ok:raise ValueError('canonical pre2026 minute identity required')


def capture_prefix(base,out,reused,fresh,plan,fetch):
    """Caller owns a process lock; fetch(code,day) performs one source call."""
    base,out=Path(base),Path(out);names=[]
    for code,day in fresh:valid_pair(code,day);names.append(code+'-'+day+'.json')
    if (len(names)!=len(set(names)) or set(names)&set(reused)
            or plan['max_fresh_query_reservations']!=len(fresh) or not fresh
            or plan['max_attempts_per_request']!=1 or plan['stop_after_consecutive_source_failures']!=3
            or not 0<=plan['inter_query_delay_seconds']<=1):raise ValueError('frozen unique identities or bounded profile changed')
    for name,origin in reused.items():
        if Path(name).name!=name or not name.endswith('.json') or Path(origin['root']).name!=origin['root']:
            raise ValueError('safe reused minute path required')
        code,day=name[:-5].split('-',1);valid_pair(code,day)
    pairs=[name[:-5].split('-',1) for name in reused]
    authenticate_reused_minutes(base,reused,pairs)
    out.mkdir(parents=True,exist_ok=True);(out/'sessions').mkdir(exist_ok=True)
    write_packet_once(out/'plan.json',plan)
    write_packet_once(out/'capture_request.json',{'reused':reused,'fresh':fresh})
    journal=QueryJournal(out,max_queries=len(fresh),max_attempts=1)
    hashes={};stop=False;consecutive=0;abnormal=None
    try:
        for name,origin in reused.items():
            source=base/origin['root']/'sessions'/name;dest=out/'sessions'/name
            if not dest.exists():
                with dest.open('xb') as stream:stream.write(source.read_bytes())
            if file_sha(dest)!=origin['sha256']:raise ValueError('reused minute output bytes changed')
            hashes[name]=file_sha(dest)
        for number,(code,day) in enumerate(fresh,1):
            packet=query_minute_packet(journal,code,day,plan['host'],lambda:fetch(code,day))
            path=out/'sessions'/(code+'-'+day+'.json');write_packet_once(path,packet);hashes[path.name]=file_sha(path)
            consecutive=consecutive+1 if packet['status']=='REQUEST_FAILED' else 0
            if number%25==0 or number==len(fresh):print('lowbeta minutes fresh',number,'/',len(fresh),code,day,packet['status'],flush=True)
            if consecutive>=3:stop=True;break
            if plan['inter_query_delay_seconds']:time.sleep(plan['inter_query_delay_seconds'])
    except BaseException as exc:
        abnormal={'type':type(exc).__name__,'message':str(exc)};raise
    finally:
        statuses=Counter()
        for name in hashes:
            packet=json.loads((out/'sessions'/name).read_text());record=packet.get('methods',{}).get('minutes.history',packet)
            statuses[record['status']]+=1
        manifest={'status':'LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED','plan_sha256':file_sha(out/'plan.json'),
            'capture_request_sha256':file_sha(out/'capture_request.json'),'requested':len(reused)+len(fresh),'captured':len(hashes),
            'per_session_sha256':dict(sorted(hashes.items())),'reused_session_provenance':reused,
            'active_reused_packets_authenticated_upfront':len(reused),
            'fresh_query_reservations':len(list((out/'queries').glob('*/reserved-*.json'))),
            'fresh_query_responses_preserved':len(list((out/'queries').glob('*/response-*.json'))),
            'response_status_counts':dict(statuses),'stopped_after_consecutive_source_failures':stop,
            'abnormal_exit':abnormal,'complete_capture':len(hashes)==len(reused)+len(fresh),
            'new_2026_queries':False,'historical_arrival_verified':False,
            'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
        write_packet_once(out/('capture-snapshot-'+digest(manifest)+'.json'),manifest)
        temporary=out/'manifest.json.tmp';temporary.write_text(json.dumps(manifest,indent=2)+'\n');temporary.replace(out/'manifest.json')
    return manifest


def authenticate(base,repo,request,plan):
    if (plan['status']!='FROZEN_LOW_BETA60_PRE2026_MINUTE_SOURCE_CAPTURE'
            or plan['max_fresh_query_reservations']!=493 or plan['max_attempts_per_request']!=1
            or plan['stop_after_consecutive_source_failures']!=3 or plan['inter_query_delay_seconds']!=.05
            or plan['host']!='116.205.183.150:7709' or plan['timeout_seconds']!=3
            or plan['package_version']!='3.2.3' or version('eltdx')!=plan['package_version']
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)):
        raise ValueError('frozen capture method or installed SDK changed')
    for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for n,h in plan[field].items():
            if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(parent/n)!=h:raise ValueError('source/method evidence changed')
    raw=base/'low-beta60-raw-dev-20261021';m=json.loads((raw/'manifest.json').read_text())
    if file_sha(raw/'manifest.json')!=request['raw_manifest_sha256'] or file_sha(raw/'calendar.json')!=m['calendar_sha256']:
        raise ValueError('raw source/calendar changed')
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=['2023-12-29','2025-12-31']:
        raise ValueError('complete pre2026 raw calendar required')
    bars={}
    for code,h in m['per_code_sha256'].items():
        f=raw/'codes'/(code+'.json')
        if file_sha(f)!=h:raise ValueError('raw packet changed')
        v=json.loads(f.read_text())
        if v['instrument']!=code or [r['date'] for r in v['bars']]!=sessions:raise ValueError('source date identity changed')
        bars[code]={r['date']:r for r in v['bars']}
    tf=base/'low-beta60-pre2026-formations-20261021/targets.json'
    if file_sha(tf)!=request['target_sha256'] or file_sha(tf)!=m['target_sha256']:raise ValueError('original targets changed')
    targets=json.loads(tf.read_text())['low_beta60'];active,skipped=prefix_minute_requirements(targets,bars,{})
    if active!=request['active_requests'] or skipped!=request['nonexecuting_source_intervals'] or len(active)!=1332:
        raise ValueError('complete original source prefix changed')
    index={}
    for name,h in request['source_manifest_sha256'].items():
        if Path(name).name!=name or file_sha(base/name/'manifest.json')!=h:raise ValueError('cached source manifest changed')
        for fn,hh in json.loads((base/name/'manifest.json').read_text())['per_session_sha256'].items():
            if Path(fn).name!=fn:raise ValueError('unsafe minute index name')
            index.setdefault(fn,{'root':name,'sha256':hh})
    reused={c+'-'+d+'.json':index[c+'-'+d+'.json'] for c,d in active if c+'-'+d+'.json' in index}
    fresh=[[c,d] for c,d in active if c+'-'+d+'.json' not in index]
    if reused!=request['reused_session_provenance'] or fresh!=request['uncached_requests'] or len(reused)!=839 or len(fresh)!=493:
        raise ValueError('frozen cached/fresh partition changed')
    authenticate_reused_minutes(base,reused,active)
    return reused,fresh


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','request','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen capture plan changed')
    plan=json.loads(Path(a.plan).read_text());request=json.loads(Path(a.request).read_text())
    if file_sha(a.request)!=plan['request_sha256']:raise ValueError('frozen gap identities changed')
    reused,fresh=authenticate(base,repo,request,plan);clients=[]
    def fetch(code,day):
        from eltdx import TdxClient,to_jsonable
        if not clients:
            client=TdxClient(host=plan['host'],timeout=3,heartbeat_interval=None,probe_hosts=False,
                pool_size=1,server_count=1,connections_per_server=1)
            try:client.__enter__()
            except BaseException:client.close();raise
            clients.append(client)
        return to_jsonable(clients[0].minutes.history(code.lower(),day,include_raw=True))
    out.mkdir(parents=True,exist_ok=True)
    try:
        with (out/'capture.lock').open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            write_packet_once(out/'request.json',request)
            manifest=capture_prefix(base,out,reused,fresh,plan,fetch)
    finally:
        for client in clients:client.close()
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('per_session_sha256','reused_session_provenance')},indent=2),flush=True)
    return 0 if manifest['complete_capture'] else 2


if __name__=='__main__':raise SystemExit(main())
