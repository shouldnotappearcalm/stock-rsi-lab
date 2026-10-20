"""Read-only pre2026 prefix inventory; no source fetch or account execution."""
import argparse,hashlib,json
from collections import Counter,defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from scripts.illiquidity_minute_sources import prefix_minute_requirements
from scripts.tdx_history_checks import inspect_minutes
from stock_rsi.intraday_tape import aggregate_minutes
p=argparse.ArgumentParser()
for n in ('source-root','output-dir'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);out=Path(a.output_dir);repo=Path(__file__).resolve().parents[3]
assert not out.exists()
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
raw=base/'low-beta60-raw-dev-20261021';m=read(raw/'manifest.json')
assert sha(raw/'manifest.json')=='411e2abe02ebf914c809d6b5acb9b7e2fabacafe7dc88081b980787fb0cd8613'
tf=base/'low-beta60-pre2026-formations-20261021/targets.json';assert sha(tf)==m['target_sha256']
targets=read(tf)['low_beta60'];bars={}
for c,h in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert sha(f)==h;v=read(f);assert all(r['date']<'2026-01-01' for r in v['bars'])
 bars[c]={r['date']:r for r in v['bars']}
active,skipped=prefix_minute_requirements(targets,bars,{})
# This precedence is fixed before reading the response quality for any pair.
roots=['tdx-fixed-order-history-20261017','intraday-prefix-tape-20261017','return-family-minutes-dev-20261017',
 'reversal-minutes-full-20261017','szse-value-minutes-dev-20261017',
 'szse-value-minutes-full-20261017','illiquidity-minutes-dev-20261021']
indices=defaultdict(list);manifests={}
for n in roots:
 f=base/n/'manifest.json';manifests[n]=sha(f)
 for name,h in read(f)['per_session_sha256'].items():
  assert Path(name).name==name;indices[name].append({'root':n,'sha256':h})
rows=[];missing=[];reuse={};conflicts=[]
for code,day in active:
 name=code+'-'+day+'.json';row={'instrument':code,'day':day};origins=indices.get(name,[])
 if not origins:row['status']='UNCACHED_IN_CHECKED_SOURCES';missing.append([code,day]);rows.append(row);continue
 signatures=set();loaded={}
 for origin in origins:
  f=base/origin['root']/'sessions'/name;assert sha(f)==origin['sha256'];packet=read(f)
  assert packet['instrument']==code and packet['requested_day']==day
  record=packet.get('methods',{}).get('minutes.history',packet)
  signatures.add(digest({'status':record['status'],'response':record.get('response')}));loaded[origin['root']]=record
 first=origins[0];reuse[name]=first;row.update(source_roots=origins,selected_source=first)
 if len(signatures)>1:row['status']='CONFLICTING_CACHED_RESPONSES';conflicts.append([code,day]);rows.append(row);continue
 record=loaded[first['root']]
 if record['status']!='RESPONSE_CAPTURED':row['status']='CACHED_SOURCE_FAILURE';row['source_status']=record['status'];rows.append(row);continue
 try:
  facts=inspect_minutes(code,day,record['response'],bars[code][day]);row['facts']=facts
  windows=aggregate_minutes(code,date.fromisoformat(day),record['response']['points'])
  lower=sum(w['volume_lower_shares'] for w in windows);row['stressed_volume_lower_shares']=lower
  if not facts['last_close_matches'] or facts['traded_points_outside_daily_range']:raise ValueError('historical minute price signature conflicts with raw day')
  if lower>int(Decimal(bars[code][day]['volume'])):raise ValueError('stressed minute volume exceeds whole-day source')
  row['status']='EXISTING_RECONSTRUCTED_SOURCE_CHECKS_PASSED'
 except (ValueError,KeyError,AssertionError) as exc:row['status']='CACHED_SOURCE_REJECTED';row['error']=str(exc)
 rows.append(row)
assert len(rows)==len(active) and all(day<='2025-12-31' for _,day in active)
out.mkdir(parents=True)
details={'active_requests':active,'nonexecuting_source_intervals':skipped,'session_inventory':rows,
 'uncached_requests':missing,'reused_session_provenance':reuse,'conflicting_cached_requests':conflicts}
(out/'details.json').write_text(json.dumps(details,indent=2)+'\n')
methods=['experiments/qlib/audit_sources/2026-10-21-low-beta60-minute-inventory.py','scripts/illiquidity_minute_sources.py',
 'scripts/tdx_history_checks.py','src/stock_rsi/intraday_tape.py','src/stock_rsi/lifecycle_source_rows.py',
 'scripts/fundamental_query_journal.py','src/stock_rsi/data.py','src/stock_rsi/calendar.py','src/stock_rsi/time.py']
result={'status':'LOW_BETA60_PRE2026_MINUTE_PREFIX_CACHE_INVENTORY_NOT_ADMISSION',
 'method_code_sha256':{n:sha(repo/n) for n in methods},'raw_manifest_sha256':sha(raw/'manifest.json'),
 'target_sha256':sha(tf),'source_manifest_sha256':manifests,'primary_tape_root':roots[0],
 'required_active_sessions':len(active),'nonexecuting_source_intervals':len(skipped),
 'status_counts':dict(Counter(r['status'] for r in rows)),'uncached_count':len(missing),
 'cache_conflict_count':len(conflicts),'cached_minute_packets_authenticated':sum(len(r.get('source_roots',[])) for r in rows),
 'local_details_sha256':sha(out/'details.json'),'new_network_requests':0,'source_fetch_performed':False,
 'full_October':False,'portfolio_returns_computed':False,'new_2026_market_values_queried':False,
 'source_metadata_may_include_later_keys':True,'source_packets_read_only_pre2026':True,
 'minute_execution_admitted':False,'historical_arrival_certified':False,'queue_and_impact_calibrated':False,
 'candidate_promoted':False,'objective_achieved':False}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('status','required_active_sessions','status_counts','uncached_count','cache_conflict_count')},indent=2))
