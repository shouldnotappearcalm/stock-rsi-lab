"""Fixed pre2026 source-only probe; no account replay or policy revision."""
import argparse,csv,hashlib,json,socket,time
from datetime import datetime,timezone,date
from importlib.metadata import version
from pathlib import Path
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,source_code,validate_bars,query_rows

B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
METHOD_FILES=('scripts/capture_high52_unfilled_sources.py','scripts/capture_low_risk_raw_account_data.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py')

def main(argv=None):
 parser=argparse.ArgumentParser()
 for name in ('request','expected-request-sha256','orders','output-dir'):parser.add_argument('--'+name,required=True)
 parser.add_argument('--resume',action='store_true');args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
 if sha256_file(args.request)!=args.expected_request_sha256:raise ValueError('source request changed')
 req=json.loads(Path(args.request).read_text())
 if (req['status']!='FROZEN_HIGH52_UNFILLED_SOURCE_PROBE' or sha256_file(args.orders)!=req['orders_sha256']
     or set(req['method_code_sha256'])!=set(METHOD_FILES)
     or any(sha256_file(root/n)!=h for n,h in req['method_code_sha256'].items())
     or any(version(k)!=v for k,v in req['package_versions'].items())):raise ValueError('source-only method or original orders changed')
 with Path(args.orders).open() as stream:orders=list(csv.DictReader(stream))
 pairs=[[r['instrument'],r['session']] for r in orders if r['side']=='BUY' and r['fill_status']=='UNFILLED']
 if pairs!=req['pairs'] or len(pairs)!=35 or len({tuple(p) for p in pairs})!=35:raise ValueError('exact35 original unfilled pairs required')
 for code,day in pairs:
  source_code(code)
  if not '2024-01-02'<=day<='2025-12-31' or date.fromisoformat(day).isoformat()!=day:raise ValueError('pre2026 source boundary crossed')
 for name,h in req['source_manifest_sha256'].items():
  if Path(name).name!=name or sha256_file(B/name/'manifest.json')!=h:raise ValueError('reused source identity changed')
 fresh_raw=[p for p in pairs if p[0] not in req['raw_routes']]
 fresh_tape=[p for p in pairs if p[0]+'-'+p[1]+'.json' not in req['tape_routes']]
 if fresh_raw!=req['fresh_daily_pairs'] or fresh_tape!=req['fresh_minute_pairs'] or len(fresh_raw)+len(fresh_tape)!=req['new_request_budget']:raise ValueError('source routing or budget changed')
 if args.resume:
  if (out/'request.json').read_bytes()!=Path(args.request).read_bytes():raise ValueError('source checkpoint changed')
 else:
  if out.exists():raise ValueError('source output exists')
  (out/'daily').mkdir(parents=True);(out/'sessions').mkdir();(out/'request.json').write_bytes(Path(args.request).read_bytes());atomic_json(out/'progress.json',{})
 progress=json.loads((out/'progress.json').read_text())
 expected_names={folder+'/'+c+'-'+d+'.json' for c,d in pairs for folder in ('daily','sessions')}
 if not set(progress)<=expected_names:raise ValueError('unknown source checkpoint artifact')
 for name,h in progress.items():
  if sha256_file(out/name)!=h:raise ValueError('captured source changed')
 bs=None;new_calls=0
 if any('daily/'+c+'-'+d+'.json' not in progress for c,d in fresh_raw):
  import baostock as bs
  socket.setdefaulttimeout(20)
  if bs.login().error_code!='0':raise RuntimeError('daily source login failed')
 try:
  for code,day in pairs:
   name='daily/'+code+'-'+day+'.json';path=out/name
   if name in progress:continue
   if path.exists():raise ValueError('preserve uncommitted source packet')
   if code in req['raw_routes']:
    route=req['raw_routes'][code];source=B/route['source']/'codes'/(code+'.json')
    if sha256_file(source)!=route['sha256']:raise ValueError('reused raw packet changed')
    packet=json.loads(source.read_text());rows=[r for r in packet['bars'] if r['date']==day]
    origin={'kind':'IMMUTABLE_SOURCE_ROW_REUSE','source':route['source'],'source_packet_sha256':route['sha256'],
            'original_window':packet['window'],'original_contains_later_bytes':packet['window'][1]>'2025-12-31'}
   else:
    if new_calls>=req['new_request_budget']:raise ValueError('new request budget exhausted')
    new_calls+=1
    fields,raw=query_rows(bs.query_history_k_data_plus(source_code(code),','.join(BAR_FIELDS),start_date=day,end_date=day,frequency='d',adjustflag='3'))
    rows=validate_bars(code,fields,raw);origin={'kind':'BOUNDED_NEW_ONE_DAY_QUERY','query_window':[day,day]}
   if len(rows)!=1 or rows[0]['date']!=day:raise ValueError('exact requested raw day required')
   validate_bars(code,BAR_FIELDS,[[rows[0][k] for k in BAR_FIELDS]])
   atomic_json(path,{'instrument':code,'requested_day':day,'bar':rows[0],'provenance':origin,'captured_at':datetime.now(timezone.utc).isoformat()})
   progress[name]=sha256_file(path);atomic_json(out/'progress.json',progress)
 finally:
  if bs is not None:bs.logout()
 from eltdx import TdxClient,to_jsonable
 with TdxClient(host=req['tdx_host'],timeout=3,heartbeat_interval=None,probe_hosts=False) as client:
  for i,(code,day) in enumerate(pairs,1):
   filename=code+'-'+day+'.json';name='sessions/'+filename;path=out/name
   if name in progress:continue
   if path.exists():raise ValueError('preserve uncommitted minute packet')
   if filename in req['tape_routes']:
    route=req['tape_routes'][filename];source=B/route['source']/'sessions'/filename
    if sha256_file(source)!=route['sha256']:raise ValueError('reused minute bytes changed')
    path.write_bytes(source.read_bytes())
   else:
    if new_calls>=req['new_request_budget']:raise ValueError('new request budget exhausted')
    new_calls+=1
    packet={'instrument':code,'requested_day':day,'request_started_at':datetime.now(timezone.utc).isoformat()}
    try:packet.update(status='RESPONSE_CAPTURED',response=to_jsonable(client.minutes.history(code.lower(),day,include_raw=True)))
    except Exception as exc:packet.update(status='REQUEST_FAILED',error_type=type(exc).__name__,error=str(exc)[:300])
    atomic_json(path,packet);time.sleep(.05)
   packet=json.loads(path.read_text())
   if packet['instrument']!=code or packet['requested_day']!=day:raise ValueError('minute identity changed')
   progress[name]=sha256_file(path);atomic_json(out/'progress.json',progress);print('source pair',i,'/35',flush=True)
 manifest={'status':'HIGH52_UNFILLED_PRE2026_SOURCES_CAPTURED','pairs':35,'request_sha256':args.expected_request_sha256,
  'artifact_sha256':progress,'new_source_requests_this_invocation':new_calls,'per_invocation_new_source_request_budget':req['new_request_budget'],'global_cross_restart_reservations_enforced':False,
  'new_requests_have_pre2026_cutoff':True,'original_vendor_packets_unchanged':True,'2026_strategy_returns_queried':False,
  'historical_arrival_verified':False,'source_capture_is_fill_verification':False,'objective_achieved':False}
 if set(progress)!=expected_names:raise ValueError('incomplete source capture')
 atomic_json(out/'manifest.json',manifest);print('source capture complete',flush=True);return 0
if __name__=='__main__':raise SystemExit(main())
