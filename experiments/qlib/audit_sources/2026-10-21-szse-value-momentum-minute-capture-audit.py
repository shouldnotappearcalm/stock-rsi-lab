"""Stdlib-only minute capture provenance audit; no SDK/network/account/admission."""
import argparse,copy,hashlib,json,re
from collections import Counter
from datetime import date,datetime
from decimal import Decimal as D
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

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','repo-root','capture-dir','plan','expected-plan-sha256','request','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv);base=Path(a.source_root);repo=Path(a.repo_root);root=Path(a.capture_dir);planfile=Path(a.plan);requestfile=Path(a.request);out=Path(a.output)
 assert not out.exists();plan,request,bars,reused,fresh,inputhashes,signatures=preflight(base,repo,planfile,a.expected_plan_sha256,requestfile)
 if a.preflight_only:print('Independent preflight1744identities/2halts,1051selected originalbytes,2225cachedreferences/8manifests,693fixedfresh; no pending output/SDK/network');return 0
 assert root.resolve()==(base/plan['capture_directory']).resolve()
 assert (root/'request.json').read_bytes()==requestfile.read_bytes() and (root/'plan.json').read_bytes()==planfile.read_bytes()
 assert read(root/'capture_request.json')=={'reused':reused,'fresh':fresh}
 manifest=read(root/'manifest.json');assert manifest['status']=='LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED' and manifest['plan_sha256']==sha(root/'plan.json') and manifest['capture_request_sha256']==sha(root/'capture_request.json')
 assert manifest['requested']==1744 and manifest['active_reused_packets_authenticated_upfront']==1051 and manifest['reused_session_provenance']==reused
 for flag in ('new_2026_queries','historical_arrival_verified','admitted_for_reconstructed_execution','portfolio_returns_computed','objective_achieved'):assert manifest[flag] is False
 expected_names={c+'-'+d+'.json' for c,d in request['active_requests']};assert set(manifest['per_session_sha256'])<=expected_names and set(reused)<=set(manifest['per_session_sha256'])
 assert manifest['captured']==len(manifest['per_session_sha256']) and manifest['complete_capture']==(manifest['captured']==1744)
 snapshots=list(root.glob('capture-snapshot-*.json'));assert len(snapshots)==1 and snapshots[0].name=='capture-snapshot-'+digest(manifest)+'.json' and read(snapshots[0])==manifest
 expectedkeys={digest(identity(c,d,plan['host'])):(c,d) for c,d in fresh};folders={f.name:f for f in (root/'queries').iterdir()} if (root/'queries').exists() else {}
 assert set(folders)<=set(expectedkeys) and len(folders)<=693
 assert set(folders)=={digest(identity(c,d,plan['host'])) for c,d in fresh[:len(folders)]}
 query_outcomes=[];projection={};reserved_count=response_count=0;unanswered=[];query_hashes={}
 for key,folder in folders.items():
  code,day=expectedkeys[key];check_identity(read(folder/'request.json'),code,day,plan['host'])
  present={f.name for f in folder.iterdir()};assert 'request.json' in present and present<={'request.json','reserved-1.json','response-1.json'}
  for f in folder.iterdir():query_hashes[str(f.relative_to(root))]=sha(f)
  reserved=folder/'reserved-1.json';responsefile=folder/'response-1.json'
  if not reserved.exists():assert not responsefile.exists();unanswered.append({'instrument':code,'day':day,'state':'REQUEST_WITHOUT_RESERVATION'});continue
  r=read(reserved);assert r['identity_sha256']==key and r['attempt']==1 and datetime.fromisoformat(r['reserved_at_utc']).utcoffset().total_seconds()==0;reserved_count+=1
  if not responsefile.exists():unanswered.append({'instrument':code,'day':day,'state':'RESERVED_OUTCOME_UNKNOWN','reservation_sha256':sha(reserved)});continue
  response=read(responsefile);assert response['identity_sha256']==key and response['reservation_sha256']==sha(reserved);response_count+=1
  projected=project_fresh(code,day,response,sha(reserved),sha(responsefile));projection[code+'-'+day+'.json']=projected
  query_outcomes.append({'instrument':code,'day':day,'journal_status':response['status'],'projected_status':projected['status'],'response_sha256':sha(responsefile),**({'error_type':response['error_type'],'error':response['error']} if response['status']=='SOURCE_ERROR' else {})})
 assert reserved_count==manifest['fresh_query_reservations']==len(list((root/'queries').glob('*/reserved-*.json'))) and response_count==manifest['fresh_query_responses_preserved']==len(list((root/'queries').glob('*/response-*.json')))
 statuscounts=Counter();fresh_packets=[];failed=[];quality_questions=[]
 for name,h in manifest['per_session_sha256'].items():
  f=root/'sessions'/name;assert Path(name).name==name and sha(f)==h;packet=read(f);code,day=name[:-5].split('-',1);pair(code,day)
  assert packet['instrument']==code and packet['requested_day']==day;rec=record(packet);statuscounts[rec['status']]+=1
  if name in reused:
   origin=reused[name];original=base/origin['root']/'sessions'/name;assert h==origin['sha256'] and f.read_bytes()==original.read_bytes()
  else:
   assert name in projection and packet==projection[name],(name,'fresh immutable journal projection');fresh_packets.append(name)
   if packet['status']=='REQUEST_FAILED':failed.append({'file':name,'sha256':h,'error_type':packet['error_type'],'error':packet['error']})
   else:
    try:cached_quality(code,day,packet,bars[code][day])
    except (AssertionError,ValueError,KeyError,TypeError,ArithmeticError) as exc:quality_questions.append({'file':name,'sha256':h,'error_type':type(exc).__name__,'error':str(exc),'admission':'SEPARATE_SOURCE_REVIEW_REQUIRED'})
 assert dict(statuscounts)==manifest['response_status_counts']
 captured_fresh={name for name in manifest['per_session_sha256'] if name not in reused};assert captured_fresh=={c+'-'+d+'.json' for c,d in fresh[:len(captured_fresh)]}
 consecutive=0;firststop=None
 for n,(c,d) in enumerate(fresh[:len(captured_fresh)],1):
  projected=projection[c+'-'+d+'.json'];consecutive=consecutive+1 if projected['status']=='REQUEST_FAILED' else 0
  if consecutive>=3:firststop=n;break
 assert manifest['stopped_after_consecutive_source_failures']==(firststop is not None)
 if firststop is not None:assert firststop==len(captured_fresh)==len(folders)
 assert list(manifest['per_session_sha256'])==sorted(manifest['per_session_sha256'])
 rebuilt_manifest={'status':'LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED','plan_sha256':sha(root/'plan.json'),'capture_request_sha256':sha(root/'capture_request.json'),'requested':1744,'captured':len(manifest['per_session_sha256']),'per_session_sha256':dict(sorted(manifest['per_session_sha256'].items())),'reused_session_provenance':reused,'active_reused_packets_authenticated_upfront':1051,'fresh_query_reservations':reserved_count,'fresh_query_responses_preserved':response_count,'response_status_counts':dict(statuscounts),'stopped_after_consecutive_source_failures':firststop is not None,'abnormal_exit':manifest['abnormal_exit'],'complete_capture':len(manifest['per_session_sha256'])==1744,'new_2026_queries':False,'historical_arrival_verified':False,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
 assert manifest==rebuilt_manifest and read(snapshots[0])==rebuilt_manifest
 unmanifested=[{'file':str(f.relative_to(root)),'sha256':sha(f)} for f in (root/'sessions').glob('*.json') if f.name not in manifest['per_session_sha256']]
 cleanupfile=root/'client_cleanup.json';cleanup=read(cleanupfile) if cleanupfile.exists() else None
 if cleanup is not None:
  assert cleanup['created_clients']==len(cleanup['closed_clients'])<=1
  assert all(v['close_called'] is True and type(v['entered']) is bool for v in cleanup['closed_clients'])
 cleanup_ok=cleanup is not None and all(v.get('error') is None for v in cleanup['closed_clients'])
 if len(folders) and cleanup is not None:assert cleanup['created_clients']==1
 scopefile=root/'composite-scope.json';scope=read(scopefile) if scopefile.exists() else None
 if scope is not None:
  assert scope=={'status':'COMPOSITE_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'szse_value_momentum_equal','capture_plan_sha256':a.expected_plan_sha256,'request_sha256':sha(requestfile),'legacy_helper_manifest_sha256':sha(root/'manifest.json'),'legacy_status_marker_preserved':True,'expected_active_pairs':1744,'fixed_reused_pairs':1051,'maximum_fresh_logical_reservations':693,'complete_capture':manifest['complete_capture'],'cleanup_sha256':sha(cleanupfile),'new_2026_queries':False,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
 negatives={}
 examplecode,exampleday=fresh[0];example=identity(examplecode,exampleday,plan['host'])
 for mode in ('future_day','wrong_endpoint','second_attempt','fresh_projection_rewrite','lost_source_error'):
  if mode=='future_day':
   try:pair(examplecode,'2026-01-05')
   except AssertionError:negatives[mode]=True
   else:raise AssertionError('future identity accepted')
  elif mode=='wrong_endpoint':
   changed=copy.deepcopy(example);changed['host']='unregistered:7709'
   try:check_identity(changed,examplecode,exampleday,plan['host'])
   except AssertionError:negatives[mode]=True
   else:raise AssertionError('wrong endpoint accepted')
  elif mode=='second_attempt':
   try:assert {'request.json','reserved-1.json','response-1.json','reserved-2.json'}<={'request.json','reserved-1.json','response-1.json'}
   except AssertionError:negatives[mode]=True
   else:raise AssertionError('second attempt accepted')
  else:
   response={'status':'SOURCE_ERROR','error_type':'FixtureError','error':'retain this source failure'};expected=project_fresh(examplecode,exampleday,response,'a'*64,'b'*64);changed=copy.deepcopy(expected)
   if mode=='fresh_projection_rewrite':changed['requested_day']='2026-01-05'
   else:changed['error']='hidden'
   try:assert changed==project_fresh(examplecode,exampleday,response,'a'*64,'b'*64)
   except AssertionError:negatives[mode]=True
   else:raise AssertionError('projection/error mutation accepted')
 for f,h in inputhashes.items():assert sha(f)==h
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for name,h in plan[field].items():assert sha(parent/name)==h
 assert sha(planfile)==a.expected_plan_sha256
 fully_recorded=manifest['complete_capture'] and manifest['abnormal_exit'] is None and not manifest['stopped_after_consecutive_source_failures'] and reserved_count==response_count==693 and not unanswered and not unmanifested and scope is not None and cleanup_ok
 result={'status':'INDEPENDENT_COMPOSITE_MINUTE_CAPTURE_PROVENANCE_RECONSTRUCTED_ADMISSION_SEPARATE','audit_code_sha256':sha(__file__),'capture_plan_sha256':sha(planfile),'request_sha256':sha(requestfile),'capture_manifest_sha256':sha(root/'manifest.json'),
  'scope_sha256':sha(scopefile) if scopefile.exists() else None,'legacy_snapshot_sha256':sha(snapshots[0]),'legacy_helper_status_and_snapshot_preserved':True,'composite_scope_verified':scope is not None,
  'required_active_identities_reconstructed':1744,'nonexecuting_source_intervals':request['nonexecuting_source_intervals'],'eight_source_manifests_authenticated':True,'matching_cache_references_authenticated':2225,'selected1051_reuse_bytes_unchanged':True,
  'capture_fully_recorded':fully_recorded,'capture_complete_flag':manifest['complete_capture'],'captured_packets':manifest['captured'],'captured_status_counts':dict(statuscounts),'fresh_logical_reservations':reserved_count,'fresh_responses':response_count,
  'query_artifact_sha256':query_hashes,'fresh_query_outcomes_and_errors':query_outcomes,'failed_source_packets':failed,'unanswered_or_unreserved_attempts':unanswered,'uncaptured_required_files':sorted(expected_names-set(manifest['per_session_sha256'])),
  'unmanifested_source_files_preserved':unmanifested,'abnormal_exit':manifest['abnormal_exit'],'stopped_after_consecutive_source_failures':manifest['stopped_after_consecutive_source_failures'],'client_cleanup':cleanup,'client_cleanup_verified':cleanup_ok,
  'fresh_source_quality_questions_for_separate_admission':quality_questions,'semantic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,'imports_project_code':False,
  'source_queries_performed_by_auditor':0,'SDK_client_imported_by_auditor':False,'admitted_for_reconstructed_execution':False,'historical_arrival_verified':False,'exact_share_precision_certified':False,'SDK_date_echo_authenticated':False,'transport_packet_count_certified':False,
  'queue_and_impact_calibrated':False,'portfolio_returns_computed':False,'account_replay_performed':False,'new_2026_queries':False,'objective_achieved':False,
  'limitations':['693is a logical minutes.history reservation ceiling with one attempt per identity, not a certified TCP/protocol transport-packet count. The installed SDK/client is not imported or reexecuted by this auditor.',
   'Capture completeness counts preserved packets, including failures; it grants no execution admission. All raw fresh payloads, errors, unanswered attempts, snapshot and cleanup evidence are retained.',
   'Cached-source content prechecks and fresh quality questions do not certify historical arrival/date echo, exact share volume, corporate completeness, queue/impact or any account result; a separate local-only1744sample admission is still required.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independent minute capture audit',manifest['captured'],'packets;',reserved_count,'logical reservations; admission false; no account/ROI')
 return 0
if __name__=='__main__':raise SystemExit(main())
