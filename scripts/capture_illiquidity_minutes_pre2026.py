"""Capture a frozen source-only minute request with immutable query reservations."""
import argparse
import fcntl
from importlib.metadata import version
import json
from pathlib import Path
import time

from scripts.fundamental_query_journal import QueryJournal,file_sha,write_packet_once
from scripts.illiquidity_minute_sources import authenticate_reused_minutes,prefix_minute_requirements,query_minute_packet
from scripts.prepare_illiquidity_account_events import authenticate_sources


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('base-dir','raw-data-dir','proof-dir','targets','request','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1]
    planfile,requestfile=map(Path,(args.plan,args.request))
    if file_sha(planfile)!=args.expected_plan_sha256:raise ValueError('frozen minute capture plan changed')
    plan=json.loads(planfile.read_text());request=json.loads(requestfile.read_text())
    if (plan['status']!='FROZEN_ILLIQUIDITY_PRE2026_MINUTE_SOURCE_CAPTURE'
            or file_sha(requestfile)!=plan['request_sha256'] or version('eltdx')!=plan['package_version']
            or any(file_sha(root/n)!=v for n,v in plan['method_code_sha256'].items())):
        raise ValueError('frozen capture method, SDK or request changed')
    base,raw,proofdir,targetsfile,out=map(Path,(args.base_dir,args.raw_data_dir,args.proof_dir,args.targets,args.output_dir))
    packets,proof,calendar=authenticate_sources(raw,proofdir,targetsfile,root)
    if (file_sha(raw/'manifest.json')!=plan['raw_manifest_sha256']
            or file_sha(proofdir/'reviewed-manifest.json')!=plan['proof_manifest_sha256']
            or file_sha(targetsfile)!=request['target_sha256']):raise ValueError('source provenance changed')
    bars={c:{r['date']:r for r in p['bars']} for c,p in packets.items()}
    active,skipped=prefix_minute_requirements(json.loads(targetsfile.read_text()),bars,proof['lifecycles'])
    if active!=request['active_requests'] or skipped!=request['nonexecuting_source_intervals']:
        raise ValueError('complete frozen minute prefix differs')
    index={};primary=None
    for name,expected in request['source_manifest_sha256'].items():
        if Path(name).name!=name or file_sha(base/name/'manifest.json')!=expected:raise ValueError('reusable source manifest changed')
        m=json.loads((base/name/'manifest.json').read_text())
        if name==request['primary_tape_root']:primary=set(m['per_session_sha256'])
        for filename,h in m['per_session_sha256'].items():
            if Path(filename).name!=filename:raise ValueError('unsafe minute source filename')
            index.setdefault(filename,{'root':name,'sha256':h})
    if primary is None:raise ValueError('primary tape source absent')
    authenticated_reuse=authenticate_reused_minutes(base,index,active)
    supplemental=[p for p in active if p[0]+'-'+p[1]+'.json' not in primary]
    fresh=[p for p in supplemental if p[0]+'-'+p[1]+'.json' not in index]
    if supplemental!=request['supplemental_requests'] or fresh!=request['fresh_requests'] or plan['max_fresh_query_reservations']!=len(fresh):
        raise ValueError('source query budget or reusable prefix changed')
    if not out.exists():out.mkdir(parents=True)
    with (out/'capture.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        write_packet_once(out/'plan.json',plan);(out/'sessions').mkdir(exist_ok=True)
        journal=QueryJournal(out,max_queries=len(fresh),max_attempts=1)
        hashes={};origins={};stop=False;consecutive=0;clients=[]
        try:
            # Reuse source bytes before starting any fresh request, including failed responses.
            for code,day in supplemental:
                name=code+'-'+day+'.json'
                if name not in index:continue
                origin=index[name];source=base/origin['root']/'sessions'/name
                if file_sha(source)!=origin['sha256']:raise ValueError('reused minute packet changed')
                path=out/'sessions'/name
                if not path.exists():path.write_bytes(source.read_bytes())
                if file_sha(path)!=origin['sha256']:raise ValueError('reused bytes differ')
                packet=json.loads(path.read_text())
                if packet['instrument']!=code or packet['requested_day']!=day:raise ValueError('reused minute identity changed')
                hashes[name]=file_sha(path);origins[name]=origin
            for number,(code,day) in enumerate(fresh,1):
                def fetch():
                    from eltdx import TdxClient,to_jsonable
                    if not clients:
                        client=TdxClient(host=plan['host'],timeout=plan['timeout_seconds'],heartbeat_interval=None,
                            probe_hosts=False,pool_size=1,server_count=1,connections_per_server=1)
                        try:client.__enter__()
                        except Exception:
                            client.close();raise
                        clients.append(client)
                    return to_jsonable(clients[0].minutes.history(code.lower(),day,include_raw=True))
                packet=query_minute_packet(journal,code,day,plan['host'],fetch)
                path=out/'sessions'/(code+'-'+day+'.json');write_packet_once(path,packet);hashes[path.name]=file_sha(path)
                consecutive=consecutive+1 if packet['status']=='REQUEST_FAILED' else 0
                if number%25==0 or number==len(fresh):
                    print(json.dumps({'fresh_captured':number,'fresh_total':len(fresh),'reused':len(origins),
                        'instrument':code,'day':day,'status':packet['status']}),flush=True)
                if consecutive>=plan['stop_after_consecutive_source_failures']:
                    stop=True;break
                time.sleep(plan['inter_query_delay_seconds'])
        finally:
            for client in clients:client.close()
        reservations=list((out/'queries').glob('*/reserved-*.json'))
        responses=list((out/'queries').glob('*/response-*.json'))
        statuses={}
        for name in hashes:
            p=json.loads((out/'sessions'/name).read_text());record=p.get('methods',{}).get('minutes.history',p)
            statuses[record['status']]=statuses.get(record['status'],0)+1
        manifest={'status':'ILLIQUIDITY_PRE2026_MINUTE_SOURCE_CAPTURE_RECORDED',
            'plan_sha256':file_sha(out/'plan.json'),'request_sha256':file_sha(requestfile),
            'requested':len(supplemental),'captured':len(hashes),'per_session_sha256':dict(sorted(hashes.items())),
            'reused_session_provenance':origins,'all_reused_source_bytes_preserved':True,
            'active_reused_packets_authenticated_upfront':len(authenticated_reuse),
            'fresh_query_reservations':len(reservations),'fresh_query_responses_preserved':len(responses),
            'response_status_counts':statuses,'stopped_after_consecutive_source_failures':stop,
            'complete_capture':len(hashes)==len(supplemental),'new_2026_queries':False,
            'historical_arrival_verified':False,'admitted_for_reconstructed_execution':False,
            'portfolio_returns_computed':False,'objective_achieved':False}
        write_packet_once(out/('capture-snapshot-'+str(len(hashes))+'.json'),manifest)
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({k:v for k,v in manifest.items() if k not in ('per_session_sha256','reused_session_provenance')},indent=2),flush=True)


if __name__=='__main__':main()
