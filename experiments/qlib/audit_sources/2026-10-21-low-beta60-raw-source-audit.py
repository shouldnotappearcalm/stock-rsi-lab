"""Stdlib-only verification of captured pre2026 sources; never portfolio ROI."""
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser()
for name in ('capture-dir','source-root','targets','output'):p.add_argument('--'+name,required=True)
a=p.parse_args();root=Path(a.capture_dir);sources=Path(a.source_root);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical_sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
requestfile=repo/'experiments/qlib/low-beta60-raw-source-request.json'
assert sha(requestfile)=='8a3da07192a1c3901997a8f57a2216b268bbf3e47082d63280e1188518abd493'
r=read(requestfile);m=read(root/'manifest.json');target=read(a.targets)['low_beta60']
assert (root/'request.json').read_bytes()==requestfile.read_bytes()
assert all(sha(repo/f)==h for f,h in r['method_code_sha256'].items())
assert all(sha(repo/f)==h for f,h in r['screen_files_sha256'].items())
assert sha(a.targets)==r['target_sha256']==m['target_sha256']
codes=sorted({c for v in target.values() for c in v['weights']})
assert codes==r['codes'] and len(target)==24 and len(codes)==69
assert r['window']==m['window']==['2023-12-29','2025-12-31']
assert m['request_sha256']==sha(requestfile)
assert sha(root/'calendar.json')==m['calendar_sha256']
calendar=read(root/'calendar.json')['sessions'];session_set=set(calendar)
assert calendar==sorted(session_set) and len(calendar)==486
assert calendar[0]=='2023-12-29' and calendar[-1]=='2025-12-31'
assert m['per_code_sha256']==read(root/'progress.json') and m['errors_sha256']==read(root/'errors.json')
assert set(m['per_code_sha256']).isdisjoint(m['errors_sha256'])
assert sorted(set(m['per_code_sha256'])|set(m['errors_sha256'])|set(m['pending_codes']))==codes
assert m['names']==len(m['per_code_sha256']) and m['requested_names']==69
assert m['reuse_routes']==r['reuse_routes'] and m['fresh_codes']==r['fresh_codes']
assert len(r['reuse_routes'])==61 and len(r['fresh_codes'])==8
inventory=read(repo/'experiments/qlib/low-beta60-raw-source-inventory.json')
assert inventory['target_sha256']==r['target_sha256'] and not inventory['raw_core_conflict_codes']
old_manifests={}
for directory,h in inventory['source_manifests_sha256'].items():
 d=sources/directory;assert sha(d/'manifest.json')==h
 old_manifests[directory]=read(d/'manifest.json')
reference=sources/r['reference_calendar_file']
assert sha(reference)==r['reference_calendar_sha256']==inventory['reference_calendar_sha256']
assert [d for d in read(reference)['sessions'] if r['window'][0]<=d<=r['window'][1]]==calendar
assert read(root/'calendar.json')=={'sessions':calendar,'origin_sha256':sha(reference),'clipped_to':r['window']}
assert sha(repo/r['protocol_file'])==r['protocol_sha256']

bar_fields=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
div_fields=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
adjust_fields=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
parameters={'daily':{'start_date':'2023-12-29','end_date':'2025-12-31','frequency':'d','adjustflag':'3'},
 'dividend2024':{'year':'2024','yearType':'operate'},'dividend2025':{'year':'2025','yearType':'operate'},
 'adjustments':{'start_date':'2023-12-29','end_date':'2025-12-31'}}
queries={};response_status=Counter();artifact_count=0
for d in sorted((root/'queries').iterdir()) if (root/'queries').exists() else []:
 identity=read(d/'request.json');assert d.name==canonical_sha(identity)
 assert identity['source']=='BaoStock' and identity['instrument'] in r['fresh_codes']
 component=identity['component'];assert component in parameters and identity['parameters']==parameters[component]
 assert identity['raw_development_request_sha256']==sha(requestfile)
 assert sorted(v.name for v in d.iterdir())==['request.json','reserved-1.json','response-1.json']
 reserved=read(d/'reserved-1.json');response=read(d/'response-1.json')
 assert reserved['attempt']==1 and reserved['identity_sha256']==d.name
 assert response['identity_sha256']==d.name and response['reservation_sha256']==sha(d/'reserved-1.json')
 if response['status']=='CAPTURED':assert response['payload_sha256']==canonical_sha(response['payload'])
 else:assert response['status']=='SOURCE_ERROR'
 key=(identity['instrument'],component);assert key not in queries
 queries[key]=(d,response);response_status[response['status']]+=1;artifact_count+=3
assert len(queries)==len(list(root.rglob('reserved-*.json')))==m['query_reservations_consumed']<=32
assert m['maximum_new_query_reservations']==r['maximum_new_query_reservations']==32

