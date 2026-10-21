"""One bounded price-delay capture; reuse original journal/helper without changes."""
import argparse,fcntl,json
from importlib.metadata import version
from pathlib import Path
from scripts.admit_low_beta60_minutes_pre2026 import inspect_packet
from scripts.capture_low_beta60_minutes_pre2026 import capture_prefix,valid_pair
from scripts.fundamental_query_journal import digest,file_sha,write_packet_once
from scripts.illiquidity_minute_sources import prefix_minute_requirements,authenticate_reused_minutes

RAW='price-delay-raw-dev-20261021'
TARGET='price-delay-pre2026-formations-20261021/targets.json'
SOURCE='price-delay-account-source-events-20261021'
INVENTORY='price-delay-minute-inventory-20261021'
ROOTS=('illiquidity-minutes-dev-20261021','low-beta60-minutes-dev-20261021',
 'szse-value-momentum-minutes-dev-20261021','return-family-minutes-dev-20261017','szse-value-minutes-dev-20261017')
METHOD_FILES=('scripts/capture_price_delay_minutes_pre2026.py','scripts/capture_low_beta60_minutes_pre2026.py',
 'scripts/admit_low_beta60_minutes_pre2026.py','scripts/fundamental_query_journal.py','scripts/illiquidity_minute_sources.py',
 'scripts/tdx_history_checks.py','src/stock_rsi/intraday_tape.py','src/stock_rsi/lifecycle_source_rows.py',
 'src/stock_rsi/data.py','src/stock_rsi/calendar.py','src/stock_rsi/time.py')
PUBLIC_FILES=('experiments/qlib/price-delay-minute-gap-identities.json',
 'experiments/qlib/price-delay-minute-inventory.json','experiments/qlib/price-delay-raw-daily-results.json',
 'experiments/qlib/price-delay-raw-daily-independent-ledger-audit.json','experiments/qlib/price-delay-raw-daily-root-numeric-verification.json',
 'experiments/qlib/price-delay-raw-daily-verification.json',
 'docs/research/price-delay-minute-source-plan-2026-10-21.md')
LOCAL_FILES=(RAW+'/manifest.json',RAW+'/calendar.json',TARGET,SOURCE+'/summary.json',SOURCE+'/effective_proofs.json',
 INVENTORY+'/details.json',INVENTORY+'/summary.json','price-delay-raw-daily-pre2026-20261021/summary.json')


def read(path):return json.loads(Path(path).read_text())


def validate_profile(p):
 integers={'timeout_seconds':3,'pool_size':1,'server_count':1,'connections_per_server':1,
  'max_fresh_query_reservations':918,'max_attempts_per_request':1,'stop_after_consecutive_source_failures':3,
  'required_source_pairs':2502,'existing_source_pairs_to_reuse':1584}
 if (p['status']!='FROZEN_PRICE_DELAY_PRE2026_MINUTE_SOURCE_CAPTURE' or p['candidate']!='price_delay_d1'
     or p['window']!=['2024-01-02','2025-12-31'] or p['host']!='116.205.183.150:7709'
     or p['package_version']!='3.2.3' or p['heartbeat_interval'] is not None or p['probe_hosts'] is not False
     or p['inter_query_delay_seconds']!=.05
     or any(type(p[k]) is not int or p[k]!=v for k,v in integers.items())):
  raise ValueError('fixed price-delay918-query pre2026 single-endpoint profile required')


def require_new_output(path):
 if Path(path).exists():raise ValueError('preserve existing capture; no implicit restart or replacement')


