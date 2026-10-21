"""Stdlib-only independent1744-sample admission output reconstruction; no runner/SDK/network/account."""
import argparse,copy,hashlib,json,re
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal as D,ROUND_HALF_UP
from pathlib import Path
if not __debug__:raise RuntimeError('Assertions must remain enabled')
RAW='szse-value-momentum-raw-dev-20261021';TARGET='szse-value-momentum-formations-pre2026-20261021/targets.json';SOURCE='szse-value-momentum-account-sources-20261021';INV='szse-value-momentum-minute-inventory-20261021'
ROOTS=['tdx-fixed-order-history-20261017','intraday-prefix-tape-20261017','return-family-minutes-dev-20261017','reversal-minutes-full-20261017','szse-value-minutes-dev-20261017','szse-value-minutes-full-20261017','illiquidity-minutes-dev-20261021','low-beta60-minutes-dev-20261021']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def pair(code,day):assert re.fullmatch('(SH|SZ)[0-9]{6}',code) and date.fromisoformat(day).isoformat()==day and '2024-01-02'<=day<='2025-12-31'
def record(packet):return packet.get('methods',{}).get('minutes.history',packet)
def validate_plan(p):
 assert p['status']=='FROZEN_COMPOSITE_PRE2026_MINUTE_SOURCE_CAPTURE' and p['candidate']=='szse_value_momentum_equal' and p['window']==['2024-01-02','2025-12-31']
 assert p['host']=='116.205.183.150:7709' and p['package_version']=='3.2.3' and p['heartbeat_interval'] is None and p['probe_hosts'] is False and p['inter_query_delay_seconds']==.05
 for k,v in {'timeout_seconds':3,'pool_size':1,'server_count':1,'connections_per_server':1,'max_fresh_query_reservations':693,'max_attempts_per_request':1,'stop_after_consecutive_source_failures':3,'required_source_pairs':1744,'existing_source_pairs_to_reuse':1051,'cached_references_authenticated':2225}.items():assert type(p[k]) is int and p[k]==v,k
 assert p['existing_output_refused_no_implicit_resume'] is True and p['fresh_calls_made_before_freeze']==0
 for k in ('new_2026_queries_allowed','historical_arrival_certified','reconstructed_execution_admitted','portfolio_returns_computed','objective_achieved'):assert p[k] is False

def cached_quality(code,day,packet,daily):
 pair(code,day);assert packet['instrument']==code and packet['requested_day']==day and daily['date']==day and daily['tradestatus']=='1' and daily['isST']=='0'
 r=record(packet);assert r['status']=='RESPONSE_CAPTURED';v=r['response']
 assert v['exchange']==code[:2].lower() and type(v['market_id']) is int and v['market_id']==(1 if code.startswith('SH') else 0) and v['code']==code[2:] and v['trading_date']==day
 labels=[f'{h:02}:{m:02}' for h in range(16) for m in range(60) if '09:31'<=f'{h:02}:{m:02}'<='11:30' or '13:01'<=f'{h:02}:{m:02}'<='15:00']
 assert len(v['points'])==len(labels)==240;lower=0
 for n,(point,label) in enumerate(zip(v['points'],labels)):
  assert type(point['index']) is int and point['index']==n and point['time_label']==label and point['time']==day+'T'+label+':00+08:00'
  price,vol=point['price_milli'],point['volume'];assert type(price) is int and type(vol) is int and min(price,vol)>=0 and not isinstance(point['price'],bool)
  assert D(str(point['price']))==D(price)/1000
  if vol:assert price>0 and price%10==0 and D(daily['low'])<=D(price)/1000<=D(daily['high'])
  lower+=max(0,vol*100-100)
 assert D(v['points'][-1]['price_milli'])/1000==D(daily['close']) and lower<=D(daily['volume'])
 return lower

