"""Bounded pre2026 raw-source cache inventory. No project imports/network/replay.
Only authenticated, pre2026-clipped packets are opened. Mixed/full/horizon
packet trees are skipped even when they may contain additional reusable names.
"""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
E=R/'experiments/qlib';OUT=Path('/tmp/low-market-residual-vol1m-pre2026-raw-source-inventory-20261021.json')
T=B/'low-market-residual-vol1m-budgeted-pre2026-development-20261021/targets.json'
PRIORITY=['price-delay-raw-dev-20261021','low-beta60-raw-dev-20261021','szse-value-momentum-raw-dev-20261021','budgeted-residual-raw-dev-20261021','return-families-raw-dev-20261017','szse-value-raw-dev-20261017','illiquidity-raw-source-continuation-20261020']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
target_initial_sha256=sha(T)
x=read(T);targets=x['low_market_residual_vol_1m'];assert len(targets)==24 and all('2024-01-02'<=d<='2025-12-31' for d in targets);codes=sorted({c for v in targets.values() for c in v['weights']});assert len(codes)==361
vmrequest=E/'szse-value-momentum-raw-source-request.json';vmreq=read(vmrequest);vmaudit=E/'szse-value-momentum-raw-source-independent-audit.json';vma=read(vmaudit)
assert vma['capture_complete'] is True and vma['request_sha256']==sha(vmrequest) and vma['all5_authenticated_cache_calendars_identical_486'] is True
anchors={v['directory']:v['manifest_sha256'] for v in vmreq['reuse_sources']}
audit_paths={'price-delay-raw-dev-20261021':E/'price-delay-raw-source-independent-audit.json','low-beta60-raw-dev-20261021':E/'low-beta60-raw-source-audit.json','szse-value-momentum-raw-dev-20261021':vmaudit,'budgeted-residual-raw-dev-20261021':E/'budgeted-residual-raw-source-audit.json','illiquidity-raw-source-continuation-20261020':E/'illiquidity-raw-development-data-audit.json'}
for name,p in audit_paths.items():
 a=read(p);h=a.get('capture_manifest_sha256',a.get('manifest_sha256',a.get('raw_manifest_sha256')));assert h==sha(B/name/'manifest.json');anchors[name]=h
 if name!='illiquidity-raw-source-continuation-20261020':assert a.get('capture_complete',a.get('SDK_decoded_responses_all_successful')) is True
sources=[];candidates=defaultdict(list);incomplete=[];calendar=None;conflicts=[];all_packet_hashes={}
for priority,name in enumerate(PRIORITY):
 d=B/name;m=read(d/'manifest.json');assert sha(d/'manifest.json')==anchors[name];assert m['window']==['2023-12-29','2025-12-31'];assert m.get('new_2026_market_queries') is False
 cp=d/'calendar.json';assert sha(cp)==m['calendar_sha256'];cal=read(cp)['sessions'];assert len(cal)==486 and cal==sorted(set(cal)) and cal[0]=='2023-12-29' and cal[-1]=='2025-12-31'
 if calendar is not None:assert cal==calendar
 calendar=cal;local=[];nfull=0
 for c in sorted(set(codes)&set(m['per_code_sha256'])):
  p=d/'codes'/(c+'.json');h=sha(p);assert h==m['per_code_sha256'][c];packet=read(p);assert packet['instrument']==c and packet['window']==m['window']
  bars=packet['bars'];bar_days=[r['date'] for r in bars];assert bar_days==sorted(set(bar_days));assert all('2023-12-29'<=v<='2025-12-31' for v in bar_days)
  vendor=c[:2].lower()+'.'+c[2:];assert all(r['code']==vendor and r['adjustflag']=='3' for r in bars)
  assert not packet['quarantine'],'nonempty quarantine requires separate bounded inspection'
  for key in ('distributions','adjustments'):
   assert all(r['code']==vendor and '2023-12-29'<=r['dividOperateDate']<='2025-12-31' for r in packet[key])
  # Normalize only row/dictionary ordering; never alter or merge source values.
  core={k:sorted(packet[k],key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False)) for k in ('bars','distributions','adjustments')}
  coreh=canonical(core);missing=sorted(set(calendar)-set(bar_days));complete=bar_days==calendar
  item={'directory':name,'priority':priority,'file':str(p.relative_to(B)),'packet_sha256':h,'manifest_sha256':sha(d/'manifest.json'),'calendar_sha256':m['calendar_sha256'],'window':m['window'],'observed_bar_rows':len(bars),'complete_486_session_calendar':complete,'missing_sessions':missing,'extra_sessions':sorted(set(bar_days)-set(calendar)),'distributions':len(packet['distributions']),'adjustments':len(packet['adjustments']),'quarantines':0,'raw_core_sha256':coreh,'isST_rows':sum(r.get('isST')=='1' for r in bars),'halted_rows':sum(r.get('tradestatus')=='0' for r in bars),'corporate_action_admitted':False}
  local.append(item);candidates[c].append(item);all_packet_hashes[str(p.relative_to(B))]=h
  if complete:nfull+=1
  else:incomplete.append({'instrument':c,**item,'missing_sessions_classified_as_prelisting':False})
 audit_anchor={'file':str(audit_paths[name].relative_to(R)),'sha256':sha(audit_paths[name])} if name in audit_paths else {'file':str(vmaudit.relative_to(R)),'sha256':sha(vmaudit),'authenticated_source_manifest_via_request':str(vmrequest.relative_to(R)),'request_sha256':sha(vmrequest),'per_new_target_packet_independently_checked_here':True}
 sources.append({'directory':name,'priority':priority,'manifest_sha256':sha(d/'manifest.json'),'calendar_sha256':m['calendar_sha256'],'source_status':m['status'],'window':m['window'],'manifest_names':m['names'],'target_intersection':len(local),'fully_covered_target_packets':nfull,'audit_anchor':audit_anchor})
