"""Stdlib source-output audit; capture/projection integrity is not account admission.
Fresh SDK-decoded replies are reconstructed; inherited96 packets stay byte exact.
No source calls, project imports, price adjustment inference, or account replay.
"""
import argparse,copy,hashlib,json,re
from collections import Counter,defaultdict
from datetime import date,datetime
from decimal import Decimal as D
from pathlib import Path
if not __debug__:raise RuntimeError('audit assertions must remain enabled')
START,END='2023-12-29','2025-12-31'
FRESH=['SZ000021','SZ000032','SZ001389','SZ001696','SZ002156','SZ002312','SZ002429']
SOURCES=['low-beta60-raw-dev-20261021','budgeted-residual-raw-dev-20261021','illiquidity-raw-source-continuation-20261020','return-families-raw-dev-20261017','szse-value-raw-dev-20261017']
BAR=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
DIV=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
ADJ=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
PARAMS={'daily':{'start_date':START,'end_date':END,'frequency':'d','adjustflag':'3'},'dividend2024':{'year':'2024','yearType':'operate'},'dividend2025':{'year':'2025','yearType':'operate'},'adjustments':{'start_date':START,'end_date':END}}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def canonical_day(d):assert isinstance(d,str) and date.fromisoformat(d).isoformat()==d;return d
def quantity(v):
 d=D(v);assert d.is_finite() and d>=0;return d
def symbol(code):assert re.fullmatch(r'SZ(?:000|001|002|003)\d{3}',code);return 'sz.'+code[2:]
def dictrows(fields,rows,expected):
 assert fields==expected and all(isinstance(r,list) and len(r)==len(fields) for r in rows)
 return [dict(zip(fields,r)) for r in rows]
def calendar_facts(bars,sessions):
 days=[canonical_day(r['date']) for r in bars];assert days==sorted(set(days))
 extra=sorted(set(days)-set(sessions));assert not extra,extra
 return {'full_explicit_calendar_covered':days==sessions,'observed_rows':len(days),'first_observed_session':days[0] if days else None,'last_observed_session':days[-1] if days else None,
  'missing_sessions':[d for d in sessions if d not in set(days)],'missing_sessions_classified_as_prelisting':False,'synthetic_source_rows_created':0}
def validate_packet(p,code,sessions):
 assert p['instrument']==code and p['window']==[START,END];sym=symbol(code)
 facts=calendar_facts(p['bars'],sessions)
 for r in p['bars']:
  assert set(r)==set(BAR) and r['code']==sym and START<=r['date']<=END
  assert r['adjustflag']=='3' and r['tradestatus'] in ('0','1') and r['isST'] in ('0','1')
  for k in ('open','high','low','close','preclose','volume','amount'):
   if r[k]:quantity(r[k])
  if r['tradestatus']=='1':
   assert all(r[k] and quantity(r[k])>0 for k in ('open','high','low','close','preclose','volume'))
   assert D(r['low'])<=min(D(r['open']),D(r['close']))<=max(D(r['open']),D(r['close']))<=D(r['high'])
 seen=set()
 for r in p['distributions']:
  assert set(r)==set(DIV) and r['code']==sym and START<=canonical_day(r['dividOperateDate'])<=END
  assert r['dividOperateDate'][:4] in ('2024','2025') and digest(r) not in seen;seen.add(digest(r))
  for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
   if r[k]:quantity(r[k])
 for r in p['adjustments']:
  assert set(r)==set(ADJ) and r['code']==sym and START<=canonical_day(r['dividOperateDate'])<=END
  for k in ADJ[2:]:
   if r[k]:assert D(r[k]).is_finite() and D(r[k])>0
 return facts

def reconstruct_dividends(fields,rows,code,year):
 accepted=[];quarantine=[];seen=set()
 for r in dictrows(fields,rows,DIV):
  assert r['code']==symbol(code);day=r['dividOperateDate']
  if not day:quarantine.append({'reason':'MISSING_OPERATE_DATE','record':r});continue
  assert canonical_day(day)[:4]==str(year)
  if day>END:quarantine.append({'reason':'AFTER_CAPTURE_CUTOFF','record':r});continue
  if day<START:quarantine.append({'reason':'BEFORE_CAPTURE_WINDOW','record':r});continue
  for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
   if r[k]:quantity(r[k])
  assert digest(r) not in seen;seen.add(digest(r));accepted.append(r)
 return accepted,quarantine

