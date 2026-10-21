"""Independent stdlib-only source provenance/assembly audit; never SDK/network/account.
Frozen request binding b8f0974b71414f00e916068f8f417b55a971824b26c90d1221782938190e8495.
Preflight reads authenticated prior sources only.
"""
import argparse,copy,hashlib,json,re
from collections import Counter
from datetime import date,datetime
from decimal import Decimal as D
from pathlib import Path
if not __debug__:raise RuntimeError('Do not disable assertions')
START,PRE,END='2023-12-29','2025-12-31','2026-10-20'
FORM='szse-value-momentum-formations-full-v2-20261021';OLD='szse-value-momentum-raw-dev-20261021';PROJ='szse-value-momentum-account-sources-20261021'
SOURCES=('low-beta60-raw-horizon-20261021','low-risk-raw-account-data-20261017','szse-value-raw-full-20261017','reversal-raw-full-20261017')
BAR=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
DIV=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
ADJ=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def same(a,b):assert digest(a)==digest(b),'typed JSON mismatch'
def safe(root,n):
 p=Path(n);assert not p.is_absolute() and '..' not in p.parts
 result=root/p;assert result.resolve().is_relative_to(root.resolve());return result
def day(s):assert isinstance(s,str) and date.fromisoformat(s).isoformat()==s;return s
def number(s):v=D(s);assert v.is_finite() and v>=0;return v
def symbol(c):assert re.fullmatch(r'SZ(?:000|001|002|003)\d{3}',c);return 'sz.'+c[2:]
def core(r):return [r['date'],r['code'],*[str(number(r[k]).normalize()) if r[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']]
def bars_valid(c,rows,start=START):
 ds=[]
 for r in rows:
  assert set(r)==set(BAR) and r['code']==symbol(c) and start<=day(r['date'])<=END
  assert r['adjustflag']=='3' and r['tradestatus'] in ('0','1') and r['isST'] in ('0','1')
  for k in ('open','high','low','close','preclose','volume','amount'):
   if r[k]:number(r[k])
  if r['tradestatus']=='1':
   assert all(r[k] and number(r[k])>0 for k in ('open','high','low','close','preclose','volume'))
   assert number(r['low'])<=min(number(r['open']),number(r['close']))<=max(number(r['open']),number(r['close']))<=number(r['high'])
  ds.append(r['date'])
 assert ds==sorted(set(ds))
def dividends(c,rows,year):
 accepted=[];quarantine=[];seen=set()
 for r in rows:
  assert set(r)==set(DIV) and r['code']==symbol(c)
  at=r['dividOperateDate']
  if not at:quarantine.append({'reason':'MISSING_OPERATE_DATE','record':copy.deepcopy(r)});continue
  assert day(at)[:4]==str(year)
  if not START<=at<=END:
   quarantine.append({'reason':'AFTER_EXTENSION_CUTOFF' if at>END else 'BEFORE_EXTENSION_WINDOW','record':copy.deepcopy(r)});continue
  for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
   if r[k]:number(r[k])
  assert digest(r) not in seen;seen.add(digest(r));accepted.append(copy.deepcopy(r))
 return accepted,quarantine
def adjustments(c,rows,start=START):
 seen=set()
 for r in rows:
  assert set(r)==set(ADJ) and r['code']==symbol(c) and start<=day(r['dividOperateDate'])<=END
  assert digest(r) not in seen;seen.add(digest(r))
def expected_dates(c,sessions):return [d for d in sessions if c!='SZ001389' or d>='2024-04-02']
def overlap(assembled,cache):
 assert assembled['instrument']==cache['instrument']
 a={r['date']:core(r) for r in assembled['bars']};b={r['date']:core(r) for r in cache['bars'] if START<=r['date']<=END}
 assert len(a)==len(assembled['bars']) and len(b)==sum(START<=r['date']<=END for r in cache['bars'])
 assert all(a[d]==b[d] for d in a.keys()&b.keys())
 lo=max(START,assembled['window'][0],cache['window'][0]);hi=min(END,assembled['window'][1],cache['window'][1])
 for k in ('distributions','adjustments'):same([r for r in assembled[k] if lo<=r['dividOperateDate']<=hi],[r for r in cache[k] if lo<=r['dividOperateDate']<=hi])
def compose(c,source,baseline,sessions,caches):
 assert source['instrument']==c
 p={'instrument':c,'window':[START,END]}
 if baseline is not None:assert baseline['instrument']==c and baseline['window']==[START,PRE]
 for k,f in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
  rows=source[k];assert all(source['window'][0]<=r[f]<=END for r in rows)
  if baseline is not None:
   if source['window'][0]<=START:
    old=[r for r in rows if r[f]<=PRE]
    same([core(r) for r in old],[core(r) for r in baseline[k]]) if k=='bars' else same(old,baseline[k])
   rows=baseline[k]+[r for r in rows if r[f]>PRE]
  p[k]=copy.deepcopy(rows)
 p['quarantine']=copy.deepcopy(baseline.get('quarantine',[]) if baseline else [])
 p['quarantine'].extend(copy.deepcopy([q for q in source.get('quarantine',[]) if baseline is None or not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']>PRE]))
 bars_valid(c,p['bars']);assert [r['date'] for r in p['bars']]==expected_dates(c,sessions),'missing source sessions'
 for year in (2024,2025,2026):
  rows=[r for r in p['distributions'] if r['dividOperateDate'][:4]==str(year)];a,q=dividends(c,rows,year);same(a,rows);assert not q
 assert all(START<=r['dividOperateDate']<=END for r in p['distributions']);adjustments(c,p['adjustments'])
 for v in caches:overlap(p,v)
 return p

def authenticate(base,repo,requestfile,expectedsha):
 assert expectedsha=='b8f0974b71414f00e916068f8f417b55a971824b26c90d1221782938190e8495' and sha(requestfile)==expectedsha;r=read(requestfile);bound={requestfile:expectedsha}
 assert set(r)==set('status candidate window maximum_source_reservations max_attempts_per_query maximum_consecutive_failed_codes maximum_administrative_login_attempts socket_timeout_seconds output_directory protocol_file baostock_version method_code_sha256 public_evidence_sha256 local_source_sha256 target_sha256 source_manifest_sha256 source_calendar_sha256 original_packet_sha256 codes cache_routes baseline_codes fresh_codes incremental_codes cold_codes source_calendar_sessions known_primary_bound_missing_sessions new_source_calls_before_method_freeze source_admitted_for_account_replay portfolio_returns_computed historical_arrival_verified full_corporate_actions_certified objective_achieved'.split())
 assert r['baostock_version']=='0.9.4' and r['source_calendar_sessions']==676 and r['known_primary_bound_missing_sessions']=={'SZ001389':60}
 assert r['new_source_calls_before_method_freeze']==0
 for k in ('source_admitted_for_account_replay','portfolio_returns_computed','historical_arrival_verified','full_corporate_actions_certified','objective_achieved'):assert r[k] is False
 required_methods={'scripts/capture_value_momentum_raw_extension.py','scripts/value_momentum_raw_extension_sources.py','scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_low_risk_raw_account_data.py','scripts/capture_illiquidity_raw_development.py','scripts/fundamental_query_journal.py','scripts/capture_frozen_target_development_data.py','experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-full-raw-inventory.py'}
 required_public={'experiments/qlib/szse-value-momentum-2026-target-v2-verification.json','experiments/qlib/szse-value-momentum-2026-target-v2-independent-audit.json','experiments/qlib/szse-value-momentum-2026-target-v2-receipt.json','experiments/qlib/szse-value-momentum-2026-targets.json','experiments/qlib/szse-value-momentum-full-raw-inventory.json','experiments/qlib/szse-value-momentum-full-raw-inventory-review.json','docs/research/szse-value-momentum-raw-extension-source-plan-2026-10-21.md'}
 required_local={OLD+'/manifest.json',OLD+'/calendar.json',PROJ+'/summary.json',PROJ+'/lifecycles.json',FORM+'/targets.json',FORM+'/receipt.json','szse-value-momentum-full-raw-inventory-20261021.json'}
 assert set(r['method_code_sha256'])==required_methods and set(r['public_evidence_sha256'])==required_public and set(r['local_source_sha256'])==required_local
 assert r['status']=='FROZEN_COMPOSITE_RAW_EXTENSION_SOURCE_REQUEST'  and r['candidate']=='szse_value_momentum_equal' and r['window']==[START,END]
 for k,v in {'maximum_source_reservations':362,'max_attempts_per_query':1,'maximum_consecutive_failed_codes':3,'maximum_administrative_login_attempts':1,'socket_timeout_seconds':20,'output_directory':'szse-value-momentum-raw-full-20261021','protocol_file':'docs/research/szse-value-momentum-raw-extension-source-plan-2026-10-21.md'}.items():assert r[k]==v
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  assert r[field]
  for n,h in r[field].items():
   f=safe(parent,n);assert sha(f)==h,n;bound[f]=h
 invfile=repo/'experiments/qlib/szse-value-momentum-full-raw-inventory.json';inv=read(invfile)
 assert invfile.read_bytes()==(base/'szse-value-momentum-full-raw-inventory-20261021.json').read_bytes()
 assert all(inv['semantic_negative_controls_passed'].values())
 review=read(repo/'experiments/qlib/szse-value-momentum-full-raw-inventory-review.json');assert review['ready_for_bounded_source_capture_design'] is True and review['capture_execution_authorized'] is False and review['inventory_sha256']==sha(invfile)
 assert inv['source_priority_fixed_before_inventory']==list(SOURCES) and not inv['cross_cache_raw_core_conflict_codes'] and not inv['original_pre2026_prefix_conflict_codes']
 assert inv['target_sha256']==r['target_sha256']==sha(base/FORM/'targets.json')
 audit=read(repo/'experiments/qlib/szse-value-momentum-2026-target-v2-independent-audit.json');receipt=read(base/FORM/'receipt.json')
 verification=read(repo/'experiments/qlib/szse-value-momentum-2026-target-v2-verification.json')
 assert verification['all34formations_independently_reconstructed'] is True and verification['old24target_and_receipt_bytes_identical'] is True
 assert verification['independent_audit_sha256']==sha(repo/'experiments/qlib/szse-value-momentum-2026-target-v2-independent-audit.json')
 assert (repo/'experiments/qlib/szse-value-momentum-2026-target-v2-receipt.json').read_bytes()==(base/FORM/'receipt.json').read_bytes()
 assert (repo/'experiments/qlib/szse-value-momentum-2026-targets.json').read_bytes()==(base/FORM/'targets.json').read_bytes()
 assert audit['receipt_sha256']==sha(base/FORM/'receipt.json') and audit['all_three_families_34_targets_reconstructed'] is True
 assert audit['original24_complete_receipts_and_family_targets_byte_exact'] is True and audit['imports_project_code'] is False and all(audit['semantic_negative_controls_rejected'].values())
 assert receipt['artifact_sha256']['targets.json']==r['target_sha256'] and receipt['account_replay_performed'] is False and receipt['2026_strategy_returns_queried'] is False
 targets=read(base/FORM/'targets.json');codes=sorted(set().union(*(set(t['weights']) for t in targets.values())))
 assert codes==r['codes'] and len(codes)==127 and len(targets)==34
 manifests={};sessions=None
 assert set(r['source_manifest_sha256'])==set(r['source_calendar_sha256'])==set(SOURCES)
 for n in SOURCES:
  root=base/n;f=root/'manifest.json';assert sha(f)==r['source_manifest_sha256'][n]==inv['source_manifest_sha256'][n];bound[f]=sha(f);m=read(f);manifests[n]=m
  f=root/'calendar.json';assert sha(f)==r['source_calendar_sha256'][n]==inv['source_calendar_sha256'][n]==m['calendar_sha256'];bound[f]=sha(f)
  ds=[d for d in read(f)['sessions'] if START<=day(d)<=min(m['window'][1],END)]
  if sessions is None:sessions=ds
  assert ds==[d for d in sessions if d<=min(m['window'][1],END)]
 assert sessions==sorted(set(sessions)) and len(sessions)==676 and [sessions[0],sessions[-1]]==[START,END]
 assert [d for d in sessions if d<=PRE]==read(base/OLD/'calendar.json')['sessions']
 old=read(base/OLD/'manifest.json');summary=read(base/PROJ/'summary.json');life=read(base/PROJ/'lifecycles.json')
 assert old['per_code_sha256']==r['original_packet_sha256'] and len(old['per_code_sha256'])==103
 assert sha(base/OLD/'manifest.json')==inv['original_pre2026_manifest_sha256'] and sha(base/PROJ/'summary.json')==inv['source_projection_summary_sha256']
 assert sha(base/PROJ/'lifecycles.json')==inv['lifecycle_sha256']==summary['artifact_sha256']['lifecycles.json']
 assert set(life)=={'SZ001389'} and life['SZ001389']['effective_date']=='2024-04-02' and life['SZ001389']['verified_primary_boundary'] is True
 baselines={};lineage={};caches={};cached={};routes={}
 for c,h in old['per_code_sha256'].items():
  f=base/OLD/'codes'/(c+'.json');assert sha(f)==h;bound[f]=h;p=read(f)
  assert p['instrument']==c and p['window']==[START,PRE] and [r['date'] for r in p['bars']]==[d for d in expected_dates(c,sessions) if d<=PRE]
  assert digest(p)==summary['original_packet_digests'][c];baselines[c]=p
  lineage[c]={'baseline':{'kind':'ORIGINAL_DEVELOPMENT_PACKET','file':str(f.relative_to(base)),'sha256':h}}
 for c in codes:
  item=inv['items'][c];choices=item['choices'];values=[];proofs=[]
  expected_sources=[n for n in SOURCES if c in manifests[n]['per_code_sha256']]
  assert [q['source_directory'] for q in choices]==expected_sources
  for choice in choices:
   n=choice['source_directory'];f=base/n/'codes'/(c+'.json');assert sha(f)==choice['source_packet_sha256']==manifests[n]['per_code_sha256'][c];bound[f]=sha(f);v=read(f)
   assert v['instrument']==c and v['window']==choice['window'];rows=[r for r in v['bars'] if START<=r['date']<=END];bars_valid(c,rows)
   assert [r['date'] for r in rows]==[d for d in expected_dates(c,sessions) if d<=min(v['window'][1],END)]
   for previous in values:overlap(v,previous)
   if c in baselines:overlap(baselines[c],v)
   values.append(v);proofs.append({'source_directory':n,'source_packet_sha256':choice['source_packet_sha256'],'source_window':v['window'],'original_provenance':v.get('provenance'),'original_source_query_receipts':v.get('source_query_receipts')})
  if not choices:assert item['priority_route'] is None;continue
  first=choices[0];assert item['priority_route']==first['source_directory'];caches[c]=values
  routes[c]={'source_directory':first['source_directory'],'source_packet_sha256':first['source_packet_sha256'],'complete_through_Oct20':first['complete_through_Oct20']}
  lineage.setdefault(c,{})['registered_caches']=proofs
  if c not in baselines:
   p={'instrument':c,'window':[START,PRE]}
   for k,f in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):p[k]=copy.deepcopy([row for row in values[0][k] if START<=row[f]<=PRE])
   p['quarantine']=copy.deepcopy([q for q in values[0].get('quarantine',[]) if not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']<=PRE])
   assert [row['date'] for row in p['bars']]==[d for d in sessions if d<=PRE];baselines[c]=p
   lineage[c]['baseline']={'kind':'CLIPPED_NEW_NAME_PRE2026_CACHE','source_directory':first['source_directory'],'source_packet_sha256':first['source_packet_sha256']}
  if first['complete_through_Oct20']:cached[c]=values[0];compose(c,values[0],baselines[c],sessions,values)
 fresh=[c for c in codes if c not in cached];incremental=[c for c in fresh if c in baselines];cold=[c for c in fresh if c not in baselines]
 assert len(cached)==15 and len(baselines)==114 and len(fresh)==112 and len(incremental)==99 and len(cold)==13 and 3*len(incremental)+5*len(cold)==362
 assert routes==r['cache_routes'] and fresh==r['fresh_codes'] and sorted(baselines)==r['baseline_codes'] and incremental==r['incremental_codes'] and cold==r['cold_codes']
 return r,codes,sessions,baselines,cached,caches,lineage,bound,targets

def specs(c,baselines):
 start='2026-01-01' if c in baselines else START
 return [('daily',{'start_date':start,'end_date':END,'frequency':'d','adjustflag':'3'},BAR)]+[(f'dividend{y}',{'year':str(y),'yearType':'operate'},DIV) for y in ((2026,) if c in baselines else (2024,2025,2026))]+[('adjustments',{'start_date':start,'end_date':END},ADJ)]
def validate_identity(v,r,requestsha,baselines):
 assert set(v)=={'source','instrument','component','parameters','composite_raw_extension_request_sha256'}
 assert v['source']=='BaoStock' and v['instrument'] in r['fresh_codes'] and v['composite_raw_extension_request_sha256']==requestsha
 expected={k:parameters for k,parameters,_ in specs(v['instrument'],baselines)}
 assert v['component'] in expected and v['parameters']==expected[v['component']]
def successful(v):return v['initial_error_code']==v['final_error_code']=='0' and v['iteration_error_type'] is None and v['iteration_error'] is None
def projection(c,payloads,receipts,baselines):
 start='2026-01-01' if c in baselines else START;v={'instrument':c,'window':[start,END]}
 for component,parameters,fields in specs(c,baselines):
  q=payloads[component];assert successful(q) and q['fields']==fields and all(isinstance(row,list) and len(row)==len(fields) for row in q['rows'])
  rows=[dict(zip(fields,row)) for row in q['rows']]
  if component=='daily':bars_valid(c,rows,start);v['bars']=rows;v['distributions']=[];v['quarantine']=[]
  elif component=='adjustments':adjustments(c,rows,start);v['adjustments']=rows
  else:
   accepted,excluded=dividends(c,rows,parameters['year']);v['distributions'].extend(accepted);v['quarantine'].extend(excluded)
 v['source_query_receipts']=receipts
 return v

def with_provenance(c,source,p,baselines,lineage,requestsha):
 p['provenance']={'kind':'AUTHENTICATED_CACHE_SUFFIX_WITH_PRESERVED_PREFIX' if c not in fresh_set else 'PRESERVED_PREFIX_JOURNALED_SUFFIX' if c in baselines else 'JOURNALED_FULL_WINDOW',
  'request_sha256':requestsha,'registered_source_lineage':copy.deepcopy(lineage.get(c,{})),'original_prefix_preserved':c in baselines,
  'baseline_provenance':copy.deepcopy(baselines.get(c,{}).get('provenance')),'baseline_source_query_receipts':copy.deepcopy(baselines.get(c,{}).get('source_query_receipts')),
  'source_provenance':copy.deepcopy(source.get('provenance')),'source_query_receipts':copy.deepcopy(source.get('source_query_receipts'))}
 if 'source_query_receipts' in source:p['source_query_receipts']=copy.deepcopy(source['source_query_receipts'])
 return p

def semantic_controls(r,baselines,cached,caches,lineage,sessions,requestsha):
 negative={}
 def reject(name,fn):
  try:fn()
  except (AssertionError,ValueError,KeyError):negative[name]=True
  else:raise AssertionError('semantic mutation accepted: '+name)
 c=next(iter(cached));source=cached[c]
 for mode in ('issuer','future_bar','duplicate_bar','negative_volume','OHLC','missing_required_session','original_prefix_rewrite','registered_corporate_rewrite'):
  p=copy.deepcopy(source)
  if mode=='issuer':p['bars'][0]['code']='sz.999999'
  elif mode=='future_bar':p['bars'][-1]['date']='2026-10-21'
  elif mode=='duplicate_bar':p['bars'].append(copy.deepcopy(p['bars'][-1]))
  elif mode=='negative_volume':p['bars'][0]['volume']='-1'
  elif mode=='OHLC':next(row for row in p['bars'] if row['tradestatus']=='1')['high']='0'
  elif mode=='missing_required_session':p['bars'].pop()
  elif mode=='original_prefix_rewrite':p['bars'][0]['close']='999'
  else:
   if p['distributions']:p['distributions'][0]['dividCashPsBeforeTax']='999'
   else:p['adjustments'][0]['adjustFactor']='999'
  reject(mode,lambda p=p:compose(c,p,baselines[c],sessions,caches[c]))
 for side in ('left','right'):
  left=copy.deepcopy(source);right=copy.deepcopy(source)
  (left if side=='left' else right)['bars'].append(copy.deepcopy(source['bars'][-1]))
  reject('duplicate_overlap_'+side,lambda left=left,right=right:overlap(left,right))
 # Shared historical window must agree even if one source has a longer later tail.
 overlap(baselines[c],source)
 negative['different_corporate_tail_outside_common_window_not_conflict']=True
 c=r['fresh_codes'][0];component,parameters,_=specs(c,baselines)[0]
 identity={'source':'BaoStock','instrument':c,'component':component,'parameters':parameters,'composite_raw_extension_request_sha256':requestsha}
 for mode in ('unregistered_query_code','future_query_end','query_start_rewrites_old_baseline','request_link_rewrite'):
  p=copy.deepcopy(identity)
  if mode=='unregistered_query_code':p['instrument']='SZ999999'
  elif mode=='future_query_end':p['parameters']['end_date']='2026-10-21'
  elif mode=='query_start_rewrites_old_baseline':p['parameters']['start_date']=START if c in baselines else '2026-01-01'
  else:p['composite_raw_extension_request_sha256']='f'*64
  reject(mode,lambda p=p:validate_identity(p,r,requestsha,baselines))
 sample={k:'' for k in DIV};sample.update(code=symbol(c),dividOperateDate='2026-10-21',dividCashPsBeforeTax='0.1')
 accepted,quarantine=dividends(c,[sample],2026)
 assert accepted==[] and quarantine==[{'reason':'AFTER_EXTENSION_CUTOFF','record':sample}];negative['future_dividend_quarantined_not_accepted']=True
 fixture={'instrument':'SZ003031','window':[START,END],'bars':copy.deepcopy(source['bars'][60:]),'distributions':[],'adjustments':[],'quarantine':[]}
 for row in fixture['bars']:row['code']='sz.003031'
 reject('unregistered_cold_listing_gap_not_exempted',lambda:compose('SZ003031',fixture,None,sessions,[]))
 return negative

def source_questions(packets,sessions,targets):
 questions={'quarantines':[],'noncash_distributions':[],'corporate_metadata_questions':[],'adjustments_without_same_day_distribution':[],'distributions_without_same_day_adjustment':[],'unexplained_preclose_changes':[],'formation_execution_status_questions':[],'noninteger_share_volume':[],'off_cent_prices':[]}
 index={d:i for i,d in enumerate(sessions)}
 for c,p in packets.items():
  ph=digest(p);byday={r['date']:r for r in p['bars']};dd={r['dividOperateDate'] for r in p['distributions']};ad={r['dividOperateDate'] for r in p['adjustments']};previous=None;previousday=None
  for q in p['quarantine']:questions['quarantines'].append({'instrument':c,'packet_digest':ph,'entry_sha256':digest(q),'entry':q})
  for row in p['bars']:
   if row['tradestatus']=='1':
    if D(row['volume'])!=D(row['volume']).to_integral_value():questions['noninteger_share_volume'].append({'instrument':c,'day':row['date'],'volume':row['volume'],'packet_digest':ph})
    for k in ('open','high','low','close','preclose'):
     if D(row[k])!=D(row[k]).quantize(D('.01')):questions['off_cent_prices'].append({'instrument':c,'day':row['date'],'field':k,'value':row[k],'packet_digest':ph})
   if previous is not None and row['preclose'] and D(row['preclose'])>0 and abs(D(row['preclose'])-previous)>D('.005') and row['date'] not in dd:
    questions['unexplained_preclose_changes'].append({'instrument':c,'day':row['date'],'previous_day':previousday,'previous_close':str(previous),'preclose':row['preclose'],'packet_digest':ph,'cash_inferred':False})
   if row['close'] and D(row['close'])>0:previous=D(row['close']);previousday=row['date']
  count=Counter(r['dividOperateDate'] for r in p['distributions'])
  for row in p['distributions']:
   reasons=[]
   if D(row['dividStocksPs'] or '0')>0 or D(row['dividReserveToStockPs'] or '0')>0:questions['noncash_distributions'].append({'instrument':c,'packet_digest':ph,'row_sha256':digest(row),'record':row,'primary_review_complete':False})
   if count[row['dividOperateDate']]>1:reasons.append('MULTIPLE_ROWS_SAME_EX_DATE_REVIEW_REVISIONS')
   for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
    if not row[k]:reasons.append('BLANK_COMPONENT:'+k)
   for k in ('dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate'):
    if row[k]:
     day(row[k])
     if row[k]>END:reasons.append('METADATA_AFTER_CUTOFF:'+k)
    elif k in ('dividPlanDate','dividRegistDate'):reasons.append('MISSING_DATE:'+k)
   for k in ('dividRegistDate','dividOperateDate'):
    if row[k] and row[k] not in index:reasons.append('NOT_SOURCE_SESSION:'+k)
   if reasons:questions['corporate_metadata_questions'].append({'instrument':c,'packet_digest':ph,'row_sha256':digest(row),'record':row,'questions':reasons})
  for at in sorted(ad-dd):questions['adjustments_without_same_day_distribution'].append({'instrument':c,'day':at,'packet_digest':ph,'records':[r for r in p['adjustments'] if r['dividOperateDate']==at],'adjacent_distribution_days':sorted(d for d in dd if d in index and at in index and abs(index[d]-index[at])==1),'entitlement_inferred':False})
  for at in sorted(dd-ad):questions['distributions_without_same_day_adjustment'].append({'instrument':c,'day':at,'packet_digest':ph,'adjacent_adjustment_days':sorted(d for d in ad if d in index and at in index and abs(index[d]-index[at])==1)})
  for execution,t in targets.items():
   if c not in t['weights']:continue
   for role,at in (('formation',t['as_of']),('execution',execution)):
    row=byday.get(at)
    if row is None or row['tradestatus']!='1' or row['isST']!='0':questions['formation_execution_status_questions'].append({'instrument':c,'execution':execution,'role':role,'day':at,'tradestatus':row['tradestatus'] if row else None,'isST':row['isST'] if row else None,'packet_digest':ph})
 return questions

def journal(root,r,baselines,requestsha):
 queries={};artifacts={};outcomes=[];timeline=[]
 for folder in sorted((root/'queries').iterdir()) if (root/'queries').exists() else []:
  assert folder.is_dir();identity=read(folder/'request.json');validate_identity(identity,r,requestsha,baselines);assert folder.name==digest(identity)
  assert set(f.name for f in folder.iterdir())<= {'request.json','reserved-1.json','response-1.json'}
  reservation=read(folder/'reserved-1.json');assert set(reservation)=={'identity_sha256','attempt','reserved_at_utc'} and reservation['identity_sha256']==folder.name and reservation['attempt']==1
  at=datetime.fromisoformat(reservation['reserved_at_utc']);assert at.utcoffset().total_seconds()==0
  key=(identity['instrument'],identity['component']);assert key not in queries
  response=None;vendor=None
  receipt={k+'_file':str((folder/n).relative_to(root)) for k,n in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json'))}
  for k in ('request','reserved'):receipt[k+'_sha256']=sha(root/receipt[k+'_file'])
  if (folder/'response-1.json').exists():
   response=read(folder/'response-1.json');receipt['response_sha256']=sha(folder/'response-1.json')
   assert response['identity_sha256']==folder.name and response['reservation_sha256']==sha(folder/'reserved-1.json') and response['status'] in ('CAPTURED','SOURCE_ERROR')
   if response['status']=='CAPTURED':
    payload=response['payload'];assert response['payload_sha256']==digest(payload)
    received=datetime.fromisoformat(payload['captured_at_utc']);assert received.utcoffset().total_seconds()==0 and received>=at
    assert payload['fields']==['provider_response'] and len(payload['rows'])==1;vendor=payload['rows'][0]
    outcome={k:vendor[k] for k in ('initial_error_code','initial_error_msg','final_error_code','final_error_msg','iteration_error_type','iteration_error')}
   else:outcome={k:response[k] for k in ('error_type','error')}
  else:outcome={'reserved_unanswered':True}
  queries[key]={'receipt':receipt,'vendor':vendor,'response':response,'reservation':reservation};timeline.append((at,key))
  outcomes.append({'instrument':key[0],'component':key[1],'status':response['status'] if response else 'RESERVED_UNANSWERED','outcome':outcome,'response_sha256':receipt.get('response_sha256')})
  for f in folder.iterdir():artifacts[str(f.relative_to(root))]=sha(f)
 assert len(queries)==len(list(root.rglob('reserved-*.json')))<=362
 # Journal timestamps establish actual request order without interpreting historical arrival.
 observed=[key for _,key in sorted(timeline)]
 allowed=[(c,k) for c in r['fresh_codes'] for k,_,_ in specs(c,baselines)]
 assert observed==[key for key in allowed if key in queries]
 for c in r['fresh_codes']:
  expected=[k for k,_,_ in specs(c,baselines)];present=[k for code,k in observed if code==c]
  assert present==expected[:len(present)]
 return queries,artifacts,outcomes,observed

def main():
 global fresh_set
 p=argparse.ArgumentParser()
 for n in ('source-root','repo-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
 p.add_argument('--capture-dir');p.add_argument('--output');p.add_argument('--preflight-only',action='store_true');a=p.parse_args()
 base=Path(a.source_root);repo=Path(a.repo_root);requestfile=Path(a.request)
 if a.output:assert not Path(a.output).exists(),'preserve previous audit report'
 r,codes,sessions,baselines,cached,caches,lineage,bound,targets=authenticate(base,repo,requestfile,a.expected_request_sha256)
 fresh_set=set(r['fresh_codes']);negatives=semantic_controls(r,baselines,cached,caches,lineage,sessions,a.expected_request_sha256)
 if a.preflight_only:
  for f,h in bound.items():assert sha(f)==h
  print('Source-only independent preflight:127/114baselines/15reuse/99incremental/13cold/362logicalqueries; no new source/output/account/network');return 0
 assert a.output and a.capture_dir;root=Path(a.capture_dir);assert root.resolve()==(base/r['output_directory']).resolve()
 assert (root/'request.json').read_bytes()==requestfile.read_bytes();m=read(root/'manifest.json')
 assert m['status']=='COMPOSITE_RAW_EXTENSION_CAPTURED_ADMISSION_SEPARATE' and m['window']==[START,END] and m['request_sha256']==sha(requestfile)
 assert read(root/'calendar.json')=={'sessions':sessions} and sha(root/'calendar.json')==m['calendar_sha256']
 assert m['requested_names']==127 and m['fresh_codes']==r['fresh_codes'] and m['reused_codes']==sorted(cached) and m['baseline_codes']==sorted(baselines)
 assert m['incremental_codes']==[c for c in r['fresh_codes'] if c in baselines] and m['cold_codes']==[c for c in r['fresh_codes'] if c not in baselines]
 assert m['maximum_source_reservations']==362 and m['method_code_sha256']==r['method_code_sha256'] and m['target_sha256']==r['target_sha256']
 assert m['original_packet_sha256']==r['original_packet_sha256'] and m['cache_routes']==r['cache_routes'] and m['source_manifest_sha256']==r['source_manifest_sha256'] and m['source_calendar_sha256']==r['source_calendar_sha256']
 for k in ('admitted_for_account_replay','historical_arrival_verified','full_corporate_actions_certified','actual_FIFO_tax_liability_verified','portfolio_returns_computed','investment_rules_changed','objective_achieved','original_source_files_changed','full_October_complete'):assert m[k] is False
 postcheck=read(root/'source-postcheck.json');assert sha(root/'source-postcheck.json')==m['source_postcheck_sha256']
 assert postcheck=={'source_inputs_unchanged_after_capture':True} and m['source_inputs_unchanged_after_capture'] is True
 assert m['SDK_decoded_responses_not_TCP_wire'] is True and m['source_units']=={'price':'CNY/share','volume':'shares','amount':'CNY'}
 same(m['per_code_sha256'],read(root/'progress.json'));same(m['errors_sha256'],read(root/'errors.json'))
 completecodes=set(m['per_code_sha256']);errorcodes=set(m['errors_sha256']);pending=set(m['pending_codes'])
 assert not completecodes&errorcodes and not completecodes&pending and not errorcodes&pending and completecodes|errorcodes|pending==set(codes)
 assert m['pending_codes']==[c for c in codes if c in pending] and m['names']==len(completecodes)
 assert {f.stem for f in (root/'codes').glob('*.json')}==completecodes
 assert ({f.stem for f in (root/'errors').glob('*.json')} if (root/'errors').exists() else set())==errorcodes
 queries,journalhashes,outcomes,order=journal(root,r,baselines,a.expected_request_sha256);assert m['query_reservations_consumed']==len(queries)
 packets={};totals={k:0 for k in ('bars','distributions','adjustments','quarantine')};prefixes=[];errors={};partial_failures=[]
 for c,h in m['per_code_sha256'].items():
  path=root/'codes'/(c+'.json');assert sha(path)==h;actual=read(path)
  if c in cached:source=cached[c]
  else:
   receipts={};payloads={}
   for component,_,_ in specs(c,baselines):
    q=queries[(c,component)];assert q['response'] is not None and q['response']['status']=='CAPTURED' and q['vendor'] is not None and successful(q['vendor'])
    receipts[component]=q['receipt'];payloads[component]=q['vendor']
   source=projection(c,payloads,receipts,baselines)
  expected=with_provenance(c,source,compose(c,source,baselines.get(c),sessions,caches.get(c,[])),baselines,lineage,a.expected_request_sha256)
  same(actual,expected);packets[c]=actual
  if c in baselines:
   for k,f in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):same([row for row in actual[k] if row[f]<=PRE],baselines[c][k])
   prefixes.append(c)
  for k in totals:totals[k]+=len(actual[k])
 for c,h in m['errors_sha256'].items():
  f=root/'errors'/(c+'.json');assert sha(f)==h;v=read(f)
  assert v['instrument']==c and v['request_sha256']==a.expected_request_sha256 and v['source_responses_retained'] is True
  errors[c]={'sha256':h,'record':v};partial_failures.append({'instrument':c,'queries_retained':[k for code,k in order if code==c]})
 assert totals==m['totals'] and set(cached)<=completecodes
 attempted=[c for c in r['fresh_codes'] if any(code==c for code,_ in order)]
 assert attempted==r['fresh_codes'][:len(attempted)] and errorcodes<=set(attempted) and completecodes-set(cached)<=set(attempted)
 consecutive=0;stopcode=None
 for c in attempted:
  if c in errorcodes:consecutive+=1
  elif c in completecodes:consecutive=0
  else:assert m['abnormal_exit'] is not None and c==attempted[-1]
  if consecutive==3:stopcode=c;assert c==attempted[-1]
 stop=None
 if (root/'stopped.json').exists():
  stop=read(root/'stopped.json');assert stopcode is not None and stop=={'reason':'THREE_CONSECUTIVE_FAILED_CODES','last_instrument':stopcode}
 else:assert stopcode is None
 if m['abnormal_exit'] is None and stopcode is None:assert len(attempted)==112
 cleanup=read(root/'cleanup.json');assert sha(root/'cleanup.json')==m['cleanup_sha256'] and cleanup['login_attempted']==cleanup['logout_attempted']
 admin=None
 loginfiles=list(root.glob('login-reserved-*.json'));assert len(loginfiles)<=1
 if attempted:
  assert len(loginfiles)==1 and loginfiles[0].name=='login-reserved-1.json'
  assert read(loginfiles[0])=={'attempt':1,'request_sha256':a.expected_request_sha256}
  reply=read(root/'login-response-1.json');admin={'reservation_sha256':sha(loginfiles[0]),'response_sha256':sha(root/'login-response-1.json'),'response':reply}
  assert cleanup['login_attempted'] is True
 else:assert not loginfiles
 success=len(completecodes)==127 and not errorcodes and not pending and m['abnormal_exit'] is None
 if success:assert len(queries)==362 and all(q['response'] is not None and q['response']['status']=='CAPTURED' and successful(q['vendor']) for q in queries.values())
 questions=source_questions(packets,sessions,targets)
 for f,h in bound.items():assert sha(f)==h
 assert sha(requestfile)==a.expected_request_sha256
 result={'status':'INDEPENDENT_COMPOSITE_RAW_EXTENSION_SOURCE_CAPTURE_AND_PREFIX_PROVENANCE_RECONSTRUCTED_ADMISSION_SEPARATE','audit_code_sha256':sha(__file__),'request_sha256':sha(requestfile),'capture_manifest_sha256':sha(root/'manifest.json'),
  'capture_complete':success,'captured_names':len(completecodes),'requested_names':127,'reused_cache_suffix_names':len(cached),'fresh_packet_names':len(completecodes-set(cached)),
  'original103_source_files_unchanged':True,'derived11_cached_pre2026_baselines_authenticated':True,'captured_baseline_prefix_codes_exact':prefixes,
  'all127_packet_assemblies_reconstructed':success,'all_registered_common_day_financial_and_corporate_records_compared':True,'explicit_calendar_sessions':676,
  'primary_listing_prelisting_absence':{'instrument':'SZ001389','listed_on':'2024-04-02','missing_dates':[d for d in sessions if d<'2024-04-02'],'primary_boundary_already_proven':True,'source_admission_not_granted':True},
  'maximum_logical_query_reservations':362,'query_reservations_consumed':len(queries),'unconsumed_logical_budget':362-len(queries),'journal_artifact_sha256':journalhashes,'vendor_outcomes_retained':outcomes,
  'totals':totals,'errors':errors,'failed_code_partial_query_chains':partial_failures,'pending_codes':m['pending_codes'],'stop':stop,'abnormal_exit':m['abnormal_exit'],
  'source_postcheck_sha256':sha(root/'source-postcheck.json'),'source_inputs_unchanged_after_capture_independently_reauthenticated':True,'administrative_login':admin,'cleanup':cleanup,'cleanup_sha256':sha(root/'cleanup.json'),'semantic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
  **questions,'sdk_decoded_responses_not_TCP_wire':True,'raw_quarantine_and_inherited_provenance_may_reference_later_dates':True,'source_admitted_for_account':False,'corporate_action_completeness_verified':False,
  'captured_2026_values_inspected':True,'imports_project_code':False,'new_source_queries_performed':0,'account_replay_performed':False,'portfolio_returns_computed':False,'historical_arrival_verified':False,'actual_FIFO_tax_liability_verified':False,'objective_achieved':False,
  'limitations':['Only frozen local inputs and captured decoded SDK response journals are reconstructed. Logical reservations do not certify TCP wire requests or retry internals.',
   'Original103 financial records are preserved exactly; cache suffix composition is separately projected, so newly assembled packet bytes differ from baseline source files by design.',
   'Capture success does not grant source admission. New corporate rows, adjustment adjacency, preclose questions, source completeness, tax/inference scope and intraday evidence require separate review.',
   'No new listing exception is inferred; only existing primary-proven SZ001389 prelisting dates are excluded. No missing prices or corporate entitlements are synthesized.']}
 with Path(a.output).open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independent raw extension capture audit:',len(completecodes),'packets;',len(queries),'logical query chains; admission/account/ROI false')
 return 0
if __name__=='__main__':raise SystemExit(main())
