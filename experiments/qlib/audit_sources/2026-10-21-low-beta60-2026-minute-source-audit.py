"""Independent stdlib reconstruction of754newyear minute sources and old1332SHA."""
import argparse,copy,hashlib,json
from datetime import date
from decimal import Decimal as D,ROUND_HALF_UP
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('source-root','capture-dir','admission-dir','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);capture=Path(a.capture_dir);admission=Path(a.admission_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact_json(f,v):assert Path(f).read_bytes()==(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
pf=repo/'experiments/qlib/low-beta60-2026-minute-source-plan-v2.json'
assert sha(pf)=='5083b01ee5d5d25d1fc204823aee98434d34ad394078a8144dd45d7a03f293e9'
plan=read(pf)
for field,root in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
 assert all(sha(root/f)==h for f,h in plan[field].items())
inventory=read(repo/'experiments/qlib/low-beta60-continuous-minute-source-inventory-summary.json')
reused=inventory['reused2026_session_provenance'];fresh=inventory['uncached2026_requests'];active=inventory['required2026_requests']
assert len(active)==754 and len(reused)==507 and len(fresh)==247
oldroot=base/'low-beta60-minutes-dev-20261021';oldproof=read(repo/'experiments/qlib/low-beta60-minute-source-verification.json')
assert sha(oldroot/'manifest.json')==oldproof['capture_manifest_sha256'];oldmanifest=read(oldroot/'manifest.json')
assert len(oldmanifest['per_session_sha256'])==1332 and all(sha(oldroot/'sessions'/n)==h for n,h in oldmanifest['per_session_sha256'].items())
old_audit=repo/'experiments/qlib/low-beta60-minute-source-independent-audit.json'
assert sha(old_audit)==oldproof['independent_audit_sha256'] and read(old_audit)['reconstructed_source_admission_passes'] is True
manifest=read(capture/'manifest.json');summary=read(admission/'summary.json')
assert (capture/'plan.json').read_bytes()==pf.read_bytes() and manifest['plan_sha256']==sha(pf)==summary['plan_sha256']
assert sha(capture/'manifest.json')==summary['capture_manifest_sha256']
snapshots=list(capture.glob('capture-snapshot-*.json'));assert len(snapshots)==1 and sha(snapshots[0])==sha(capture/'manifest.json')
assert snapshots[0].name=='capture-snapshot-'+digest(manifest)+'.json'
exact_json(capture/'capture_request.json',{'reused':reused,'fresh':fresh});assert sha(capture/'capture_request.json')==manifest['capture_request_sha256']
assert manifest['reused_session_provenance']==reused and manifest['captured']==manifest['requested']==754
assert manifest['complete_capture'] is True and manifest['abnormal_exit'] is None and not manifest['stopped_after_consecutive_source_failures']
assert manifest['response_status_counts']=={'RESPONSE_CAPTURED':754} and manifest['fresh_query_reservations']==manifest['fresh_query_responses_preserved']==247
assert set(manifest['per_session_sha256'])=={c+'-'+d+'.json' for c,d in active}=={f.name for f in (capture/'sessions').iterdir()}
raw=base/'low-beta60-raw-extension-20261021';m=read(raw/'manifest.json');assert sha(raw/'manifest.json')==inventory['raw_manifest_sha256'];bars={}
for c,h in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert sha(f)==h;bars[c]={r['date']:r for r in read(f)['bars']}
target=base/'low-beta60-calendar-extension-formations-20261021/targets.json';assert sha(target)==inventory['target_sha256']
derived=[];seen=set()
for day,t in sorted(read(target)['low_beta60'].items()):
 seen.update(t['weights'])
 if day<'2026':continue
 for c in sorted(seen):
  if bars[c][day]['tradestatus']=='1':derived.append([c,day])
assert derived==active
labels=[f'{h:02}:{n:02}' for h in range(16) for n in range(60) if '09:31'<=f'{h:02}:{n:02}'<='11:30' or '13:01'<=f'{h:02}:{n:02}'<='15:00']
def reconstruct(code,day,packet,daily):
 assert '2026-01-01'<=day<='2026-10-13' and date.fromisoformat(day).isoformat()==day
 assert packet['instrument']==code and packet['requested_day']==day and daily['date']==day and daily['tradestatus']=='1'
 record=packet.get('methods',{}).get('minutes.history',packet);assert record['status']=='RESPONSE_CAPTURED';v=record['response']
 assert v['exchange']==code[:2].lower() and type(v['market_id']) is int and v['market_id']==(1 if code.startswith('SH') else 0)
 assert v['code']==code[2:] and v['trading_date']==day and len(v['points'])==240
 hands=0;lower=0;window_ids=[]
 for n,(point,label) in enumerate(zip(v['points'],labels)):
  assert type(point['index']) is int and point['index']==n and point['time_label']==label and point['time']==day+'T'+label+':00+08:00'
  price,vol=point['price_milli'],point['volume']
  assert type(price) is int and type(vol) is int and min(price,vol)>=0 and not isinstance(point['price'],bool)
  assert D(str(point['price']))==D(price)/1000
  if vol:assert price>0 and price%10==0 and D(daily['low'])<=D(price)/1000<=D(daily['high'])
  hands+=vol;lower+=max(0,vol*100-100)
 for n in range(0,240,5):
  b=v['points'][n:n+5];window_ids.append(digest({'security_id':code,'day':day,'points':[{'time':x['time'],'volume':x['volume'],'price_milli':x['price_milli']} for x in b]}))
 volume=D(daily['volume']);assert volume.is_finite() and volume>0 and volume==int(volume)
 assert D(v['points'][-1]['price_milli'])/1000==D(daily['close']) and lower<=volume
 facts={'points':240,'minute_volume_hands':hands,'minute_volume_shares_at_documented_multiplier':hands*100,
  'daily_volume_shares':str(volume),'exact_total_shares_match':hands*100==volume,
  'nearest_hand_daily_total_match_diagnostic_only':D(hands)==(volume/100).quantize(D(1),rounding=ROUND_HALF_UP),
  'last_close_matches':True,'traded_points_outside_daily_range':[],'positive_volume_on_original_halt':False,
  'historical_date_echo_authenticated':False,'exact_share_precision_certified':False}
 return facts,lower,window_ids


details=read(admission/'details.json');assert sha(admission/'details.json')==summary['details_sha256']
rows={(r['instrument'],r['day']):r for r in details['sessions']};assert len(rows)==754 and set(rows)=={tuple(p) for p in active}
ids=[];diffs=[];packets={};querykeys=set();exact=nearest=0
for c,d in active:
 name=c+'-'+d+'.json';f=capture/'sessions'/name;row=rows[c,d]
 assert sha(f)==manifest['per_session_sha256'][name]==row['source_sha256'];packet=read(f);packets[name]=packet
 if name in reused:
  origin=reused[name];assert sha(base/origin['root']/'sessions'/name)==sha(f)==origin['sha256'] and row['origin']==origin
 else:
  identity={'method':'minutes.history','instrument':c,'requested_day':d,'host':plan['host'],'include_raw':True};key=digest(identity);querykeys.add(key);folder=capture/'queries'/key
  assert {p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'}
  exact_json(folder/'request.json',identity);reserved=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
  exact_json(folder/'reserved-1.json',reserved);exact_json(folder/'response-1.json',response)
  assert reserved['identity_sha256']==key and reserved['attempt']==1 and response['status']=='CAPTURED' and response['identity_sha256']==key
  assert sha(folder/'reserved-1.json')==response['reservation_sha256']==packet['query_reservation_sha256']
  assert sha(folder/'response-1.json')==packet['query_response_sha256'];payload=response['payload'];assert digest(payload)==response['payload_sha256']
  assert payload['fields']==['response'] and payload['rows']==[packet['response']] and packet['observed_at']==payload['captured_at_utc']
  assert row['origin']=='FROZEN_FRESH2026_QUERY'
 facts,lower,windows=reconstruct(c,d,packet,bars[c][d]);ids.extend(windows)
 assert row['status']=='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE' and row['windows']==48 and row['facts']==facts and row['stressed_volume_lower_shares']==lower
 exact+=facts['exact_total_shares_match'];nearest+=facts['nearest_hand_daily_total_match_diagnostic_only']
 diffs.append(facts['minute_volume_shares_at_documented_multiplier']-int(D(bars[c][d]['volume'])))
assert len(querykeys)==len(list((capture/'queries').iterdir()))==247 and {p.name for p in (capture/'queries').iterdir()}==querykeys
assert summary['status_counts']=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':754} and summary['admitted_for_reconstructed_execution'] is True
assert summary['combined_source_pairs_including_original1332']==2086 and summary['original1332_source_bytes_rechecked_unchanged'] is True
assert summary['exact_share_total_matches']==exact and summary['nearest_hand_total_matches_diagnostic_only']==nearest and len(ids)==754*48
first_c,first_d=active[0];original=packets[first_c+'-'+first_d+'.json'];negative={}
for kind in ('missing_minute','wrong_security','outside_price_range','lunch_timestamp','oversized_lower_volume'):
 packet=copy.deepcopy(original);v=packet.get('methods',{}).get('minutes.history',packet)['response']
 if kind=='missing_minute':v['points'].pop()
 elif kind=='wrong_security':packet['instrument']='SZ000001'
 elif kind=='outside_price_range':
  price=D(bars[first_c][first_d]['high'])+D('.01');v['points'][0].update(price_milli=int(price*1000),price=str(price),volume=1)
 elif kind=='lunch_timestamp':v['points'][120]['time']=first_d+'T12:01:00+08:00'
 else:v['points'][0]['volume']=int(D(bars[first_c][first_d]['volume']))//100+1000
 try:reconstruct(first_c,first_d,packet,bars[first_c][first_d])
 except (AssertionError,KeyError):negative[kind]=True
 else:raise AssertionError('source arithmetic negative accepted:'+kind)
for k in ('exact_share_precision_certified','historical_arrival_verified','sdk_date_echo_authenticated','queue_and_impact_calibrated','full_corporate_actions_certified','portfolio_returns_computed','candidate_promoted','objective_achieved'):assert summary[k] is False
result={'status':'INDEPENDENT754_NEWYEAR_MINUTE_SOURCES_RECONSTRUCTED_AND1332_ORIGINAL_BYTES_UNCHANGED',
 'audit_code_sha256':sha(__file__),'plan_sha256':sha(pf),'capture_manifest_sha256':sha(capture/'manifest.json'),
 'admission_summary_sha256':sha(admission/'summary.json'),'source_pairs_reconstructed':754,
 'original1332_source_bytes_authenticated_unchanged':True,'original_independent_audit_sha256':sha(old_audit),
 'combined_source_pairs':2086,'cached_source_bytes_authenticated':507,'fresh_queries_reconstructed':247,
 'points_reconstructed':754*240,'windows_reconstructed':len(ids),'all_newyear_window_ids_sha256':digest(ids),
 'exact_share_total_matches':exact,'nearest_hand_total_matches_diagnostic_only':nearest,
 'reported_minus_daily_share_difference_min':min(diffs),'reported_minus_daily_share_difference_max':max(diffs),
 'semantic_negative_controls_rejected':negative,'negative_controls_use_hash_gate':False,'imports_project_code':False,
 'reconstructed_source_admission_passes':True,'exact_share_precision_certified':False,'historical_arrival_verified':False,
 'sdk_date_echo_authenticated':False,'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,
 'portfolio_returns_computed':False,'candidate_promoted':False,'objective_achieved':False}
with Path(a.output).open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print('Independent754newyear sources/247queries/180960points/36192windows reconstructed;old1332bytes unchanged;five negatives rejected;no ROI')