def fresh_projection(code,payloads,receipts,requestsha):
 distributions=[];quarantine=[]
 for year in (2024,2025):
  v=payloads['dividend'+str(year)];a,q=reconstruct_dividends(v['fields'],v['rows'],code,year);distributions+=a;quarantine+=q
 return {'instrument':code,'window':[START,END],'bars':dictrows(payloads['daily']['fields'],payloads['daily']['rows'],BAR),
  'distributions':distributions,'quarantine':quarantine,'adjustments':dictrows(payloads['adjustments']['fields'],payloads['adjustments']['rows'],ADJ),
  'source_query_receipts':receipts,'provenance':{'kind':'JOURNALED_PRE2026_RAW_SOURCE','request_sha256':requestsha,'query_end':END,'calendar_complete_not_assumed':True}}

def raw_core(p):
 return hashlib.sha256(json.dumps([[r['date'],r['code'],*[str(D(r[k]).normalize()) if r[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']] for r in p['bars']],separators=(',',':')).encode()).hexdigest()
def authenticate_request(repo,base,requestfile,expected,targetsfile):
 assert sha(requestfile)==expected;r=read(requestfile)
 assert r['status']=='FROZEN_VALUE_MOMENTUM_RAW_SOURCE_REQUEST' and r['candidate']=='szse_value_momentum_equal' and r['window']==[START,END]
 assert r['fresh_codes']==FRESH and [s['directory'] for s in r['reuse_sources']]==SOURCES
 assert r['maximum_new_query_reservations']==28 and r['max_attempts_per_query']==1 and r['maximum_consecutive_failed_fresh_codes']==3 and r['maximum_cross_restart_administrative_login_attempts']==3 and r['socket_timeout_seconds']==20
 assert r['source_admission_separate'] is True and r['portfolio_returns_computed'] is False and r['2026_market_values_queried'] is False
 assert sha(repo/r['protocol_file'])==r['protocol_sha256']
 for field in ('method_code_sha256','screen_files_sha256'):
  for f,h in r[field].items():assert not Path(f).is_absolute() and '..' not in Path(f).parts and sha(repo/f)==h,(field,f)
 audit=read(repo/'experiments/qlib/szse-value-momentum-independent-audit.json');screen=read(repo/'experiments/qlib/szse-value-momentum-pre2026-results.json')
 assert audit['summary_sha256']==r['screen_files_sha256']['experiments/qlib/szse-value-momentum-pre2026-results.json'] and audit['development_gate_passes_independently'] is True and audit['selected_development_lead']=='szse_value_momentum_equal'
 assert screen['selected_development_lead']=='szse_value_momentum_equal' and screen['2026_market_values_queried'] is False
 assert sha(targetsfile)==r['target_sha256'];targets=read(targetsfile)['szse_value_momentum_equal']
 codes=sorted({c for t in targets.values() for c in t['weights']});assert len(targets)==24 and len(codes)==103 and codes==r['codes']
 assert set(r['reuse_routes']).isdisjoint(FRESH) and set(r['reuse_routes'])|set(FRESH)==set(codes) and len(r['reuse_routes'])==96
 inventory=read(repo/'experiments/qlib/szse-value-momentum-raw-source-inventory.json')
 assert not inventory['conflicting_codes'] and inventory['names']==103 and inventory['missing_codes']==FRESH and inventory['target_sha256']==r['target_sha256']
 caches={};sessions=None;routes={};calendar_hashes={};revision_questions=[]
 for entry in r['reuse_sources']:
  name=entry['directory'];directory=base/name;assert sha(directory/'manifest.json')==entry['manifest_sha256']==inventory['source_manifest_sha256'][name]
  m=read(directory/'manifest.json');assert m['window']==[START,END] and sha(directory/'calendar.json')==m['calendar_sha256']
  current=read(directory/'calendar.json')['sessions'];assert current==sorted(set(current)) and len(current)==486 and [current[0],current[-1]]==[START,END]
  if sessions is not None:assert sessions==current
  sessions=current;calendar_hashes[name]=m['calendar_sha256'];caches[name]=(directory,m)
  for code in codes:
   if code in m['per_code_sha256'] and code not in routes:routes[code]={'directory':name,'packet_sha256':m['per_code_sha256'][code]}
 assert routes==r['reuse_routes']
 original_packets={};original_hashes={}
 for code in codes:
  choices=[];core_hashes=set();distribution_versions=defaultdict(dict);distribution_sets={}
  for name,(directory,m) in caches.items():
   if code not in m['per_code_sha256']:continue
   f=directory/'codes'/(code+'.json');h=sha(f);assert h==m['per_code_sha256'][code];p=read(f);facts=validate_packet(p,code,sessions)
   assert facts['full_explicit_calendar_covered'] is True;core=raw_core(p);core_hashes.add(core)
   choices.append((name,h,core));original_hashes[str(f)]=h;distribution_sets[name]={'packet_sha256':h,'row_set_sha256':digest(sorted(p['distributions'],key=digest)),'ex_dates':[row['dividOperateDate'] for row in p['distributions']]}
   for row in p['distributions']:distribution_versions[row['dividOperateDate']][digest(row)]={'source_directory':name,'packet_sha256':h,'record':row}
   if name==routes[code]['directory']:original_packets[code]=(f,p)
  assert len(core_hashes)<=1,(code,'raw price core conflict')
  stated=inventory['items'][code];assert stated['priority_route']==(routes[code]['directory'] if code in routes else None)
  assert {(c['source_directory'],c['source_sha256'],c['raw_core_sha256']) for c in stated['choices']}==set(choices)
  if len({v['row_set_sha256'] for v in distribution_sets.values()})>1:revision_questions.append({'instrument':code,'classification':'CROSS_CACHE_CORPORATE_ROW_SET_DIFFERS_REVIEW_REQUIRED','source_row_sets':distribution_sets})
  for day,versions in distribution_versions.items():
   if len(versions)>1:revision_questions.append({'instrument':code,'ex_date':day,'different_source_rows':list(versions.values()),'resolution':'PRIMARY_SOURCE_REVIEW_REQUIRED_NO_CACHE_REWRITE'})
 return r,targets,sessions,calendar_hashes,original_packets,original_hashes,revision_questions

def validate_identity(identity,requestsha):
 assert set(identity)=={'source','instrument','component','parameters','raw_development_request_sha256'}
 assert identity['source']=='BaoStock' and identity['instrument'] in FRESH and identity['raw_development_request_sha256']==requestsha
 assert identity['component'] in PARAMS and identity['parameters']==PARAMS[identity['component']]
def query_payload(folder,response,receipt,root):
 for key,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
  assert receipt[key+'_file']==str((folder/name).relative_to(root)) and receipt[key+'_sha256']==sha(folder/name)
 assert response['status']=='CAPTURED';envelope=response['payload'];assert envelope['fields']==['provider_response'] and len(envelope['rows'])==1
 v=envelope['rows'][0];assert v['initial_error_code']==v['final_error_code']=='0' and v['iteration_error_type'] is None and v['iteration_error'] is None
 return v

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('capture-dir','source-root','repo-root','request','expected-request-sha256','targets','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
 root=Path(a.capture_dir);base=Path(a.source_root);repo=Path(a.repo_root);out=Path(a.output);requestfile=Path(a.request)
 assert not out.exists()
 r,target,sessions,calendar_hashes,originals,original_hashes,revisions=authenticate_request(repo,base,requestfile,a.expected_request_sha256,Path(a.targets))
 if a.preflight_only:print('Independent source preflight:96 authenticated original packets,5 calendars,103 target names; no output/network/ROI');return 0
 m=read(root/'manifest.json');assert (root/'request.json').read_bytes()==requestfile.read_bytes() and m['request_sha256']==sha(requestfile)
 assert m['status']=='VALUE_MOMENTUM_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE' and m['window']==[START,END]
 assert m['target_sha256']==r['target_sha256'] and sha(root/'calendar.json')==m['calendar_sha256']
 assert read(root/'calendar.json')=={'sessions':sessions,'source_calendars':calendar_hashes}
 assert m['source_units']=={'price':'CNY/share','volume':'shares','amount':'CNY'}
 for flag in ('missing_rows_synthesized','admitted_for_account_replay','new_2026_market_queries','historical_arrival_verified','portfolio_return_computed','objective_achieved'):assert m[flag] is False
 assert m['corporate_action_completeness_verified'] is False and m['SDK_decoded_responses_not_TCP_wire'] is True and m['raw_quarantine_or_provenance_may_reference_later_dates'] is True
 assert m['per_code_sha256']==read(root/'progress.json') and m['errors_sha256']==read(root/'errors.json')
 assert not set(m['per_code_sha256'])&set(m['errors_sha256']) and not set(m['pending_codes'])&(set(m['per_code_sha256'])|set(m['errors_sha256']))
 assert sorted(set(m['per_code_sha256'])|set(m['errors_sha256'])|set(m['pending_codes']))==r['codes']
 assert m['names']==len(m['per_code_sha256']) and m['requested_names']==103 and m['reuse_routes']==r['reuse_routes'] and m['fresh_codes']==FRESH
 assert {f.stem for f in (root/'codes').glob('*.json')}==set(m['per_code_sha256'])
 queries={};vendor_outcomes=[];response_counts=Counter();journal_hashes={}
 for d in sorted((root/'queries').iterdir()) if (root/'queries').exists() else []:
  identity=read(d/'request.json');validate_identity(identity,sha(requestfile));assert d.name==digest(identity)
  assert sorted(f.name for f in d.iterdir())==['request.json','reserved-1.json','response-1.json']
  reserved=read(d/'reserved-1.json');response=read(d/'response-1.json');assert reserved['identity_sha256']==d.name and reserved['attempt']==1
  assert datetime.fromisoformat(reserved['reserved_at_utc']).utcoffset().total_seconds()==0
  assert response['identity_sha256']==d.name and response['reservation_sha256']==sha(d/'reserved-1.json')
  status=response['status'];assert status in ('CAPTURED','SOURCE_ERROR')
  if status=='CAPTURED':
   assert response['payload_sha256']==digest(response['payload']);envelope=response['payload'];assert envelope['fields']==['provider_response'] and len(envelope['rows'])==1
   v=envelope['rows'][0];outcome={k:v[k] for k in ('initial_error_code','initial_error_msg','final_error_code','final_error_msg','iteration_error_type','iteration_error')}
  else:outcome={k:response[k] for k in ('error_type','error')}
  key=(identity['instrument'],identity['component']);assert key not in queries;queries[key]=(d,response);response_counts[status]+=1
  for f in d.iterdir():journal_hashes[str(f.relative_to(root))]=sha(f)
  vendor_outcomes.append({'instrument':key[0],'component':key[1],'status':status,'outcome':outcome,'response_sha256':sha(d/'response-1.json')})
 assert len(queries)==len(list(root.rglob('reserved-*.json')))==m['query_reservations_consumed']<=28
 assert m['maximum_new_query_reservations']==28
 totals=Counter();calendars={};packets={};fresh_inputs={};reuse_counts=Counter();quarantines=[];noncash=[];corporate_questions=[];adjustment_questions=[];distribution_questions=[];reference_questions=[];status_rows=[];formation_questions=[];tick_questions=[];volume_questions=[]
 for code,h in m['per_code_sha256'].items():
  path=root/'codes'/(code+'.json');assert sha(path)==h;packet=read(path);packets[code]=packet
  if code in originals:
   original,_=originals[code];assert path.read_bytes()==original.read_bytes() and h==r['reuse_routes'][code]['packet_sha256'];reuse_counts[r['reuse_routes'][code]['directory']]+=1
  else:
   assert code in FRESH and set(packet['source_query_receipts'])==set(PARAMS)
   payloads={k:query_payload(*queries[(code,k)],packet['source_query_receipts'][k],root) for k in PARAMS}
   expected=fresh_projection(code,payloads,packet['source_query_receipts'],sha(requestfile));assert packet==expected,(code,'SDK-to-packet projection')
   fresh_inputs[code]=(payloads,packet['source_query_receipts'],expected)
  diagnostic=validate_packet(packet,code,sessions);assert diagnostic==m['calendar_diagnostics'][code];calendars[code]=diagnostic|{'extra_sessions':[],'packet_sha256':h,'classification':'FULL_EXPLICIT_CALENDAR' if diagnostic['full_explicit_calendar_covered'] else 'PARTIAL_UNCLASSIFIED_NO_IPO_INFERENCE'}
  byday={v['date']:v for v in packet['bars']};divdays={v['dividOperateDate'] for v in packet['distributions']};adjdays={v['dividOperateDate'] for v in packet['adjustments']}
  previous=None;previousday=None
  for row in packet['bars']:
   if row['isST']=='1':status_rows.append({'instrument':code,'day':row['date'],'packet_sha256':h})
   if row['tradestatus']=='1':
    if D(row['volume'])!=D(row['volume']).to_integral_value():volume_questions.append({'instrument':code,'day':row['date'],'volume':row['volume'],'packet_sha256':h})
    for k in ('open','high','low','close','preclose'):
     if D(row[k])!=D(row[k]).quantize(D('.01')):tick_questions.append({'instrument':code,'day':row['date'],'field':k,'value':row[k],'packet_sha256':h})
   if previous is not None and row['preclose'] and D(row['preclose'])>0 and abs(D(row['preclose'])-previous)>D('.005') and row['date'] not in divdays:
    reference_questions.append({'instrument':code,'day':row['date'],'previous_observed_day':previousday,'previous_close':str(previous),'preclose':row['preclose'],'packet_sha256':h,'action':'UNEXPLAINED_REFERENCE_CHANGE_NO_CASH_INFERENCE'})
   if row['close'] and D(row['close'])>0:previous=D(row['close']);previousday=row['date']
  for execution,t in target.items():
   if code in t['weights']:
    for role,day in (('formation',t['as_of']),('execution',execution)):
     row=byday.get(day)
     if row is None or row['tradestatus']!='1' or row['isST']!='0':formation_questions.append({'instrument':code,'execution':execution,'role':role,'day':day,'tradestatus':row['tradestatus'] if row else None,'isST':row['isST'] if row else None,'packet_sha256':h})
  for q in packet['quarantine']:quarantines.append({'instrument':code,'packet_sha256':h,'quarantine_sha256':digest(q),'entry':q})
  same_day_counts=Counter(row['dividOperateDate'] for row in packet['distributions'])
  for row in packet['distributions']:
   reasons=[]
   if same_day_counts[row['dividOperateDate']]>1:reasons.append('MULTIPLE_SOURCE_ROWS_SAME_EX_DATE_REQUIRE_REVISION_RESOLUTION')
   if D(row['dividStocksPs'] or '0')>0 or D(row['dividReserveToStockPs'] or '0')>0:noncash.append({'instrument':code,'packet_sha256':h,'source_row_sha256':digest(row),'record':row})
   if not row['dividCashPsBeforeTax'] or not row['dividStocksPs']:reasons.append('MISSING_CASH_OR_STOCK_COMPONENT')
   if not row['dividReserveToStockPs']:reasons.append('BLANK_CAPITAL_COMPONENT_REQUIRES_EXPLICIT_SOURCE_INTERPRETATION')
   for k in ('dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate'):
    if row[k]:
     canonical_day(row[k])
     if row[k]>END:reasons.append('METADATA_DATE_AFTER_CUTOFF:'+k)
    elif k in ('dividPlanDate','dividRegistDate'):reasons.append('MISSING_EVENT_DATE:'+k)
   if row['dividRegistDate'] and row['dividRegistDate'] not in sessions:reasons.append('RECORD_DATE_NOT_EXPLICIT_SESSION')
   if row['dividOperateDate'] not in sessions:reasons.append('EX_DATE_NOT_EXPLICIT_SESSION')
   if reasons:corporate_questions.append({'instrument':code,'packet_sha256':h,'source_row_sha256':digest(row),'record':row,'questions':reasons})
  for day in sorted(adjdays-divdays):
   i=sessions.index(day) if day in sessions else None;nearby=[d for d in divdays if i is not None and d in sessions and abs(sessions.index(d)-i)==1]
   adjustment_questions.append({'instrument':code,'day':day,'packet_sha256':h,'adjustment_records':[v for v in packet['adjustments'] if v['dividOperateDate']==day],'adjacent_distribution_dates':sorted(nearby),'classification':'ADJACENCY_REVIEW_REQUIRED' if nearby else 'NO_DISTRIBUTION_SOURCE_REVIEW_REQUIRED'})
  for day in sorted(divdays-adjdays):distribution_questions.append({'instrument':code,'day':day,'packet_sha256':h,'adjacent_adjustment_dates':sorted(d for d in adjdays if day in sessions and d in sessions and abs(sessions.index(d)-sessions.index(day))==1)})
  for k,f in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[k]+=len(packet[f])
 assert dict(totals)==m['totals'] and set(calendars)==set(m['calendar_diagnostics'])
 errors={}
 for code,h in m['errors_sha256'].items():
  f=root/'errors'/(code+'.json');assert sha(f)==h;v=read(f);assert v['instrument']==code and v['request_sha256']==sha(requestfile) and v['raw_responses_retained'] is True;errors[code]={'sha256':h,'record':v}
 complete=m['names']==103 and not errors and not m['pending_codes']
 if complete:assert len(queries)==28 and response_counts=={'CAPTURED':28} and len(fresh_inputs)==7 and sum(reuse_counts.values())==96
 administrative=[]
 for n,f in enumerate(sorted(root.glob('login-reserved-*.json')),1):
  assert n<=3 and f.name==f'login-reserved-{n}.json' and read(f)=={'attempt':n,'request_sha256':sha(requestfile)}
  reply=root/f'login-response-{n}.json';logout=root/f'logout-response-{n}.json';assert reply.exists() and logout.exists()
  administrative.append({'attempt':n,'reservation_sha256':sha(f),'response_sha256':sha(reply),'response':read(reply),'logout_sha256':sha(logout),'logout':read(logout)})
 if queries:assert administrative
 negatives={};reference=next(iter(packets));original=packets[reference]
 for mode in ('bar_issuer','future_bar','duplicate_bar','status','negative_volume','ohlc'):
  v=copy.deepcopy(original)
  if mode=='bar_issuer':v['bars'][0]['code']='sz.999999'
  elif mode=='future_bar':v['bars'][-1]['date']='2026-01-05'
  elif mode=='duplicate_bar':v['bars'].append(copy.deepcopy(v['bars'][-1]))
  elif mode=='status':v['bars'][0]['tradestatus']='UNKNOWN'
  elif mode=='negative_volume':v['bars'][0]['volume']='-1'
  else:next(r for r in v['bars'] if r['tradestatus']=='1')['high']='0'
  try:validate_packet(v,reference,sessions)
  except (AssertionError,ValueError):negatives[mode]=True
  else:raise AssertionError('semantic source mutation accepted:'+mode)
 if fresh_inputs:
  code=next(iter(fresh_inputs));payloads,receipts,expected=fresh_inputs[code]
  for mode in ('fresh_price_rewrite','quarantine_rewrite','provenance_rewrite','receipt_rewrite'):
   v=copy.deepcopy(expected)
   if mode=='fresh_price_rewrite':v['bars'][0]['close']='999'
   elif mode=='quarantine_rewrite':v['quarantine'].append({'reason':'FORGED','record':{}})
   elif mode=='provenance_rewrite':v['provenance']['query_end']='2026-10-20'
   else:v['source_query_receipts']['daily']['response_sha256']='0'*64
   try:assert v==fresh_projection(code,payloads,receipts,sha(requestfile))
   except AssertionError:negatives[mode]=True
   else:raise AssertionError('fresh source projection mutation accepted:'+mode)
  identity=read(queries[(code,'daily')][0]/'request.json');identity['parameters']['end_date']='2026-10-20'
  try:validate_identity(identity,sha(requestfile))
  except AssertionError:negatives['future_query_scope']=True
  else:raise AssertionError('future query mutation accepted')
 for f,h in original_hashes.items():assert sha(f)==h
 assert sha(requestfile)==a.expected_request_sha256
 result={'status':'INDEPENDENT_FIXED_COMPOSITE_RAW_SOURCE_CAPTURE_RECONSTRUCTED_ADMISSION_SEPARATE','audit_code_sha256':sha(__file__),'request_sha256':sha(requestfile),'capture_manifest_sha256':sha(root/'manifest.json'),
  'captured_names':m['names'],'capture_complete':complete,'reuse_byte_identical_counts':dict(reuse_counts),'original96_source_packets_changed':False,
  'all5_authenticated_cache_calendars_identical_486':True,'source_query_identities':len(queries),'maximum_new_query_reservations':28,'journal_artifact_sha256':journal_hashes,'source_query_status_counts':dict(response_counts),'vendor_outcomes_preserved':vendor_outcomes,
  'totals':dict(totals),'calendar_diagnostics':calendars,'incomplete_calendars':{c:d for c,d in calendars.items() if not d['full_explicit_calendar_covered']},'all_extra_dates':[],
  'quarantines':quarantines,'cross_cache_distribution_revision_questions':revisions,'noncash_distributions_requiring_primary_review':noncash,'other_corporate_source_questions':corporate_questions,
  'adjustments_without_same_day_distribution':adjustment_questions,'distributions_without_same_day_adjustment':distribution_questions,'unexplained_raw_preclose_changes':reference_questions,
  'isST_source_rows':status_rows,'formation_execution_status_questions':formation_questions,'noninteger_volume_rows':volume_questions,'active_price_fields_off_cent_tick':tick_questions,
  'capture_errors':errors,'pending_codes':m['pending_codes'],'capture_stop':{'sha256':sha(root/'stopped.json'),'record':read(root/'stopped.json')} if (root/'stopped.json').exists() else None,'administrative_sessions':administrative,'semantic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
  'manifest_explicit_corporate_completeness_false':m.get('corporate_action_completeness_verified') is False,
  'sdk_decoded_responses_not_TCP_wire':True,'original_provenance_and_quarantine_may_contain_later_dates':True,'source_units':m['source_units'],'raw_source_admitted_for_account_replay':False,
  'corporate_action_completeness_verified':False,'primary_corporate_or_lifecycle_review_complete':False,'missing_sessions_classified_as_prelisting':False,'synthetic_source_rows_created':0,
  'imports_project_code':False,'new_source_queries_performed':0,'new_2026_market_queries':False,'portfolio_returns_computed':False,'objective_achieved':False,
  'limitations':['Original96 receipts/provenance are authenticated unchanged by exact packet bytes and all matching cached raw-price cores; only7fresh SDK chains are independently projected from28 current captured financial queries.',
   'Issuer/status/raw numerics and explicit calendar membership are source-integrity checks, not historical truth, ownership/IPO/listing classification, legal tax proof, full corporate-action coverage or account admission.',
   'Missing rows remain partial and unclassified; exact/adjacent action-factor differences and preclose changes are questions only and never synthesize cash/shares.',
   'Accepted bars and action ex/adjustment dates are bounded through2025-12-31. Quarantined/source-provenance metadata can mention later dates and does not become an investment input.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independent raw capture audit',m['names'],'names',len(queries),'queries; incomplete calendars',len(result['incomplete_calendars']),'; admission false; no ROI')
 return 0
if __name__=='__main__':raise SystemExit(main())