def preflight(base,repo,planfile,expected,requestfile):
 assert sha(planfile)==expected;p=read(planfile);validate_plan(p);assert sha(requestfile)==p['request_sha256'];r=read(requestfile)
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for name,h in p[field].items():assert not Path(name).is_absolute() and '..' not in Path(name).parts and sha(parent/name)==h,(field,name)
 for name,h in r['method_code_sha256'].items():assert sha(repo/name)==h
 assert r['source_precedence']==ROOTS and set(r['source_manifest_sha256'])==set(ROOTS) and not r['conflicting_cached_requests']
 for flag in ('minute_execution_admitted','portfolio_returns_computed','new_2026_market_values_queried'):assert r[flag] is False
 results=read(repo/'experiments/qlib/szse-value-momentum-raw-daily-results.json');audit=read(repo/'experiments/qlib/szse-value-momentum-raw-daily-ledger-audit.json');review=read(repo/'experiments/qlib/szse-value-momentum-raw-daily-output-review.json')
 assert results['raw_daily_proxy_development_gate_passes'] is True and audit['raw_daily_proxy_development_gate_passes_independently'] is True and review['ready_for_minute_source_inventory'] is True
 assert audit['summary_sha256']==review['summary_sha256']==sha(base/'szse-value-momentum-raw-daily-dev-20261021/summary.json')
 assert r['local_details_sha256']==sha(base/INV/'details.json') and r['inventory_summary_sha256']==sha(base/INV/'summary.json')
 rm=read(base/RAW/'manifest.json');assert sha(base/RAW/'manifest.json')==r['raw_manifest_sha256'] and rm['names']==103 and not rm['errors_sha256'] and not rm['pending_codes']
 sessions=read(base/RAW/'calendar.json')['sessions'];assert len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==['2023-12-29','2025-12-31'] and sha(base/RAW/'calendar.json')==rm['calendar_sha256']
 bars={};inputhashes={}
 for code,h in rm['per_code_sha256'].items():
  f=base/RAW/'codes'/(code+'.json');assert sha(f)==h;v=read(f);assert v['instrument']==code and v['window']==['2023-12-29','2025-12-31'];inputhashes[str(f)]=h
  assert all('2023-12-29'<=row['date']<='2025-12-31' for row in v['bars']);bars[code]={row['date']:row for row in v['bars']}
 assert sha(base/TARGET)==rm['target_sha256']==r['target_sha256'];targets=read(base/TARGET)['szse_value_momentum_equal'];assert len(targets)==24 and {c for t in targets.values() for c in t['weights']}==set(bars)
 assert sha(base/SOURCE/'summary.json')==r['source_projection_summary_sha256'];ss=read(base/SOURCE/'summary.json');assert sha(base/SOURCE/'lifecycles.json')==ss['artifact_sha256']['lifecycles.json'];lifecycles=read(base/SOURCE/'lifecycles.json')
 active=[];skipped=[];seen=set()
 for day,t in sorted(targets.items()):
  pair('SZ000001',day);assert sessions[sessions.index(day)-1]==t['as_of'] and day[:7]!=t['as_of'][:7];seen.update(t['weights'])
  for code in sorted(seen):
   boundary=lifecycles.get(code);row=bars[code].get(day)
   if boundary and day<boundary['effective_date']:
    assert boundary['kind']=='LISTING_BEGIN' and boundary['verified_primary_boundary'] is True and row is None and code not in t['weights']
    skipped.append({'instrument':code,'day':day,'reason':'BEFORE_PRIMARY_LISTING_BOUNDARY','primary_document_sha256':boundary['primary_document_sha256'],'actual_inventory_proven_zero':False,'synthetic_price_created':False});continue
   assert row is not None and row['date']==day and row['isST']=='0'
   if row['tradestatus']=='0':skipped.append({'instrument':code,'day':day,'reason':'SOURCE_HALT','actual_inventory_proven_zero':False,'synthetic_price_created':False})
   else:assert row['tradestatus']=='1';active.append([code,day])
 assert active==r['active_requests'] and skipped==r['nonexecuting_source_intervals'] and len(active)==1744 and len(skipped)==2
 index={}
 for name in ROOTS:
  mf=base/name/'manifest.json';assert sha(mf)==r['source_manifest_sha256'][name]
  for fn,h in read(mf)['per_session_sha256'].items():assert Path(fn).name==fn;index.setdefault(fn,[]).append({'root':name,'sha256':h})
 reused={};fresh=[];references=0;source_signatures={}
 for code,day in active:
  pair(code,day);fn=code+'-'+day+'.json';origins=index.get(fn,[])
  if not origins:fresh.append([code,day]);continue
  signatures=set();selected=None
  for origin in origins:
   f=base/origin['root']/'sessions'/fn;assert sha(f)==origin['sha256'];packet=read(f);assert packet['instrument']==code and packet['requested_day']==day
   rec=record(packet);signatures.add(digest({'status':rec['status'],'response':rec.get('response')}));references+=1;inputhashes[str(f)]=origin['sha256']
   if selected is None:selected=packet
  assert len(signatures)==1;cached_quality(code,day,selected,bars[code][day]);reused[fn]=origins[0];source_signatures[fn]=next(iter(signatures))
 assert len(reused)==1051 and len(fresh)==693 and references==2225 and reused==r['reused_session_provenance'] and fresh==r['uncached_requests']
 return p,r,bars,reused,fresh,inputhashes,source_signatures

