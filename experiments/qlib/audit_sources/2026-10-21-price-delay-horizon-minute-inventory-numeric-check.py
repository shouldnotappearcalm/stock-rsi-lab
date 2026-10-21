"""Separate stdlib source-inventory recomputation; no account/ROI or network."""
import hashlib,json
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
D=B/'price-delay-horizon-minute-inventory-20261021'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(x,m):
 if not x:raise ValueError(m)
request=read(R/'experiments/qlib/price-delay-horizon-minute-inventory-request.json')
need(sha(R/'experiments/qlib/price-delay-horizon-minute-inventory-request.json')=='110a70fa2c40a6429352842a0f152796721d6c5268845269c6ec93f23b13dc28','frozen request')
v,s=read(D/'details.json'),read(D/'summary.json')
need(sha(D/'details.json')==s['details_sha256'],'details summary link')
raw=B/'price-delay-raw-horizon-v2-20261021';rm=read(raw/'manifest.json')
need(sha(raw/'manifest.json')=='9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490','raw anchor')
need(sha(B/'price-delay-horizon-formations-20261021/candidate_targets.json')=='5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923','fixed target anchor')
targets=read(B/'price-delay-horizon-formations-20261021/candidate_targets.json');bars={}
for c,h in rm['per_code_sha256'].items():
 p=raw/'codes'/(c+'.json');need(sha(p)==h,'raw packet');bars[c]={x['date']:x for x in read(p)['bars']}
active=[];skipped=[];seen=set()
for day,t in sorted(targets.items()):
 seen.update(t['weights'])
 for c in sorted(seen):
  x=bars[c][day]
  if x['tradestatus']=='1':active.append([c,day])
  elif x['tradestatus']=='0':skipped.append({'instrument':c,'day':day,'reason':'SOURCE_HALT','actual_inventory_proven_zero':False,'synthetic_price_created':False})
  else:raise ValueError('unexpected trading source status')
need(active==v['all_active_requests'] and skipped==v['all_nonexecuting_source_intervals'],'entire algorithmic identity list')
old=read(B/'price-delay-minute-inventory-20261021/details.json')
need([x for x in active if x[1]<'2026-01-01']==old['active_requests'] and [x for x in skipped if x['day']<'2026-01-01']==old['nonexecuting_source_intervals'],'literal old2502/2')
new=[x for x in active if x[1]>='2026-01-01'];need(new==v['new2026_active_requests'],'2026 partition')
index={}
for root in request['source_precedence']:
 m=B/root/'manifest.json';need(sha(m)==request['source_manifest_sha256'][root],'cache manifest')
 for name,h in read(m)['per_session_sha256'].items():index.setdefault(name,[]).append({'root':root,'sha256':h})
missing=[];reuse={};marker=[];references=0
for c,day in new:
 name=c+'-'+day+'.json';origins=index.get(name,[]);state={'0':'ORDINARY_FLAG_ZERO','1':'NONORDINARY_FLAG_ONE'}.get(bars[c][day].get('isST'),'ORDINARY_FLAG_UNKNOWN')
 if state!='ORDINARY_FLAG_ZERO':marker.append({'instrument':c,'day':day,'source_state':state,'required_account_dependency_proof':True,'actual_inventory_proven_zero':False})
 signatures=set()
 for origin in origins:
  f=B/origin['root']/'sessions'/name;need(sha(f)==origin['sha256'],'cached bytes');packet=read(f);rec=packet.get('methods',{}).get('minutes.history',packet)
  need(packet['instrument']==c and packet['requested_day']==day and rec['status']=='RESPONSE_CAPTURED','cached identity/source status')
  signatures.add(digest({'status':rec['status'],'response':rec.get('response')}));references+=1
 need(len(signatures)<=1,'cache response conflict')
 if origins:reuse[name]=origins[0]
 else:missing.append([c,day])
 row=v['cached_reference_details'][name]
 need(row['origins']==origins and row['source_state']==state,'all source references and flags')
 if origins:need(row['status']=='CACHED_SOURCE_PACKET_RETAINED' and row['ordinary_source_quality_checked']==(state=='ORDINARY_FLAG_ZERO') and row['source_or_account_admitted'] is False,'producer ordinary-check boundary')
need(missing==v['uncached_requests'] and reuse==v['reused_session_provenance'] and marker==v['nonordinary_or_unknown_source_markers'],'new exact partitions')
need(not v['invalid_cached_requests'] and not v['conflicting_cached_requests'],'no reported invalid/conflict')
for n,h in request['immutable_financial_sha256'].items():need(sha(B/n)==h,'all48 financial actual bytes')
for n,h in v['old_pre2026_evidence']['original2502_packet_sha256'].items():need(sha(B/'price-delay-minutes-dev-20261021/sessions'/n)==h,'old2502 source bytes')
report={'status':'PRICE_DELAY_HORIZON_MINUTE_INVENTORY_SEPARATE_NUMERIC_RECOMPUTATION_PASS',
 'script_sha256':sha(Path(__file__)),'request_sha256':sha(R/'experiments/qlib/price-delay-horizon-minute-inventory-request.json'),
 'summary_sha256':sha(D/'summary.json'),'details_sha256':sha(D/'details.json'),
 'all_required_pair_identities_independently_recomputed':True,'old2502_and2halt_literal_prefixes_identical':True,
 'new_active_pairs':len(new),'new_cached_reuse_pairs':len(reuse),'new_missing_pairs':len(missing),'cached_references_authenticated':references,
 'new_nonordinary_markers':len(marker),'all48_financial_file_bytes_unchanged':True,
 'all_cached_reference_hashes_identities_response_signatures_verified':True,
 'producer_minute_quality_inspection_not_reimplemented':True,'no_new_ordinary_admission_granted':True,
 'imports_project_code':False,'new_source_queries':0,'account_or_ROI_executed':False,'critical_or_important_findings':[],
 'source_admitted_for_account_replay':False,'objective_achieved':False}
out=Path('/tmp/price-delay-horizon-minute-inventory-numeric-check-20261021.json')
with out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report))
