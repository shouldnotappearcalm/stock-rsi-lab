"""Read-only fixed-policy pre2026 minute inventory, never query or replay."""
import argparse,json
from pathlib import Path
from scripts.fundamental_query_journal import file_sha,digest
from scripts.illiquidity_minute_sources import prefix_minute_requirements
from scripts.admit_low_beta60_minutes_pre2026 import inspect_packet
from scripts.capture_low_beta60_minutes_pre2026 import valid_pair

ROOTS=('illiquidity-minutes-dev-20261021','low-beta60-minutes-dev-20261021',
 'szse-value-momentum-minutes-dev-20261021','return-family-minutes-dev-20261017','szse-value-minutes-dev-20261017')
TARGET_SHA='03acf78c10c10376b5764b0d1399d1631af08a608aa865575aa1bd56203fad0c'
METHOD_FILES=('scripts/inventory_price_delay_minutes_pre2026.py','scripts/fundamental_query_journal.py',
 'scripts/illiquidity_minute_sources.py','scripts/admit_low_beta60_minutes_pre2026.py',
 'scripts/capture_low_beta60_minutes_pre2026.py','scripts/tdx_history_checks.py',
 'src/stock_rsi/intraday_tape.py','src/stock_rsi/lifecycle_source_rows.py',
 'src/stock_rsi/data.py','src/stock_rsi/calendar.py','src/stock_rsi/time.py')

def read(path):return json.loads(Path(path).read_text())

def main():
 p=argparse.ArgumentParser()
 for n in ('source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args();base=Path(a.source_root);out=Path(a.output_dir);repo=Path(__file__).resolve().parents[1]
 if out.exists():raise ValueError('preserve prior inventory')
 raw=base/'price-delay-raw-dev-20261021';target=base/'price-delay-pre2026-formations-20261021/targets.json'
 m=read(raw/'manifest.json');source=read(base/'price-delay-account-source-events-20261021/summary.json')
 if (m['window']!=['2023-12-29','2025-12-31'] or m['names']!=151 or m['errors_sha256'] or m['pending_codes']
     or file_sha(raw/'manifest.json')!=source['raw_manifest_sha256']
     or file_sha(target)!=TARGET_SHA or m['target_sha256']!=TARGET_SHA
     or file_sha(raw/'calendar.json')!=m['calendar_sha256']):raise ValueError('fixed pre2026 target/source identity required')
 sessions=read(raw/'calendar.json')['sessions'];bars={}
 if len(sessions)!=486 or sessions[0]!='2023-12-29' or sessions[-1]!='2025-12-31' or sessions!=sorted(set(sessions)):
  raise ValueError('complete explicit pre2026 sessions required')
 for c,h in m['per_code_sha256'].items():
  f=raw/'codes'/(c+'.json')
  if file_sha(f)!=h:raise ValueError('raw source bytes changed')
  v=read(f)
  if v['instrument']!=c or v['window']!=m['window'] or [r['date'] for r in v['bars']]!=sessions:
   raise ValueError('raw source issuer or complete capped calendar changed')
  bars[c]={r['date']:r for r in v['bars']}
 targets=read(target)['price_delay_d1']
 if len(targets)!=24 or {c for t in targets.values() for c in t['weights']}!=set(bars):raise ValueError('fixed24target151name universe required')
 active,skipped=prefix_minute_requirements(targets,bars,{})
 index={};manifests={}
 for name in ROOTS:
  f=base/name/'manifest.json';manifests[name]=file_sha(f)
  for filename,h in read(f)['per_session_sha256'].items():
   if Path(filename).name!=filename:raise ValueError('unsafe source cache identity')
   index.setdefault(filename,[]).append({'root':name,'sha256':h})
 reused={};fresh=[];invalid=[];conflicts=[];references=0;details={}
 for code,day in active:
  valid_pair(code,day);filename=code+'-'+day+'.json';origins=index.get(filename,[])
  if not origins:fresh.append([code,day]);continue
  signatures=set();errors=[]
  for origin in origins:
   f=base/origin['root']/'sessions'/filename
   if file_sha(f)!=origin['sha256']:raise ValueError('cached source bytes changed')
   packet=read(f);record=packet.get('methods',{}).get('minutes.history',packet)
   if packet['instrument']!=code or packet['requested_day']!=day:raise ValueError('cached issuer/session mismatch')
   signatures.add(digest({'status':record['status'],'response':record.get('response')}));references+=1
   try:inspect_packet(code,day,packet,bars[code][day])
   except (ValueError,KeyError,TypeError) as exc:errors.append({'root':origin['root'],'error_type':type(exc).__name__,'reason':str(exc)})
  details[filename]={'origins':origins,'distinct_response_signatures':len(signatures),'errors':errors}
  if len(signatures)!=1:conflicts.append([code,day])
  elif errors:invalid.append([code,day])
  else:reused[filename]=origins[0]
 detail={'candidate':'price_delay_d1','source_precedence':list(ROOTS),'source_manifest_sha256':manifests,
  'target_sha256':TARGET_SHA,'raw_manifest_sha256':file_sha(raw/'manifest.json'),
  'source_projection_summary_sha256':file_sha(base/'price-delay-account-source-events-20261021/summary.json'),
  'active_requests':active,'nonexecuting_source_intervals':skipped,'reused_session_provenance':reused,
  'uncached_requests':fresh,'invalid_cached_requests':invalid,'conflicting_cached_requests':conflicts,'cached_reference_details':details}
 out.mkdir(parents=True);(out/'details.json').write_text(json.dumps(detail,indent=2)+'\n')
 summary={'status':'FIXED_PRICE_DELAY_PRE2026_MINUTE_INVENTORY_NOT_SOURCE_ADMISSION','candidate':'price_delay_d1',
  'method_code_sha256':{n:file_sha(repo/n) for n in METHOD_FILES},'source_precedence_fixed_before_inventory':list(ROOTS),
  'required_active_pairs':len(active),'nonexecuting_intervals':len(skipped),'cached_valid_pairs':len(reused),
  'uncached_pairs':len(fresh),'invalid_cached_pairs':len(invalid),'conflicting_cached_pairs':len(conflicts),
  'cached_references_checked':references,'local_details_sha256':file_sha(out/'details.json'),
  'all_requested_dates_end':'2025-12-31','new_network_queries':0,'new_2026_values_read':False,
  'source_admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print({k:v for k,v in summary.items() if k.endswith(('pairs','intervals','checked'))},flush=True)

if __name__=='__main__':main()