def authenticate(base,repo,request,plan):
 validate_profile(plan)
 if (version('eltdx')!=plan['package_version'] or set(plan['method_code_sha256'])!=set(METHOD_FILES)
     or set(plan['public_evidence_sha256'])!=set(PUBLIC_FILES) or set(plan['local_source_sha256'])!=set(LOCAL_FILES)):
  raise ValueError('frozen source methods or installed SDK changed')
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(parent/n)!=h:raise ValueError('frozen source/method evidence changed: '+n)
 results=read(repo/'experiments/qlib/price-delay-raw-daily-results.json')
 audit=read(repo/'experiments/qlib/price-delay-raw-daily-independent-ledger-audit.json')
 review=read(repo/'experiments/qlib/price-delay-raw-daily-verification.json')
 inventory=read(repo/'experiments/qlib/price-delay-minute-inventory.json')
 if (results['raw_daily_proxy_development_gate_passes'] is not True
     or audit['daily_proxy_development_gate_passes_independently'] is not True
     or audit['summary_sha256']!=file_sha(base/'price-delay-raw-daily-pre2026-20261021/summary.json')
     or review['root_ledger_reproduction_byte_identical'] is not True
     or review['results_sha256']!=file_sha(repo/'experiments/qlib/price-delay-raw-daily-results.json')
     or inventory['local_details_sha256']!=file_sha(base/INVENTORY/'details.json')
     or request['local_details_sha256']!=inventory['local_details_sha256']
     or request['inventory_summary_sha256']!=file_sha(base/INVENTORY/'summary.json')
     or request['source_precedence']!=list(ROOTS) or set(request['source_manifest_sha256'])!=set(ROOTS)
     or request['conflicting_cached_requests']):raise ValueError('passed raw account and unconflicted fixed inventory required')
 m=read(base/RAW/'manifest.json');ss=read(base/SOURCE/'summary.json')
 if (file_sha(base/RAW/'manifest.json')!=request['raw_manifest_sha256']
     or file_sha(base/RAW/'calendar.json')!=m['calendar_sha256'] or m['names']!=151
     or m['window']!=['2023-12-29','2025-12-31'] or m['errors_sha256'] or m['pending_codes']
     or file_sha(base/SOURCE/'summary.json')!=request['source_projection_summary_sha256']
     or file_sha(base/SOURCE/'effective_proofs.json')!=ss['artifact_sha256']['effective_proofs.json']):
  raise ValueError('raw/calendar/primary lifecycle identity changed')
 sessions=read(base/RAW/'calendar.json')['sessions'];bars={}
 if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=m['window']:
  raise ValueError('complete original explicit calendar required')
 for c,h in m['per_code_sha256'].items():
  f=base/RAW/'codes'/(c+'.json')
  if file_sha(f)!=h:raise ValueError('original raw packet changed')
  v=read(f)
  if v['instrument']!=c or v['window']!=m['window'] or any(r['date']>'2025-12-31' for r in v['bars']):
   raise ValueError('raw source issuer/window changed')
  bars[c]={r['date']:r for r in v['bars']}
 if file_sha(base/TARGET)!=m['target_sha256'] or file_sha(base/TARGET)!=request['target_sha256']:
  raise ValueError('frozen price-delay targets changed')
 targets=read(base/TARGET)['price_delay_d1']
 if len(targets)!=24 or {c for t in targets.values() for c in t['weights']}!=set(bars):raise ValueError('fixed24target151name price-delay required')
 active,skipped=prefix_minute_requirements(targets,bars,read(base/SOURCE/'effective_proofs.json')['lifecycles'])
 if active!=request['active_requests'] or skipped!=request['nonexecuting_source_intervals'] or len(active)!=2502 or len(skipped)!=2:
  raise ValueError('complete fixed active/halting prefix changed')
 indices={}
 for name in ROOTS:
  f=base/name/'manifest.json'
  if file_sha(f)!=request['source_manifest_sha256'][name]:raise ValueError('original cached manifest changed')
  for filename,h in read(f)['per_session_sha256'].items():
   if Path(filename).name!=filename:raise ValueError('unsafe cached filename')
   indices.setdefault(filename,[]).append({'root':name,'sha256':h})
 reused={};fresh=[];references=0
 for code,day in active:
  valid_pair(code,day);filename=code+'-'+day+'.json';origins=indices.get(filename,[])
  if not origins:fresh.append([code,day]);continue
  signatures=set();selected=None
  for origin in origins:
   f=base/origin['root']/'sessions'/filename
   if file_sha(f)!=origin['sha256']:raise ValueError('cached reference bytes changed')
   packet=read(f);record=packet.get('methods',{}).get('minutes.history',packet)
   if packet['instrument']!=code or packet['requested_day']!=day:raise ValueError('cached issuer/session changed')
   signatures.add(digest({'status':record['status'],'response':record.get('response')}));references+=1
   if selected is None:selected=packet
  if len(signatures)!=1:raise ValueError('conflicting original cached responses')
  inspect_packet(code,day,selected,bars[code][day]);reused[filename]=origins[0]
 if (reused!=request['reused_session_provenance'] or fresh!=request['uncached_requests']
     or len(reused)!=1584 or len(fresh)!=918 or references!=2261):raise ValueError('complete fixed cache/fresh partition changed')
 authenticate_reused_minutes(base,reused,active)
 return reused,fresh


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','request','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
 base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen price-delay minute capture plan changed')
 plan=read(a.plan)
 if file_sha(a.request)!=plan['request_sha256']:raise ValueError('fixed gap identities changed')
 request=read(a.request);reused,fresh=authenticate(base,repo,request,plan)
 require_new_output(out)
 if a.preflight_only:
  print('preflight2502pairs1584reuse918fresh2261cachedreferences; no output/SDK/network',flush=True);return 0
 clients=[];cleanup=[]
 def close_client(client,entered):
  try:client.close();cleanup.append({'entered':entered,'close_called':True,'error':None})
  except Exception as exc:cleanup.append({'entered':entered,'close_called':True,'error_type':type(exc).__name__,'error':str(exc)})
 def fetch(code,day):
  from eltdx import TdxClient,to_jsonable
  if not clients:
   client=TdxClient(host=plan['host'],timeout=3,heartbeat_interval=None,probe_hosts=False,
    pool_size=1,server_count=1,connections_per_server=1)
   try:client.__enter__()
   except BaseException:close_client(client,False);raise
   clients.append(client)
  return to_jsonable(clients[0].minutes.history(code.lower(),day,include_raw=True))
 out.mkdir(parents=True)
 with (out/'capture.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  write_packet_once(out/'request.json',request)
  try:manifest=capture_prefix(base,out,reused,fresh,plan,fetch)
  finally:
   for client in clients:close_client(client,True)
   write_packet_once(out/'client_cleanup.json',{'created_clients':len(cleanup),'closed_clients':cleanup})
  scope={'status':'PRICE_DELAY_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'price_delay_d1',
   'capture_plan_sha256':a.expected_plan_sha256,'request_sha256':file_sha(a.request),
   'legacy_helper_manifest_sha256':file_sha(out/'manifest.json'),'legacy_status_marker_preserved':True,
   'expected_active_pairs':2502,'fixed_reused_pairs':1584,'maximum_fresh_logical_reservations':918,
   'complete_capture':manifest['complete_capture'],'cleanup_sha256':file_sha(out/'client_cleanup.json'),
   'new_2026_queries':False,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
  write_packet_once(out/'price-delay-scope.json',scope)
 if any(r['error'] is not None for r in cleanup):raise ValueError('source client cleanup failed; retained evidence needs review')
 print('price-delay minute capture',manifest['captured'],'/2502,logicalreservations',manifest['fresh_query_reservations'],flush=True)
 return 0 if manifest['complete_capture'] else 2

if __name__=='__main__':raise SystemExit(main())