def identity(code,day,host):pair(code,day);return {'method':'minutes.history','instrument':code,'requested_day':day,'host':host,'include_raw':True}
def check_identity(value,code,day,host):assert value==identity(code,day,host)
def project_fresh(code,day,response,reservation_sha,response_sha):
 if response['status']=='CAPTURED':
  v=response['payload'];assert response['payload_sha256']==digest(v) and v['fields']==['response'] and len(v['rows'])==1
  assert datetime.fromisoformat(v['captured_at_utc']).utcoffset().total_seconds()==0
  return {'instrument':code,'requested_day':day,'status':'RESPONSE_CAPTURED','response':v['rows'][0],'observed_at':v['captured_at_utc'],'query_response_sha256':response_sha,'query_reservation_sha256':reservation_sha}
 assert response['status']=='SOURCE_ERROR'
 return {'instrument':code,'requested_day':day,'status':'REQUEST_FAILED','error_type':response['error_type'],'error':response['error'],'query_response_sha256':response_sha,'query_reservation_sha256':reservation_sha}

def same(actual,expected):assert digest(actual)==digest(expected),(actual,expected)
def reconstruct(code,day,packet,daily):
 lower=cached_quality(code,day,packet,daily);v=record(packet)['response'];points=v['points'];hands=sum(p['volume'] for p in points);volume=D(daily['volume'])
 assert volume.is_finite() and volume>0 and volume==int(volume)
 windows=[]
 for index in range(0,240,5):
  block=points[index:index+5];end=datetime.fromisoformat(block[-1]['time']).astimezone(timezone.utc);start=end-timedelta(minutes=5)
  positive=[D(p['price_milli'])/1000 for p in block if p['volume']>0]
  value={'security_id':code,'start':start.isoformat(),'end':end.isoformat(),'available_at':end.isoformat(),
   'volume_lower_shares':sum(max(0,p['volume']*100-100) for p in block),'buy_price':str(max(positive)) if positive else None,'sell_price':str(min(positive)) if positive else None,
   'evidence_id':digest({'security_id':code,'day':day,'points':[{'time':p['time'],'volume':p['volume'],'price_milli':p['price_milli']} for p in block]})}
  assert type(value['volume_lower_shares']) is int and value['volume_lower_shares']>=0;windows.append(value)
 assert len(windows)==48 and sum(w['volume_lower_shares'] for w in windows)==lower<=volume
 facts={'points':240,'minute_volume_hands':hands,'minute_volume_shares_at_documented_multiplier':hands*100,'daily_volume_shares':str(volume),
  'exact_total_shares_match':hands*100==volume,'nearest_hand_daily_total_match_diagnostic_only':D(hands)==(volume/100).quantize(D(1),rounding=ROUND_HALF_UP),
  'last_close_matches':True,'traded_points_outside_daily_range':[],'positive_volume_on_original_halt':False,'historical_date_echo_authenticated':False,'exact_share_precision_certified':False}
 return {'status':'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE','windows':48,'facts':facts,'stressed_volume_lower_shares':lower},windows

