"""Stdlib-only authentication and arithmetic reconstruction of minute sources."""
import argparse,copy,hashlib,json
from collections import Counter
from datetime import date
from decimal import Decimal as D,ROUND_HALF_UP
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('source-root','capture-dir','admission-dir','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);capture=Path(a.capture_dir);admission=Path(a.admission_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
cpfile=repo/'experiments/qlib/low-beta60-minute-capture-plan.json';apfile=repo/'experiments/qlib/low-beta60-minute-admission-plan.json'
assert sha(cpfile)=='0c28aa72b264540852cf6956584b4aeb3ed57ea6918f4bfa1ee91a97dbbf9c33'
assert sha(apfile)=='4cb5fc3e3385d218b31950fbb2533847a1835671e6a94fecba38f8b090210ace'
cp,ap=read(cpfile),read(apfile);manifest=read(capture/'manifest.json');summary=read(admission/'summary.json')
assert cp['max_fresh_query_reservations']==493 and cp['max_attempts_per_request']==1 and cp['stop_after_consecutive_source_failures']==3
for plan in (cp,ap):
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for f,h in plan.get(field,{}).items():assert sha(parent/f)==h
assert sha(capture/'plan.json')==sha(cpfile)==ap['capture_plan_sha256']==manifest['plan_sha256']
assert sha(capture/'manifest.json')==ap['capture_manifest_sha256']==summary['capture_manifest_sha256']
assert sha(apfile)==summary['plan_sha256'] and ap['method_code_sha256']==summary['method_code_sha256']
rqfile=repo/'experiments/qlib/low-beta60-minute-gap-identities.json';request=read(rqfile)
assert sha(rqfile)==cp['request_sha256']==ap['request_sha256']==sha(capture/'request.json')==summary['request_sha256']
raw=base/'low-beta60-raw-dev-20261021';m=read(raw/'manifest.json');sessions=read(raw/'calendar.json')['sessions']
assert sha(raw/'manifest.json')==request['raw_manifest_sha256']==summary['raw_manifest_sha256']
assert len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==['2023-12-29','2025-12-31']
assert sha(raw/'calendar.json')==m['calendar_sha256'];bars={}
for c,h in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert sha(f)==h;packet=read(f)
 assert packet['instrument']==c and [r['date'] for r in packet['bars']]==sessions
 bars[c]={r['date']:r for r in packet['bars']}
tf=base/'low-beta60-pre2026-formations-20261021/targets.json';assert sha(tf)==request['target_sha256']==summary['target_sha256']
targets=read(tf)['low_beta60'];assert len(targets)==24 and len(bars)==69
active=[];seen=set()
for day,t in sorted(targets.items()):
 assert '2024-01-02'<=day<='2025-12-31' and sessions[sessions.index(day)-1]==t['as_of'] and day[:7]!=t['as_of'][:7]
 seen.update(t['weights']);assert seen<=set(bars)
 for c in sorted(seen):
  assert bars[c][day]['tradestatus']=='1' and bars[c][day]['isST']=='0';active.append([c,day])
assert active==request['active_requests'] and len(active)==1332 and request['nonexecuting_source_intervals']==[]
index={}
for name,h in request['source_manifest_sha256'].items():
 assert sha(base/name/'manifest.json')==h
 for fn,hh in read(base/name/'manifest.json')['per_session_sha256'].items():index.setdefault(fn,{'root':name,'sha256':hh})
reused={c+'-'+d+'.json':index[c+'-'+d+'.json'] for c,d in active if c+'-'+d+'.json' in index}
fresh=[[c,d] for c,d in active if c+'-'+d+'.json' not in index]
assert len(reused)==839 and len(fresh)==493 and reused==request['reused_session_provenance']==manifest['reused_session_provenance']
assert fresh==request['uncached_requests']
assert read(capture/'capture_request.json')=={'reused':reused,'fresh':fresh}
assert sha(capture/'capture_request.json')==manifest['capture_request_sha256']
expected_names={c+'-'+d+'.json' for c,d in active};assert set(manifest['per_session_sha256'])==expected_names
assert manifest['complete_capture'] is True and manifest['abnormal_exit'] is None and manifest['stopped_after_consecutive_source_failures'] is False
assert manifest['response_status_counts']=={'RESPONSE_CAPTURED':1332} and manifest['captured']==manifest['requested']==1332
reservations=list((capture/'queries').glob('*/reserved-*.json'));responses=list((capture/'queries').glob('*/response-*.json'))
assert len(reservations)==len(responses)==manifest['fresh_query_reservations']==manifest['fresh_query_responses_preserved']==493
labels=[f'{h:02}:{n:02}' for h in range(16) for n in range(60) if '09:31'<=f'{h:02}:{n:02}'<='11:30' or '13:01'<=f'{h:02}:{n:02}'<='15:00']
assert len(labels)==240

def reconstruct(code,day,packet,daily):
 assert '2024-01-02'<=day<='2025-12-31' and date.fromisoformat(day).isoformat()==day
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

details=read(admission/'details.json');assert sha(admission/'details.json')==summary['details_sha256'] and details['nonexecuting_source_intervals']==[]
assert [(r['instrument'],r['day']) for r in details['sessions']]==[(c,d) for c,d in active]
window_ids=[];diffs=[];upper_misses=[];packets={};querykeys=set();exact=0;nearest=0
for (c,d),row in zip(active,details['sessions']):
 name=c+'-'+d+'.json';f=capture/'sessions'/name;assert sha(f)==manifest['per_session_sha256'][name]==row['source_sha256']
 packet=read(f);packets[name]=packet
 if name in reused:
  origin=reused[name];assert sha(base/origin['root']/'sessions'/name)==sha(f)==origin['sha256'] and row['origin']==origin
 else:
  identity={'method':'minutes.history','instrument':c,'requested_day':d,'host':cp['host'],'include_raw':True};key=digest(identity);querykeys.add(key);folder=capture/'queries'/key
  assert read(folder/'request.json')==identity and row['origin']=='FROZEN_FRESH_QUERY'
  res=read(folder/'reserved-1.json');response=read(folder/'response-1.json');payload=response['payload']
  assert res['identity_sha256']==key and res['attempt']==1 and response['status']=='CAPTURED' and response['identity_sha256']==key
  assert sha(folder/'reserved-1.json')==response['reservation_sha256']==packet['query_reservation_sha256']
  assert sha(folder/'response-1.json')==packet['query_response_sha256'] and digest(payload)==response['payload_sha256']
  assert payload['fields']==['response'] and payload['rows']==[packet['response']] and packet['observed_at']==payload['captured_at_utc']
 facts,lower,ids=reconstruct(c,d,packet,bars[c][d]);window_ids.extend(ids)
 assert row['status']=='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE' and row['windows']==48 and row['facts']==facts and row['stressed_volume_lower_shares']==lower
 exact+=facts['exact_total_shares_match'];nearest+=facts['nearest_hand_daily_total_match_diagnostic_only']
 difference=facts['minute_volume_shares_at_documented_multiplier']-int(D(bars[c][d]['volume']));diffs.append(difference)
 if int(D(bars[c][d]['volume']))>facts['minute_volume_shares_at_documented_multiplier']+24000:upper_misses.append([c,d])
assert len(querykeys)==493 and {f.parent.name for f in reservations}==querykeys=={f.parent.name for f in responses}
assert all(f.name=='reserved-1.json' for f in reservations) and all(f.name=='response-1.json' for f in responses)
assert summary['status_counts']=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1332} and summary['admitted_for_reconstructed_execution'] is True
assert exact==summary['exact_share_total_matches']==100 and len(window_ids)==1332*48
first_c,first_d=active[0];first_packet=packets[first_c+'-'+first_d+'.json'];negative={}
for kind in ('missing_minute','wrong_security','outside_price_range','lunch_timestamp','oversized_lower_volume'):
 packet=copy.deepcopy(first_packet);record=packet.get('methods',{}).get('minutes.history',packet);v=record['response']
 if kind=='missing_minute':v['points'].pop()
 elif kind=='wrong_security':packet['instrument']='SZ000001'
 elif kind=='outside_price_range':
  price=D(bars[first_c][first_d]['high'])+D('.01');v['points'][0].update(price_milli=int(price*1000),price=str(price),volume=1)
 elif kind=='lunch_timestamp':v['points'][120]['time']=first_d+'T12:01:00+08:00'
 else:v['points'][0]['volume']=int(D(bars[first_c][first_d]['volume']))//100+1000
 try:reconstruct(first_c,first_d,packet,bars[first_c][first_d])
 except (AssertionError,KeyError):negative[kind]=True
 else:raise AssertionError('source arithmetic negative accepted:'+kind)
