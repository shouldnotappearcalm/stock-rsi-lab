"""Independent stdlib source-chain audit; no production imports or account computation."""
from pathlib import Path
from decimal import Decimal as D
from datetime import date,datetime
from collections import Counter
import copy,hashlib,json,subprocess
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
O=B/'price-delay-raw-horizon-20261021'
REQ=R/'experiments/qlib/price-delay-horizon-raw-source-request.json'
REPORT=Path('/tmp/price-delay-horizon-raw-independent-audit-20261021.json')
EXPECTED='762b77dfed8c2a85e5fbfb7bdc7db149fd4216378230906b6ef8e18aa6ca4160'
START,PRE,END='2023-12-29','2025-12-31','2026-10-20'
SOURCES=['szse-value-momentum-raw-full-v2-20261021','low-beta60-raw-horizon-20261021','reversal-raw-full-20261017','szse-value-raw-full-20261017']
OLD=B/'price-delay-raw-dev-20261021'
BF=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
DF=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
AF=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(x,s):
 if not x:raise AssertionError(s)
def safe(root,rel):
 p=root/rel;need(not Path(rel).is_absolute() and '..' not in Path(rel).parts and p.resolve().is_relative_to(root.resolve()),'safe relative path');return p
def core(r):return [r['date'],r['code'],*[str(D(r[k]).normalize()) if r[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']]
def validday(x):need(date.fromisoformat(x).isoformat()==x,'canonical date')
def validate(c,v,sessions):
 need(v['instrument']==c and v['window']==[START,END],'packet issuer/window');need([r['date'] for r in v['bars']]==sessions,'complete ordered676 sessions')
 sym=c[:2].lower()+'.'+c[2:]
 for r in v['bars']:
  need(list(r)==BF and r['code']==sym and r['adjustflag']=='3' and r['tradestatus'] in ('0','1') and r['isST'] in ('0','1'),'bar schema/state')
  for k in ('open','high','low','close','preclose','volume','amount'):need(not r[k] or D(r[k]).is_finite() and D(r[k])>=0,'bar number')
  if r['tradestatus']=='1':
   need(all(r[k] and D(r[k])>0 for k in ('open','high','low','close','preclose','volume')),'active positive');need(D(r['low'])<=min(D(r['open']),D(r['close']))<=max(D(r['open']),D(r['close']))<=D(r['high']),'OHLC')
 for f,fields in [('distributions',DF),('adjustments',AF)]:
  need(len(v[f])==len({digest(r) for r in v[f]}),'unique corporate row')
  for r in v[f]:
   need(list(r)==fields and r['code']==sym and START<=r['dividOperateDate']<=END,'corporate identity/window');validday(r['dividOperateDate'])
   ks=('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs') if f=='distributions' else ('foreAdjustFactor','backAdjustFactor','adjustFactor')
   for k in ks:need(not r[k] or D(r[k]).is_finite() and D(r[k])>=0,'corporate number')
def clip(p):
 v={'instrument':p['instrument'],'window':[START,PRE]}
 for f,k in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:v[f]=[r for r in p[f] if START<=r[k]<=PRE]
 v['quarantine']=[q for q in p.get('quarantine',[]) if not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']<=PRE];return v
def assemble(c,src,baseline):
 v={'instrument':c,'window':[START,END]}
 for f,k in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:
  if baseline is not None and src['window'][0]<=START:
   a=[r for r in src[f] if r[k]<=PRE];b=baseline[f];need(([core(x) for x in a]==[core(x) for x in b]) if f=='bars' else a==b,'source old prefix conflict '+f)
  v[f]=copy.deepcopy((baseline[f]+[r for r in src[f] if r[k]>PRE]) if baseline else src[f])
 v['quarantine']=copy.deepcopy(baseline.get('quarantine',[]) if baseline else [])+[copy.deepcopy(q) for q in src.get('quarantine',[]) if baseline is None or not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']>PRE]
 return v
def conflicts(a,b):
 ad={r['date']:core(r) for r in a['bars']};bd={r['date']:core(r) for r in b['bars']};need(len(ad)==len(a['bars']) and len(bd)==len(b['bars']),'duplicate dates')
 result={};different=[d for d in sorted(ad.keys()&bd.keys()) if ad[d]!=bd[d]]
 if different:result['bars']=different
 lo=max(a['window'][0],b['window'][0],START);hi=min(a['window'][1],b['window'][1],END)
 for f in ('distributions','adjustments'):
  aa=[r for r in a[f] if lo<=r['dividOperateDate']<=hi];bb=[r for r in b[f] if lo<=r['dividOperateDate']<=hi]
  if aa!=bb:result[f]={'assembled':aa,'cached':bb}
 return result
CHAIN={}
def chain(root,receipt,c,comp,identity_expected=None):
 paths={k:safe(root,receipt[k+'_file']) for k in ('request','reserved','response')}
 for k,p in paths.items():need(sha(p)==receipt[k+'_sha256'],'receipt bytes '+str(p))
 identity=read(paths['request']);key=digest(identity);res=read(paths['reserved']);response=read(paths['response'])
 need(identity['instrument']==c and identity['component']==comp and identity['source']=='BaoStock','request component/issuer')
 if identity_expected is not None:need(identity==identity_expected,'exact frozen SDK parameters')
 need(paths['request'].parent==root/'queries'/key and paths['request'].name=='request.json' and paths['reserved'].name=='reserved-1.json' and paths['response'].name=='response-1.json','query identity directory/attempt1')
 need(res['attempt']==1 and res['identity_sha256']==key,'reserve attempt');need(response['identity_sha256']==key and response['status']=='CAPTURED' and response['reservation_sha256']==sha(paths['reserved']) and response['payload_sha256']==digest(response['payload']),'response binding')
 env=response['payload'];need(datetime.fromisoformat(res['reserved_at_utc'])<=datetime.fromisoformat(env['captured_at_utc']),'reserve before response');need(env['fields']==['provider_response'] and len(env['rows'])==1,'SDK envelope')
 w=env['rows'][0];need(w['initial_error_code']=='0' and w['final_error_code']=='0' and w['iteration_error_type'] is None and w['iteration_error'] is None,'initial/final SDK status')
 fields=BF if comp=='daily' else AF if comp=='adjustments' else DF;need(w['fields']==fields and all(len(r)==len(fields) for r in w['rows']),'schema projection');rows=[dict(zip(fields,r)) for r in w['rows']]
 need(all(r['code']==c[:2].lower()+'.'+c[2:] for r in rows),'SDK row issuer')
 for p in paths.values():CHAIN[str(p.relative_to(B))]=sha(p)
 return rows,identity

def ancestors(root,src,c):
 result=[(root,src)]
 for item in src.get('provenance',{}).get('registered_source_lineage',{}).get('registered_caches',[]):
  n=item.get('source_directory',item.get('root'));h=item.get('source_packet_sha256',item.get('packet_sha256'))
  if n:
   f=B/n/'codes'/(c+'.json');need(sha(f)==h,'explicit ancestor packet bytes');ap=read(f);need(ap['instrument']==c,'ancestor issuer');result.append((B/n,ap))
 return result

def main():
 req=read(REQ);m=read(O/'manifest.json');freeze=subprocess.check_output(['git','rev-parse','0e128df'],cwd=R,text=True).strip()
 need(sha(REQ)==EXPECTED==sha(O/'request.json')==m['request_sha256'],'request SHA')
 frozen={}
 for field,parent in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B),('immutable_financial_sha256',B)]:
  for n,h in req[field].items():
   need(sha(safe(parent,n))==h,'frozen binding '+n)
   if parent==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozen blob '+n)
  frozen[field]=req[field]
 need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(REQ.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozen request blob')
 need(len(req['immutable_financial_sha256'])==48 and len(req['codes'])==203 and req['maximum_source_reservations']==345 and req['max_attempts_per_query']==1 and req['maximum_administrative_login_attempts']==1 and req['socket_timeout_seconds']==20 and req['maximum_consecutive_failed_codes']==3,'fixed scope and budget')
 inv=read(R/'experiments/qlib/price-delay-horizon-raw-inventory.json');routes=req['cache_routes'];codes=req['codes'];need(codes==sorted(set(codes)),'unique ordered universe')
 targets=B/'price-delay-horizon-formations-20261021/candidate_targets.json';need(sha(targets)==req['target_sha256'],'targets unchanged');ts=read(targets);need(len(ts)==34 and sorted({c for t in ts.values() for c in t['weights']})==codes,'34target/203scope')
 manifests={};cal=read(O/'calendar.json')['sessions'];need(cal==sorted(set(cal)) and len(cal)==676 and [cal[0],cal[-1]]==[START,END] and sha(O/'calendar.json')==m['calendar_sha256'],'676calendar')
 for root in SOURCES:
  need(sha(B/root/'manifest.json')==req['source_manifest_sha256'][root] and sha(B/root/'calendar.json')==req['source_calendar_sha256'][root],'cache manifest/calendar');manifests[root]=read(B/root/'manifest.json');need(read(B/root/'calendar.json')['sessions']==[d for d in cal if d<=manifests[root]['window'][1]],'cache full sourcecalendar')
 need(cal[:486]==read(OLD/'calendar.json')['sessions'],'486 calendar prefix')
 oldm=read(OLD/'manifest.json');need(oldm['per_code_sha256']==req['original_packet_sha256'] and len(oldm['per_code_sha256'])==151,'151 originals');baselines={};lineage={};originals={}
 for c,h in req['original_packet_sha256'].items():
  p=OLD/'codes'/(c+'.json');need(sha(p)==h,'original literal packet unchanged');v=read(p);need(v['window']==[START,PRE] and [r['date'] for r in v['bars']]==cal[:486],'original fullcalendar');originals[c]=v;baselines[c]=v;lineage[c]={'baseline':{'kind':'ORIGINAL_PRICE_DELAY_PREFIX','file':str(p.relative_to(B)),'sha256':h}}
 proofs=read(O/'coordinate-reference-proofs.json');oldproofs=read(B/SOURCES[0]/'coordinate_checks.json');prior=read(R/'experiments/qlib/price-delay-horizon-existing-coordinate-reuse-audit.json')
 need(prior['existing_proof_can_be_reused_unchanged'] is True and prior['imports_project_code'] is False,'independent coordinate proof audit')
 need(prior['coordinate_checks_sha256']==sha(B/SOURCES[0]/'coordinate_checks.json') and prior['V2_manifest_sha256']==sha(B/SOURCES[0]/'manifest.json') and prior['audit_code_sha256']==sha(R/'experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-existing-coordinate-reuse-audit.py'),'prior independent proof hashes')
 primaryroot=B/'szse-value-momentum-primary-2026-gaps-20261021';primary=read(primaryroot/'manifest.json');content=read(R/'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json')
 need(prior['seven_notice_capture_manifest_sha256']==sha(primaryroot/'manifest.json')==content['capture_manifest_sha256'] and prior['seven_notice_content_review_sha256']==sha(R/'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json'),'primary/content prior proof binding')
 primary_binding={}
 for pc in ('SZ002608','SZ002756'):
  doc=primary['documents'][pc];review=next(x for x in content['documents'] if x['instrument']==pc);pdf=safe(primaryroot,doc['file']);need(sha(pdf)==doc['sha256']==review['sha256'] and pdf.read_bytes().startswith(b'%PDF'),'coordinate primary PDF immutable')
  need(all(doc[k]==review[k] for k in ('instrument','file','publication_day')),'primary identity exact')
  for k in ('request','reserved','response'):need(sha(safe(primaryroot,doc['pdf_receipt'][k+'_file']))==doc['pdf_receipt'][k+'_sha256'],'primary captured receipt unchanged')
  primary_binding[pc]={'document':doc,'bound_content_review':review} 
 need({k:digest(v) for k,v in proofs.items()}==req['coordinate_reference_proof_sha256'] and len(proofs)==4,'four exact retained proofs')
 for key,p in proofs.items():need(p in oldproofs[key.split('/')[0]],'retained coordinate object unchanged')
 cache_payloads={};cache_refs={};cache_lineage=[];derived=[]
 for c in codes:
  choices=inv['items'][c]['choices'];payloads=[]
  for choice in choices:
   root=choice['root'];p=B/root/'codes'/(c+'.json');need(root in SOURCES and sha(p)==choice['packet_sha256']==manifests[root]['per_code_sha256'][c],'registered sourcepacket hash');v=read(p);need(v['instrument']==c and v['window']==choice['window'] and [r['date'] for r in v['bars']]==[d for d in cal if d<=v['window'][1]],'cache identity/calendar');payloads.append((root,v))
   if c in originals:need(not conflicts(originals[c],v),'original pre26/cache overlap')
  cache_refs[c]=payloads
  if choices:
   lineage.setdefault(c,{})['registered_caches']=choices
   lineage[c]['retained_coordinate_variance_proofs']={k:digest(v) for k,v in proofs.items() if k.startswith(c+'/')}
   route=routes[c];selected=next(v for root,v in payloads if root==route['cache_route']);need(sha(B/route['cache_route']/'codes'/(c+'.json'))==route['cache_packet_sha256'],'selected route hash')
   if c not in baselines and route['source_class']=='incremental':
    baselines[c]=clip(selected);need([r['date'] for r in baselines[c]['bars']]==cal[:486],'derived486baseline');lineage[c]['baseline']={'kind':'CLIPPED_FIXED_PARTIAL_CACHE_PREFIX','root':route['cache_route'],'packet_sha256':route['cache_packet_sha256']};derived.append(c)
   if route['source_class']=='whole_cache':cache_payloads[c]=selected
  else:need(routes[c]['cache_route'] is None,'no hidden route')
 fresh=[c for c in codes if c not in cache_payloads];incremental=[c for c in fresh if c in baselines];cold=[c for c in fresh if c not in baselines]
 need(len(cache_payloads)==102 and len(incremental)==80 and len(cold)==21 and len(derived)==16 and len(baselines)==167 and 3*len(incremental)+5*len(cold)==345,'independent partition');need(fresh==req['fresh_codes']==m['fresh_codes'] and sorted(baselines)==req['baseline_codes']==m['baseline_codes'] and incremental==m['incremental_codes'] and cold==m['cold_codes'] and sorted(cache_payloads)==m['reused_codes'],'manifest partition')
 # Parse every actual journal directory without relying on packet receipt references.
 sources={};fresh_receipts={};query_files={};sequence=[]
 for folder in (O/'queries').iterdir():
  need(folder.is_dir() and {p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'},'no extra/incomplete/retried logical query')
  ident=read(folder/'request.json');c,comp=ident['instrument'],ident['component'];need(c in fresh,'query fresh universe');start='2026-01-01' if c in baselines else START
  params={'start_date':start,'end_date':END,'frequency':'d','adjustflag':'3'} if comp=='daily' else {'start_date':start,'end_date':END} if comp=='adjustments' else {'year':comp[-4:],'yearType':'operate'}
  allowed={'daily','adjustments','dividend2026'} if c in baselines else {'daily','adjustments','dividend2024','dividend2025','dividend2026'};need(comp in allowed,'component budget')
  rec={}
  for k,n in [('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')]:p=folder/n;rec[k+'_file']=str(p.relative_to(O));rec[k+'_sha256']=sha(p);query_files[str(p.relative_to(O))]=sha(p)
  rows,_=chain(O,rec,c,comp,{'source':'BaoStock','instrument':c,'component':comp,'parameters':params,'composite_raw_extension_request_sha256':EXPECTED});need(comp not in sources.setdefault(c,{}),'duplicate logical query');sources[c][comp]=rows;fresh_receipts.setdefault(c,{})[comp]=rec;sequence.append((read(folder/'reserved-1.json')['reserved_at_utc'],c,comp))
 need(len(query_files)==1035 and len(sequence)==345 and m['query_reservations_consumed']==345 and m['maximum_source_reservations']==345,'all345 complete logical reservations')
 ordered=[(c,comp) for _,c,comp in sorted(sequence)];expectedseq=[(c,comp) for c in fresh for comp in (['daily','dividend2026','adjustments'] if c in baselines else ['daily','dividend2024','dividend2025','dividend2026','adjustments'])];need(ordered==expectedseq,'one ordered attempt/component/code no automatic retry')
 for c in fresh:
  start='2026-01-01' if c in baselines else START;need(set(sources[c])==({'daily','dividend2026','adjustments'} if c in baselines else {'daily','dividend2024','dividend2025','dividend2026','adjustments'}),'complete fresh components')
  src={'instrument':c,'window':[start,END],'bars':sources[c]['daily'],'adjustments':sources[c]['adjustments'],'distributions':[],'quarantine':[],'source_query_receipts':fresh_receipts[c]}
  need([r['date'] for r in src['bars']]==[d for d in cal if d>=start],'fresh sourcecalendar')
  for comp,rows in sorted(sources[c].items()):
   if not comp.startswith('dividend'):continue
   for r in rows:
    d=r['dividOperateDate']
    if not d:src['quarantine'].append({'reason':'MISSING_OPERATE_DATE','record':r});continue
    validday(d);need(d[:4]==comp[-4:],'operateyear')
    if not START<=d<=END:src['quarantine'].append({'reason':'AFTER_EXTENSION_CUTOFF' if d>END else 'BEFORE_EXTENSION_WINDOW','record':r})
    else:src['distributions'].append(r)
  sources[c]=src
 saved=m['per_code_sha256'];errors=m['errors_sha256'];need(set(saved).isdisjoint(errors) and sorted(set(saved)|set(errors)|set(m['pending_codes']))==codes,'saved/error/pending partition')
 need(read(O/'progress.json')==saved and read(O/'errors.json')==errors and {p.name for p in (O/'codes').iterdir()}=={c+'.json' for c in saved} and {p.name for p in (O/'errors').iterdir()}=={c+'.json' for c in errors},'exact outputfiles/checkpoints')
 need(set(errors)=={'SH603233'} and not m['pending_codes'] and m['abnormal_exit'] is None and not (O/'stopped.json').exists(),'actual one source-quality failure preserved')
 totals=Counter();prefixcount=0;cache_receipt_count=0;failures={};whole=[]
 for c in codes:
  src=cache_payloads[c] if c in cache_payloads else sources[c];baseline=baselines.get(c);v=assemble(c,src,baseline);validate(c,v,cal)
  bad={root:conflicts(v,p) for root,p in cache_refs[c] if c+'/'+root not in proofs};bad={root:diff for root,diff in bad.items() if diff}
  if c in errors:
   ep=O/'errors'/(c+'.json');need(sha(ep)==errors[c],'error bytes');error=read(ep);need(error=={'instrument':c,'error_type':'ValueError','error':'registered cached corporate/adjustment conflict: adjustments','request_sha256':EXPECTED,'source_responses_retained':True} and bad and all(set(x)=={'adjustments'} for x in bad.values()),'precise independent source conflict retained');need(not (O/'codes'/(c+'.json')).exists(),'no falsely saved conflict');failures[c]={'error':error,'error_sha256':sha(ep),'reconstructed_source_sha256':digest(src),'registered_cache_conflicts':bad};continue
  need(not bad,'no unrecognized saved cache conflict '+c)
  p=O/'codes'/(c+'.json');need(sha(p)==saved[c],'saved packet SHA');actual=read(p)
  kind='AUTHENTICATED_CACHE_SUFFIX_WITH_PRESERVED_PREFIX' if c in cache_payloads else 'PRESERVED_PREFIX_JOURNALED_SUFFIX' if baseline else 'JOURNALED_FULL_WINDOW'
  v['provenance']={'kind':kind,'request_sha256':EXPECTED,'registered_source_lineage':lineage.get(c,{}),'original_prefix_preserved':c in baselines,'baseline_provenance':(baseline or {}).get('provenance'),'baseline_source_query_receipts':(baseline or {}).get('source_query_receipts'),'source_provenance':src.get('provenance'),'source_query_receipts':src.get('source_query_receipts')}
  if 'source_query_receipts' in src:v['source_query_receipts']=src['source_query_receipts']
  need(actual==v,'independent entire packet reconstruction '+c)
  for f in ('bars','distributions','adjustments','quarantine'):totals[f]+=len(v[f])
  if c in originals:
   need(clip(v)==clip(originals[c]),'literal all pre26 observations prefix '+c);prefixcount+=1
  if c in cache_payloads:
   root=routes[c]['cache_route'];sm=manifests[root];rr=B/sm.get('source_query_receipts_relative_to',root);checked=[]
   for comp,receipt in src.get('source_query_receipts',{}).items():
    if not (rr/receipt['request_file']).exists():
     candidates=[(ar,ap) for ar,ap in ancestors(B/root,src,c) if ap.get('source_query_receipts',{}).get(comp)==receipt and (ar/receipt['request_file']).exists()]
     need(len(candidates)==1,'unique explicit receipt ancestor');rr,ancestor=candidates[0]
    rows,identity=chain(rr,receipt,c,comp);field='bars' if comp=='daily' else 'adjustments' if comp=='adjustments' else 'distributions';clock='date' if comp=='daily' else 'dividOperateDate';lo=identity['parameters'].get('start_date',identity['parameters'].get('year','0000')+'-01-01');hi=identity['parameters'].get('end_date',identity['parameters'].get('year','2026')+'-12-31')
    accepted=[r for r in rows if r[clock] and START<=r[clock]<=END and lo<=r[clock]<=hi]
    targetrows=[r for r in src[field] if lo<=r[clock]<=hi]
    need(accepted==targetrows,'cache SDK source observation projection '+c+' '+comp);checked.append({'component':comp,'receipt_root':str(rr.relative_to(B)),'request_sha256':receipt['request_sha256'],'response_sha256':receipt['response_sha256']});cache_receipt_count+=1
   reuse=src.get('reused_dividend_response')
   if reuse is None:
    inherited=[ap['reused_dividend_response'] for ar,ap in ancestors(B/root,src,c) if ap.get('reused_dividend_response')]
    if inherited:need(all(x==inherited[0] for x in inherited),'consistent reused-dividend ancestry');reuse=inherited[0]
   if reuse:
    rr=Path(reuse['origin_directory']);need(rr.resolve().is_relative_to(B.resolve()),'registered reused response root');rows,ident=chain(rr,reuse['receipt'],c,'dividend2026');need(reuse['data']=={'fields':DF,'rows':[[r[k] for k in DF] for r in rows]},'explicit reused dividend data binding');need([r for r in rows if r['dividOperateDate'] and START<=r['dividOperateDate']<=END]==[r for r in src['distributions'] if r['dividOperateDate'][:4]=='2026'],'reused 2026 distribution observations');checked.append({'component':'dividend2026','receipt_root':str(rr.relative_to(B)),'response_sha256':reuse['receipt']['response_sha256']});cache_receipt_count+=1
   whole.append({'instrument':c,'registered_source_root':root,'source_packet_sha256':routes[c]['cache_packet_sha256'],'output_packet_sha256':saved[c],'source_observations_reconstructed':True,'SDK_component_receipts_verified':checked,'no_transport_receipts_in_packet':not checked})
 need(dict(totals)==m['totals'] and len(saved)==m['names']==202 and m['requested_names']==203,'manifest saved totals')
 need(prefixcount==151 and 'SH603233' in derived,'151 saved original prefixes plus failed derived baseline')
 # Failed symbol: independently separate common core, distribution, and coordinate differences.
 c='SH603233';v=assemble(c,sources[c],baselines[c]);details=[]
 for root,p in cache_refs[c]:
  common=set(r['date'] for r in v['bars'])&set(r['date'] for r in p['bars']);need(all(core(next(r for r in v['bars'] if r['date']==d))==core(next(r for r in p['bars'] if r['date']==d)) for d in common),'failed issuer all common raw core exact')
  hi=min(v['window'][1],p['window'][1]);need([r for r in v['distributions'] if r['dividOperateDate']<=hi]==p['distributions'],'failed common dividends exact')
  a={r['dividOperateDate']:r for r in v['adjustments']};b={r['dividOperateDate']:r for r in p['adjustments']};changes=[]
  for d in sorted(a.keys()&b.keys()):
   if a[d]!=b[d]:
    fields=[k for k in AF if a[d][k]!=b[d][k]];need(d>PRE and fields==['foreAdjustFactor'],'failed changes only2026fore');changes.append({'date':d,'cached':b[d],'fresh':a[d],'changed_fields':fields})
  extra=[a[d] for d in sorted(a.keys()-b.keys())];need(all(r['dividOperateDate']=='2026-10-19' for r in extra),'new factor date')
  details.append({'cached_root':root,'cached_packet_sha256':sha(B/root/'codes'/(c+'.json')),'common_daily_rows':len(common),'all_common_raw_core_exact':True,'all_common_distribution_rows_exact':True,'common_adjustment_changes':changes,'fresh_additional_adjustment_rows':extra,'no_corresponding_fresh_distribution_for_new_factor':not any(r['dividOperateDate']=='2026-10-19' for r in sources[c]['distributions'])})
 need(clip(v)==clip(baselines[c]),'failed source reconstructed literal486derivedprefix');failures[c]['independent_difference_explanation']=details;failures[c]['new_primary_source_proof_required']=True
 cleanup=read(O/'cleanup.json');post=read(O/'source-postcheck.json');scope=read(O/'price-delay-scope.json');login=read(O/'login-response-1.json')
 need(cleanup=={'login_attempted':True,'logout_attempted':True,'error_code':'0','error_msg':'success'} and post=={'source_inputs_unchanged_after_capture':True} and login['error_code']=='0','cleanup/postcheck/login')
 need(read(O/'login-reserved-1.json')=={'attempt':1,'request_sha256':EXPECTED} and len(list(O.glob('login-reserved-*.json')))==len(list(O.glob('login-response-*.json')))==1,'one administrative login')
 expected_scope={'status':'PRICE_DELAY_HORIZON_RAW_CAPTURE_RECORDED','candidate':'price_delay_d1','request_sha256':EXPECTED,'target_sha256':req['target_sha256'],'legacy_helper_manifest_sha256':sha(O/'manifest.json'),'cleanup_sha256':sha(O/'cleanup.json'),'postcheck_sha256':sha(O/'source-postcheck.json'),'coordinate_reference_proofs_sha256':sha(O/'coordinate-reference-proofs.json'),'source_observation_reuse_not_packet_byte_copy':True,'capture_complete':False,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'investment_rules_changed':False,'full_October_2026_complete':False,'objective_achieved':False};need(scope==expected_scope,'exact failed scope and boundaries')
 for k in ('admitted_for_account_replay','historical_arrival_verified','full_corporate_actions_certified','actual_FIFO_tax_liability_verified','portfolio_returns_computed','investment_rules_changed','objective_achieved'):need(m[k] is False,'manifest explicit false '+k)
 # Meaningful local semantic negatives exercise validators without touching stored files.
 negatives={}
 def rejects(label,fn):
  try:fn()
  except (AssertionError,ValueError):negatives[label]=True
  else:raise AssertionError('negative accepted '+label)
 sample=copy.deepcopy(assemble('SH600007',sources['SH600007'],baselines['SH600007']));sample['bars'].pop();rejects('missing_calendar_session',lambda:validate('SH600007',sample,cal))
 sample=copy.deepcopy(assemble('SH600007',sources['SH600007'],baselines['SH600007']));sample['bars'][0]['code']='sh.999999';rejects('wrong_issuer',lambda:validate('SH600007',sample,cal))
 sample=copy.deepcopy(assemble('SH600007',sources['SH600007'],baselines['SH600007']));sample['bars'][0]['high']='0';rejects('OHLC_violation',lambda:validate('SH600007',sample,cal))
 sample=copy.deepcopy(expected_scope);sample['capture_complete']=True;rejects('false_capture_complete',lambda:need(sample==expected_scope,'failed verdict changed'))
 nc='SH600004';sample=assemble(nc,cache_payloads[nc],baselines.get(nc));need(not conflicts(sample,cache_refs[nc][0][1]),'negative clean starting point');sample['adjustments'][-1]['foreAdjustFactor']='0.123';rejects('unproved_adjustment_overlap',lambda:need(not conflicts(sample,cache_refs[nc][0][1]),'coordinate conflict'))
 nc=next(x for x in cache_payloads if x in baselines);sample=copy.deepcopy(cache_payloads[nc]);sample['bars'][0]['close']='999';rejects('rewritten_original_prefix',lambda:assemble(nc,sample,baselines[nc]))
 report={'status':'PASS_INDEPENDENT_AUDIT_OF_PRESERVED_FAILED_SOURCE_CAPTURE','capture_complete':False,'failed_capture_correctly_preserved':True,'capture_manifest_sha256':sha(O/'manifest.json'),'request_sha256':EXPECTED,'scope_sha256':sha(O/'price-delay-scope.json'),'freeze_commit':freeze,'imports_project_code':False,'audit_code_sha256':sha(Path(__file__)),'method_code_sha256':req['method_code_sha256'],'all_frozen_input_hashes_verified':frozen,'203_requested_codes':codes,'676_source_sessions_verified':True,'saved_packets_independently_reconstructed':202,'whole_cache_observation_reuse_verified':102,'incremental_requested':80,'cold_requested':21,'derived486_baselines_verified':derived,'original151_source_packets_unchanged':True,'saved_original_literal_prefixes_verified':prefixcount,'failed_derived_literal486_prefix_reconstructed_from_retained_sources':True,'original48_financial_artifacts_unchanged':True,'fresh_component_chains_reconstructed':345,'fresh_instruments_with_complete_responses':101,'query_artifact_sha256':query_files,'all_verified_lineage_query_artifact_sha256':CHAIN,'logical_attempts_per_query':1,'SDK_initial_and_final_status_all_successful':True,'all345_logical_request_reservation_response_chains_fully_recorded':True,'source_quality_errors':failures,'pending_codes':m['pending_codes'],'totals_reconstructed':dict(totals),'whole_cache_lineage':whole,'whole_cache_component_receipts_verified':cache_receipt_count,'four_existing_coordinate_proofs_preserved_sha256':req['coordinate_reference_proof_sha256'],'existing_coordinate_independent_audit_sha256':sha(R/'experiments/qlib/price-delay-horizon-existing-coordinate-reuse-audit.json'),'existing_coordinate_primary_bytes_reverified':primary_binding,'cleanup_success':True,'postcheck_inputs_unchanged':True,'semantic_negative_controls_rejected':negatives,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'account_replay_performed':False,'full_October_2026_complete':False,'network_calls':0,'repository_or_source_bytes_modified':False,'objective_achieved':False,'critical_or_important_audit_findings':[],'limitations':['Technical capture-chain audit with a preserved source-quality failure; this capture is incomplete and not admitted for accounts.','SH603233 retained fresh/common-cache adjustment mismatch requires separately authenticated primary evidence; no factors, cash flows, or tax status were inferred or repaired.','SDK-decoded logical request/reservation/response chains do not prove every TCP attempt or PIT arrival.','Registered cached packets without transport receipts are authenticated by immutable packet/manifest provenance, not invented fresh transport proof.','Existing four coordinate proofs are bound and reused unchanged from their separate independent Fraction/primary-source audit; no new coordinate exception was added.','Accepted observations stop2026Oct20; quarantines/provenance may reference later dates, and full October is incomplete.']}
 REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'audit_code_sha256':report['audit_code_sha256'],'saved':202,'errors':1,'queries':345,'cache_receipts':cache_receipt_count}))
if __name__=='__main__':main()