def query_payload(code,component,receipt):
 d,response=queries[(code,component)]
 for prefix,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
  assert receipt[prefix+'_file']==str((d/name).relative_to(root))
  assert receipt[prefix+'_sha256']==sha(d/name)
 assert response['status']=='CAPTURED';envelope=response['payload']
 assert envelope['fields']==['provider_response'] and len(envelope['rows'])==1
 v=envelope['rows'][0]
 assert v['initial_error_code']==v['final_error_code']=='0' and v['iteration_error_type'] is None
 return v['fields'],v['rows']

def dict_rows(fields,rows,expected):
 assert fields==expected and all(len(row)==len(fields) for row in rows)
 return [dict(zip(fields,row)) for row in rows]

totals=Counter();incomplete={};st_rows=[];noncash=[];unmatched_adjustments=[];unmatched_distributions=[]
formation_status=[];noninteger_volume=[];off_tick=[];reuse_counts=Counter()
for code,h in m['per_code_sha256'].items():
 path=root/'codes'/(code+'.json');assert sha(path)==h;v=read(path)
 assert v['instrument']==code and v['window']==r['window']
 symbol=code[:2].lower()+'.'+code[2:]
 if code in r['reuse_routes']:
  route=r['reuse_routes'][code];old=sources/route['directory']/'codes'/(code+'.json')
  assert route['packet_sha256']==old_manifests[route['directory']]['per_code_sha256'][code]==sha(old)
  original=read(old);assert original['instrument']==code
  assert original['window'][0]<=r['window'][0]<=r['window'][1]<=original['window'][1]
  clipped={'instrument':code,'window':r['window']}
  for field,day_field in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
   clipped[field]=[row for row in original[field] if r['window'][0]<=row[day_field]<=r['window'][1]]
  clipped['quarantine']=[row for row in original['quarantine'] if not row['record'].get('dividOperateDate') or r['window'][0]<=row['record']['dividOperateDate']<=r['window'][1]]
  clipped['provenance']={'kind':'AUTHENTICATED_CLIPPED_REUSE',
   'original_sha256':sha(old),'original_source_directory':route['directory'],
   'original_window':original['window'],'source_contains_later_bytes':original['window'][1]>r['window'][1],
   'original_provenance':original.get('provenance'),
   'original_source_query_receipts':original.get('source_query_receipts'),
   'historical_arrival_verified':False,'corporate_action_completeness_verified':False}
  assert v==clipped
  core=[]
  for row in clipped['bars']:
   core.append([row['date'],row['code'],*[str(Decimal(row[k]).normalize()) if row[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],row['tradestatus'],row['isST']])
  assert hashlib.sha256(json.dumps(core,separators=(',',':')).encode()).hexdigest()==route['pre2026_raw_core_sha256']
  reuse_counts[route['directory']]+=1
 else:
  assert code in r['fresh_codes'] and set(v['source_query_receipts'])==set(parameters)
  receipts=v['source_query_receipts']
  fields,rows=query_payload(code,'daily',receipts['daily'])
  assert v['bars']==dict_rows(fields,rows,bar_fields)
  distributions=[];quarantine=[]
  for year in (2024,2025):
   component='dividend'+str(year);fields,rows=query_payload(code,component,receipts[component])
   for item in dict_rows(fields,rows,div_fields):
    assert item['code']==symbol
    day=item['dividOperateDate']
    if not day:quarantine.append({'reason':'MISSING_OPERATE_DATE','record':item})
    else:
     assert date.fromisoformat(day).isoformat()==day and day[:4]==str(year)
     distributions.append(item)
  assert v['distributions']==distributions and v['quarantine']==quarantine
  fields,rows=query_payload(code,'adjustments',receipts['adjustments'])
  assert v['adjustments']==dict_rows(fields,rows,adjust_fields)
  assert v['provenance']['request_sha256']==sha(requestfile) and v['provenance']['query_end']=='2025-12-31'
 days=[row['date'] for row in v['bars']]
 assert days==sorted(set(days)) and set(days)<=session_set
 diagnostic={'full_explicit_calendar_covered':days==calendar,'observed_rows':len(days),
  'first_observed_session':days[0] if days else None,'last_observed_session':days[-1] if days else None,
  'missing_sessions':[d for d in calendar if d not in set(days)],
  'missing_sessions_classified_as_prelisting':False,'synthetic_source_rows_created':0}
 assert diagnostic==m['calendar_diagnostics'][code]
 if diagnostic['missing_sessions']:incomplete[code]=diagnostic
 by_day={row['date']:row for row in v['bars']}
 for row in v['bars']:
  assert row['code']==symbol and row['adjustflag']=='3'
  assert row['tradestatus'] in ('0','1') and row['isST'] in ('0','1')
  for key in ('open','high','low','close','preclose','volume','amount'):
   if row[key]:assert Decimal(row[key]).is_finite() and Decimal(row[key])>=0
  if row['tradestatus']=='1':
   assert all(row[k] and Decimal(row[k])>0 for k in ('open','high','low','close','preclose','volume'))
   assert Decimal(row['low'])<=min(Decimal(row['open']),Decimal(row['close']))<=max(Decimal(row['open']),Decimal(row['close']))<=Decimal(row['high'])
   if Decimal(row['volume'])!=Decimal(row['volume']).to_integral_value():noninteger_volume.append([code,row['date'],row['volume']])
   for field in ('open','high','low','close','preclose'):
    if Decimal(row[field])!=Decimal(row[field]).quantize(Decimal('.01')):off_tick.append([code,row['date'],field,row[field]])
  if row['isST']=='1':st_rows.append([code,row['date']])
 for execute,t in target.items():
  if code in t['weights']:
   row=by_day.get(t['as_of'])
   if row is None or row['tradestatus']!='1' or row['isST']!='0':
    formation_status.append({'instrument':code,'execution':execute,'formation':t['as_of'],
     'tradestatus':None if row is None else row['tradestatus'],'isST':None if row is None else row['isST']})
 div_days=set();adj_days=set()
 for row in v['distributions']:
  assert row['code']==symbol and '2023-12-29'<=row['dividOperateDate']<='2025-12-31'
  div_days.add(row['dividOperateDate'])
  if Decimal(row['dividStocksPs'] or '0')>0 or Decimal(row['dividReserveToStockPs'] or '0')>0:
   noncash.append({'instrument':code,'record':row,'packet_sha256':h})
 for row in v['adjustments']:
  assert row['code']==symbol and '2023-12-29'<=row['dividOperateDate']<='2025-12-31'
  adj_days.add(row['dividOperateDate'])
 for d in sorted(adj_days-div_days):unmatched_adjustments.append([code,d])
 for d in sorted(div_days-adj_days):unmatched_distributions.append([code,d])
 for key,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[key]+=len(v[field])
assert dict(totals)==m['totals']
for code,h in m['errors_sha256'].items():
 f=root/'errors'/(code+'.json');assert sha(f)==h
 v=read(f);assert v['instrument']==code and v['request_sha256']==sha(requestfile) and v['raw_responses_retained']
complete=len(m['per_code_sha256'])==69 and not m['errors_sha256'] and not m['pending_codes']
if complete:assert len(queries)==32 and response_status=={'CAPTURED':32} and sum(reuse_counts.values())==61
login_files=sorted(root.glob('login-reserved-*.json'))
assert 1<=len(login_files)<=3
administrative=[]
for n,reservation in enumerate(login_files,1):
 assert reservation.name==f'login-reserved-{n}.json'
 assert read(reservation)=={'attempt':n,'request_sha256':sha(requestfile)}
 response=root/f'login-response-{n}.json';logout=root/f'logout-response-{n}.json'
 assert response.exists() and logout.exists()
 administrative.append({'attempt':n,'reservation_sha256':sha(reservation),
  'response_sha256':sha(response),'response':read(response),'logout_sha256':sha(logout),'logout':read(logout)})
if complete:assert administrative[-1]['response']['error_code']=='0'
result={'status':'INDEPENDENT_PRE2026_RAW_SOURCE_CAPTURE_AUDIT_COMPLETE','audit_code_sha256':sha(__file__),
 'capture_manifest_sha256':sha(root/'manifest.json'),'request_sha256':sha(requestfile),
 'original_cache_may_include_later_bytes':True,'sdk_decoded_responses_not_tcp_wire':True,
 'captured_names':m['names'],'capture_complete':complete,'source_query_identities':len(queries),
 'journal_artifacts_verified':artifact_count,'response_status_counts':dict(response_status),
 'authenticated_clipped_reuse_counts':dict(reuse_counts),'totals':dict(totals),'incomplete_calendars':incomplete,
 'isST_source_rows':st_rows,'unsupported_or_missing_formation_status':formation_status,
 'noncash_distributions_requiring_review':noncash,'adjustments_without_distribution':unmatched_adjustments,
 'distributions_without_adjustment':unmatched_distributions,'noninteger_volume_rows':noninteger_volume,
 'active_price_fields_off_cent_tick':off_tick,'capture_errors':m['errors_sha256'],'pending_codes':m['pending_codes'],
 'original_source_packets_changed':False,'clipped_reuse_provenance_verified':True,'raw_source_admitted_for_account_replay':False,
 'primary_corporate_or_lifecycle_review_complete':False,'new_portfolio_returns_computed':False,
 '2026_market_queries':False,'objective_achieved':False,
 'administrative_sessions':administrative,'scope':'Own SDK-response/hash/packet/calendar and numeric-field verification; data retrieval not historical truth, PIT arrival, exact minute-volume, corporate tax basis or actual held-account admission'}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('raw source audit',m['names'],'names',len(queries),'queries','complete',complete,
 'calendar gaps',len(incomplete),'noncash',len(noncash),'ST formations',len(formation_status),
 'unmatched adjustments',len(unmatched_adjustments))