for flag in ('historical_arrival_verified','sdk_date_echo_authenticated','queue_and_impact_calibrated','full_corporate_actions_certified','portfolio_returns_computed','new_2026_market_values_queried','candidate_promoted','objective_achieved'):assert summary[flag] is False
result={'status':'INDEPENDENT_LOW_BETA60_COMPLETE_MINUTE_SOURCE_AUDIT_PASSED','audit_code_sha256':sha(__file__),
 'capture_plan_sha256':sha(cpfile),'admission_plan_sha256':sha(apfile),'capture_manifest_sha256':sha(capture/'manifest.json'),
 'admission_summary_sha256':sha(admission/'summary.json'),'imports_project_code':False,'source_pairs_reconstructed':1332,
 'reused_original_bytes_authenticated':839,'fresh_immutable_queries_reconstructed':493,'protocol_points_reconstructed':1332*240,
 'five_minute_evidence_windows_reconstructed':len(window_ids),'all_window_ids_sha256':digest(window_ids),
 'exact_share_total_matches':exact,'nearest_hand_total_matches_diagnostic_only':nearest,
 'reported_minus_daily_share_difference_min':min(diffs),'reported_minus_daily_share_difference_max':max(diffs),
 'daily_share_volume_above_reported_plus_one_hand_per_minute':len(upper_misses),'upper_envelope_failures':upper_misses,
 'semantic_negative_controls_rejected':negative,'negative_controls_use_hash_gate':False,
 'reconstructed_source_admission_passes':True,'exact_share_precision_certified':False,'historical_arrival_verified':False,
 'sdk_date_echo_authenticated':False,'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,
 'portfolio_returns_computed':False,'new_2026_market_values_queried':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('Independent1332source pairs,493requests,319680protocol points,63936windows and5negative controls passed')