def build_expected(base,repo,planfile,expectedsha):
 assert sha(planfile)==expectedsha;ap=read(planfile)
 assert ap['status']=='FROZEN_COMPOSITE_PRE2026_MINUTE_SOURCE_ADMISSION' and ap['candidate']=='szse_value_momentum_equal' and ap['window']==['2024-01-02','2025-12-31']
 assert ap['required_active_sessions']==1744 and ap['fixed_reused_pairs']==1051 and ap['exact_fresh_reservations']==693 and ap['nonexecuting_source_intervals']==2 and ap['network_calls_permitted']==0
 for flag in ('portfolio_returns_computed','new_2026_market_values_queried','candidate_promoted','objective_achieved'):assert ap[flag] is False
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for name,h in ap[field].items():assert not Path(name).is_absolute() and '..' not in Path(name).parts and sha(parent/name)==h,(field,name)
 cpfile=repo/'experiments/qlib/szse-value-momentum-minute-capture-plan.json';rqfile=repo/'experiments/qlib/szse-value-momentum-minute-gap-identities.json'
 assert sha(cpfile)==ap['capture_plan_sha256'] and sha(rqfile)==ap['request_sha256']
 cp,request,bars,reused,fresh,inputhashes,signatures=preflight(base,repo,cpfile,ap['capture_plan_sha256'],rqfile)
 capture=base/'szse-value-momentum-minutes-dev-20261021';manifest=read(capture/'manifest.json');scope=read(capture/'composite-scope.json');cleanup=read(capture/'client_cleanup.json')
 auditfile=repo/'experiments/qlib/szse-value-momentum-minute-capture-independent-audit.json';captureaudit=read(auditfile)
 assert sha(capture/'manifest.json')==ap['capture_manifest_sha256']==captureaudit['capture_manifest_sha256']
 assert captureaudit['capture_plan_sha256']==sha(cpfile) and captureaudit['request_sha256']==sha(rqfile) and captureaudit['scope_sha256']==sha(capture/'composite-scope.json')
 assert captureaudit['imports_project_code'] is False and captureaudit['capture_fully_recorded'] is True
 assert (capture/'plan.json').read_bytes()==cpfile.read_bytes() and (capture/'request.json').read_bytes()==rqfile.read_bytes()
 assert read(capture/'capture_request.json')=={'reused':reused,'fresh':fresh}
 same(scope,{'status':'COMPOSITE_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'szse_value_momentum_equal','capture_plan_sha256':sha(cpfile),'request_sha256':sha(rqfile),'legacy_helper_manifest_sha256':sha(capture/'manifest.json'),'legacy_status_marker_preserved':True,'expected_active_pairs':1744,'fixed_reused_pairs':1051,'maximum_fresh_logical_reservations':693,'complete_capture':manifest['complete_capture'],'cleanup_sha256':sha(capture/'client_cleanup.json'),'new_2026_queries':False,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False})
 cleanup_ok=(cleanup=={'created_clients':1,'closed_clients':[{'entered':True,'close_called':True,'error':None}]});assert cleanup_ok
 snapshot=capture/('capture-snapshot-'+digest(manifest)+'.json');assert read(snapshot)==manifest and sha(snapshot)==captureaudit['legacy_snapshot_sha256']
 assert manifest['status']=='LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED' and manifest['requested']==manifest['captured']==1744 and manifest['complete_capture'] is True and manifest['abnormal_exit'] is None and manifest['stopped_after_consecutive_source_failures'] is False
 assert manifest['plan_sha256']==sha(cpfile) and manifest['capture_request_sha256']==sha(capture/'capture_request.json') and manifest['reused_session_provenance']==reused
 expectednames={c+'-'+d+'.json' for c,d in request['active_requests']};assert set(manifest['per_session_sha256'])==expectednames=={p.name for p in (capture/'sessions').iterdir()}
 queryhashes={str(p.relative_to(capture)):sha(p) for p in (capture/'queries').rglob('*') if p.is_file()};same(queryhashes,captureaudit['query_artifact_sha256'])
 querykeys={digest(identity(c,d,cp['host'])):(c,d) for c,d in fresh};assert {f.name for f in (capture/'queries').iterdir()}==set(querykeys)
 reservations=list((capture/'queries').glob('*/reserved-*.json'));responses=list((capture/'queries').glob('*/response-*.json'))
 assert len(reservations)==len(responses)==manifest['fresh_query_reservations']==manifest['fresh_query_responses_preserved']==693
 assert all(f.name=='reserved-1.json' for f in reservations) and all(f.name=='response-1.json' for f in responses)
 freshprojections={}
 for key,(code,day) in querykeys.items():
  folder=capture/'queries'/key;assert {p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'}
  same(read(folder/'request.json'),identity(code,day,cp['host']));reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
  assert reserve['identity_sha256']==response['identity_sha256']==key and reserve['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json')
  assert datetime.fromisoformat(reserve['reserved_at_utc']).utcoffset().total_seconds()==0
  freshprojections[code+'-'+day+'.json']=project_fresh(code,day,response,sha(folder/'reserved-1.json'),sha(folder/'response-1.json'))
 expectedrows=[];windowids=[];windowhashes=[];exact=nearest=0;diffs=[];upper_misses=[];allpackets={}
 for code,day in request['active_requests']:
  name=code+'-'+day+'.json';f=capture/'sessions'/name;h=manifest['per_session_sha256'][name];assert sha(f)==h;packet=read(f);allpackets[name]=packet;inputhashes[str(f)]=h
  row={'instrument':code,'day':day,'source_sha256':h}
  if name in reused:
   origin=reused[name];assert f.read_bytes()==(base/origin['root']/'sessions'/name).read_bytes() and h==origin['sha256'];row['origin']=origin
  else:same(packet,freshprojections[name]);row['origin']='FROZEN_FRESH_QUERY'
  facts,windows=reconstruct(code,day,packet,bars[code][day]);row.update(facts);expectedrows.append(row)
  windowids.extend(w['evidence_id'] for w in windows);windowhashes.append(digest(windows));exact+=facts['facts']['exact_total_shares_match'];nearest+=facts['facts']['nearest_hand_daily_total_match_diagnostic_only']
  difference=facts['facts']['minute_volume_shares_at_documented_multiplier']-int(D(bars[code][day]['volume']));diffs.append(difference)
  if int(D(bars[code][day]['volume']))>facts['facts']['minute_volume_shares_at_documented_multiplier']+24000:upper_misses.append([code,day])
 assert len(expectedrows)==1744 and len(windowids)==83712 and manifest['response_status_counts']=={'RESPONSE_CAPTURED':1744}
 counts=dict(Counter(r['status'] for r in expectedrows));passed=(counts=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1744} and manifest['complete_capture'] is True and manifest['abnormal_exit'] is None and not manifest['stopped_after_consecutive_source_failures'] and len(reservations)==len(responses)==693 and cleanup_ok and captureaudit['capture_fully_recorded'] is True)
 details={'sessions':expectedrows,'nonexecuting_source_intervals':request['nonexecuting_source_intervals']}
 summary={'status':'COMPOSITE_PRE2026_MINUTE_SOURCE_ADMISSION_COMPLETE','plan_sha256':sha(planfile),'method_code_sha256':ap['method_code_sha256'],
  'capture_plan_sha256':sha(cpfile),'capture_manifest_sha256':sha(capture/'manifest.json'),'request_sha256':sha(rqfile),'capture_scope_sha256':sha(capture/'composite-scope.json'),'independent_capture_audit_sha256':sha(auditfile),
  'raw_manifest_sha256':sha(base/RAW/'manifest.json'),'target_sha256':request['target_sha256'],'required_active_sessions':1744,'nonexecuting_source_intervals':2,'status_counts':counts,
  'fresh_reservations':693,'fresh_responses':693,'reused_packets':1051,'client_cleanup_passes':cleanup_ok,'admitted_for_reconstructed_execution':passed,
  'details_sha256':None,'exact_share_total_matches':exact,'exact_share_precision_certified':False,'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,
  'portfolio_returns_computed':False,'new_2026_market_values_queried':False,'candidate_promoted':False,'objective_achieved':False,'exceptions':[]}
 diagnostics={'source_pairs':1744,'protocol_points':418560,'windows':83712,'all_window_evidence_ids_sha256':digest(windowids),'all_reconstructed_windows_sha256':digest(windowhashes),
  'exact_share_total_matches':exact,'nearest_hand_total_matches_diagnostic_only':nearest,'reported_minus_daily_share_difference_min':min(diffs),'reported_minus_daily_share_difference_max':max(diffs),
  'daily_share_volume_above_reported_plus_one_hand_per_minute':len(upper_misses),'upper_envelope_failures_diagnostic_only':upper_misses}
 return ap,cp,details,summary,diagnostics,allpackets,bars,inputhashes,queryhashes

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','repo-root','admission-dir','plan','expected-plan-sha256','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv);base=Path(a.source_root);repo=Path(a.repo_root);root=Path(a.admission_dir);planfile=Path(a.plan);out=Path(a.output);assert not out.exists()
 ap,cp,details,expectedsummary,diagnostics,packets,bars,inputhashes,queryhashes=build_expected(base,repo,planfile,a.expected_plan_sha256)
 if a.preflight_only:print('Independent source-only reconstruction1744samples/418560points/83712windows/693freshchains/2halts; no admission runner/output/SDK/network/account');return 0
 assert root.resolve()==(base/ap['output_relative']).resolve()
 actualdetails=read(root/'details.json');same(actualdetails,details);expectedsummary['details_sha256']=sha(root/'details.json');summary=read(root/'summary.json');same(summary,expectedsummary)
 negative={};code,day=details['sessions'][0]['instrument'],details['sessions'][0]['day'];packet=packets[code+'-'+day+'.json']
 for mode in ('missing_minute','wrong_security','outside_price_range','lunch_timestamp','oversized_lower_volume','off_cent_price','wrong_last_close'):
  changed=copy.deepcopy(packet);v=record(changed)['response']
  if mode=='missing_minute':v['points'].pop()
  elif mode=='wrong_security':changed['instrument']='SZ000001'
  elif mode=='outside_price_range':
   price=D(bars[code][day]['high'])+D('.01');v['points'][0].update(price_milli=int(price*1000),price=str(price),volume=1)
  elif mode=='lunch_timestamp':v['points'][120]['time']=day+'T12:01:00+08:00'
  elif mode=='oversized_lower_volume':v['points'][0]['volume']=int(D(bars[code][day]['volume']))//100+1000
  elif mode=='off_cent_price':v['points'][0].update(price_milli=10001,price='10.001',volume=1)
  else:
   last=v['points'][-1];last.update(price_milli=last['price_milli']+10,price=str(D(last['price_milli']+10)/1000))
  try:reconstruct(code,day,changed,bars[code][day])
  except (AssertionError,ValueError,KeyError):negative[mode]=True
  else:raise AssertionError('semantic source mutation accepted:'+mode)
 for mode in ('false_volume_lower_bound','erased_halting_identity','false_exact_volume_certification','forged_admission_total'):
  if mode in ('false_volume_lower_bound','erased_halting_identity'):
   changed=copy.deepcopy(actualdetails)
   if mode=='false_volume_lower_bound':changed['sessions'][0]['stressed_volume_lower_shares']+=100
   else:changed['nonexecuting_source_intervals'].pop()
   expected=details
  else:
   changed=copy.deepcopy(summary);expected=expectedsummary
   if mode=='false_exact_volume_certification':changed['exact_share_precision_certified']=True
   else:changed['required_active_sessions']=1743
  try:same(changed,expected)
  except AssertionError:negative[mode]=True
  else:raise AssertionError('semantic admission-output mutation accepted:'+mode)
 for f,h in inputhashes.items():assert sha(f)==h
 capture=base/'szse-value-momentum-minutes-dev-20261021';same({str(p.relative_to(capture)):sha(p) for p in (capture/'queries').rglob('*') if p.is_file()},queryhashes)
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for name,h in ap[field].items():assert sha(parent/name)==h
 assert sha(planfile)==a.expected_plan_sha256
 result={'status':'INDEPENDENT1744_COMPOSITE_MINUTE_SOURCE_ADMISSION_ARITHMETIC_RECONSTRUCTED','audit_code_sha256':sha(__file__),'admission_plan_sha256':sha(planfile),'admission_summary_sha256':sha(root/'summary.json'),
  'capture_plan_sha256':ap['capture_plan_sha256'],'capture_manifest_sha256':ap['capture_manifest_sha256'],'request_sha256':ap['request_sha256'],'imports_project_code':False,
  'source_pairs_reconstructed':1744,'reused_original_bytes_authenticated':1051,'fresh_immutable_queries_reconstructed':693,'nonexecuting_source_intervals_reconstructed':details['nonexecuting_source_intervals'],
  **diagnostics,'semantic_negative_controls_rejected':negative,'negative_controls_use_hash_gate':False,'exact_query_artifact_bytes_reauthenticated':True,
  'all1744_details_and_summary_independently_reconstructed':True,'reconstructed_source_admission_passes':summary['admitted_for_reconstructed_execution'],
  'exact_share_precision_certified':False,'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,
  'portfolio_returns_computed':False,'new_2026_market_values_queried':False,'candidate_promoted':False,'account_replay_performed':False,'network_calls':0,'objective_achieved':False,
  'limitations':['Source arithmetic/identity admission only. The decoded date may be request-attached by SDK; historical date echo and arrival are not authenticated.',
   'Hand-volume100share conversion and lower-bound stress do not certify exact per-minute share counts or exact trade totals. Exact/nearest-hand and upper-envelope matches are diagnostics only.',
   'No queue/impact calibration, corporate/tax completeness, actual account execution, portfolio result or2026financial evidence is established.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independent1744minute source admissions,418560points,83712windows,693freshreceipts and11negativecontrols reconstructed; no account/ROI/network')
 return 0
if __name__=='__main__':raise SystemExit(main())