selected={};details={}
for c in codes:
 opts=candidates[c];full=[v for v in opts if v['complete_486_session_calendar']]
 if len({v['raw_core_sha256'] for v in full})>1:conflicts.append({'instrument':c,'sources':[{'directory':v['directory'],'packet_sha256':v['packet_sha256'],'raw_core_sha256':v['raw_core_sha256']} for v in full]})
 if full:selected[c]=full[0]
 details[c]={'status':'AUTHENTICATED_COMPLETE_PRE2026_PACKET_REUSABLE_SOURCE_ONLY' if full else 'NO_COMPLETE_PACKET_IN_BOUNDED_PRE2026_CACHE_SET','selected_reuse':full[0] if full else None,'all_registered_pre2026_cache_options':opts,'primary_corporate_tax_lifecycle_or_account_admission':False}
missing=sorted(set(codes)-set(selected));routecounts=Counter(v['directory'] for v in selected.values())
# No mixed raw packet is opened. Names alone delimit deliberately skipped trees.
skip=[]
for n in ['low-risk-raw-account-data-20261017','reversal-raw-full-20261017','szse-value-raw-full-20261017','low-beta60-raw-extension-20261021','low-beta60-raw-horizon-20261021','szse-value-momentum-raw-full-20261021','szse-value-momentum-raw-full-v2-20261021','price-delay-raw-horizon-20261021','price-delay-raw-horizon-v2-20261021']:
 if (B/n).exists():skip.append({'directory':n,'action':'SKIPPED_PACKET_AND_FINANCIAL_CONTENT','reason':'Registered full/extension/horizon source may contain2026 accepted prices or corporate financial observations; bounded inventory uses pre2026-clipped roots instead.','manifest_metadata_read':n=='low-risk-raw-account-data-20261017','packet_or_quote_content_read':False})
for n,h in all_packet_hashes.items():assert sha(B/n)==h
assert sha(T)==target_initial_sha256
report={'status':'BOUNDED_PRE2026_RAW_SOURCE_CACHE_INVENTORY_COMPLETE','candidate':'low_market_residual_vol_1m','allocator_trial':'BUDGETED_EXISTING_GENERIC_LOT_ALLOCATOR','target_file':str(T),'target_sha256':target_initial_sha256,'target_bytes_rechecked_unchanged':True,'target_family':'low_market_residual_vol_1m','target_months':24,'target_union_names':361,'source_window':['2023-12-29','2025-12-31'],'explicit_source_sessions':486,'canonical_calendar_dates_sha256':canonical(calendar),'source_priority':PRIORITY,'source_directories_checked':sources,'fully_covered_reuse_names':len(selected),'selected_reuse_count_by_directory':dict(routecounts),'missing_or_incomplete_names':len(missing),'missing_or_incomplete_instruments':missing,'incomplete_source_options':incomplete,'cross_cache_normalized_raw_core_conflicts':conflicts,'reuse_requires_conflict_resolution_before_capture':bool(conflicts),'selected_reuse':selected,'per_instrument':details,'capture_budget_estimate_not_authorization':{'missing_names':len(missing),'queries_per_missing_name':4,'components':['one unadjusted daily query2023-12-29..2025-12-31','one dividend2024operate-year query','one dividend2025operate-year query','one adjustment-factor query2023-12-29..2025-12-31'],'maximum_new_financial_logical_queries_if_one_attempt_each':len(missing)*4,'reuse_financial_queries':0,'new_calendar_queries':0,'login_logout_administrative_calls_excluded_from_financial_budget':True,'requires_frozen_request_and_separate_capture_review':True},'skipped_mixed_or_2026_sources':skip,'legacy_source_request_anchor':{'file':str(vmrequest.relative_to(R)),'sha256':sha(vmrequest)},'source_admission_for_account_replay':False,'corporate_action_completeness_verified':False,'primary_tax_or_lifecycle_proofs_verified':False,'PIT_or_historical_arrival_verified':False,'source_packets_modified':False,'strategy_or_targets_changed':False,'account_replay_performed':False,'portfolio_returns_computed':False,'new_source_queries':0,'2026_price_or_financial_records_read':False,'imports_project_code':False,'audit_code_sha256':sha(Path(__file__)),'limitations':['Bounded inventory covers seven existing physically pre2026-clipped capture roots; missing means absent or incomplete in this set, not absent throughout all local archives.','Reuse preserves literal packet bytes and provenance. Metadata/provenance may reference later capture timestamps; accepted bars/operative corporate records are clipped to2025.','A full486-date raw calendar is source coverage only: ST/halt rows remain source facts and do not imply ordinary-share or account eligibility.','No issuer-primary corporate-action, capital-tax, lifecycle, intraday/PIT or account admission is conferred.','Four-query-per-missing-code budget is an estimate using the existing bounded daily/dividend/adjustment component pattern, not a request to perform queries.']}
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':str(OUT),'sha256':sha(OUT),'code_sha256':report['audit_code_sha256'],'reuse':len(selected),'missing':len(missing),'query_budget':4*len(missing),'routes':dict(routecounts),'incomplete_options':[(v['instrument'],v['directory'],len(v['missing_sessions'])) for v in incomplete],'conflicts':len(conflicts)},indent=2))
