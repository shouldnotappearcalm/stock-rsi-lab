"""Independent read-only output review and nonbinding field-map draft; stdlib only."""
from pathlib import Path
from decimal import Decimal as D
from collections import Counter
import copy,hashlib,json
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
RAW=B/'price-delay-raw-horizon-v2-20261021'
ROOTS={
 'low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json':'01dcd1f8e96c544243ee88c446075cdaf68e8fd772dc45813144c85094251c0a',
 'low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json':'7fdec0f62c3a83842c9e447a19416d9dd4b4165a44669484822e9d841c5a7d80',
 'szse-value-momentum-full-reviewed-proofs-20261021.json':'ac0cf40ccc3dc1d4ab3a723bfcd1e75cb34f51cac3068bba879b12033a09b9d8',
 'szse-value-full-corporate-notices-20261017/reviewed-manifest.json':'0c14b8e9bfa421a20b5bb6b1befd4b8c0c7c93e674b9f87e910394efacd64723',
 'return-family-corporate-notices-20261017/reviewed-manifest.json':'a77d0caf8788616fee773c1c4e5a0b9614956cbd0f79732644fee0b0b85b1bd8',
 'reversal-full-corporate-notices-20261017/reviewed-manifest.json':'ff7d6c9e1a17978c74d204a616f1bd965600a5605d02667570256d881ccbf022'}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def need(ok,message):
 if not ok:raise ValueError(message)
bound={}
def auth(p,h):
 need(sha(p)==h,'changed bytes: '+str(p));bound[str(p)]=h
inventory_path=B/'price-delay-horizon-corporate-inventory-20261021.json'
auth(inventory_path,'4ca1c82931ceca0129b01ea1660ca82d7b4ca6b075dd67ba06e96554ff88d9d5');v=read(inventory_path)
request_path=R/'experiments/qlib/price-delay-horizon-corporate-inventory-request.json';auth(request_path,'7bb7337030b4fe6b7fd2c16ada9f31fd2b6c58db1c84f503cbeb366a3db98292');request=read(request_path)
auth(R/request['script_file'],'680e6cc96fbacd9563386e424751a6cd16de4d14cdd242c55ad3c5e52aaffa3f');auth(R/request['protocol_file'],request['protocol_sha256'])
need(v['audit_code_sha256']==request['script_sha256'],'inventory source code mismatch')
auth(v['independent_raw_audit_file'],'a7bf3324200deb497ba93327fe41c2d4e6ae7fb5b39d7ed81916aaca91ded753');a=read(v['independent_raw_audit_file'])
auth(RAW/'manifest.json','9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490');m=read(RAW/'manifest.json')
need(a['manifest_sha256']==v['raw_manifest_sha256']==sha(RAW/'manifest.json') and a['all203_packets_676_sessions_verified'] is True,'raw independent completeness binding')
need(m['local_assembly_complete'] is True and a['critical_or_important_findings']==[],'raw terminal audit has findings')
auth(RAW/'calendar.json',m['calendar_sha256']);sessions=read(RAW/'calendar.json')['sessions'];need(len(sessions)==676 and sessions==sorted(set(sessions)) and sessions[0]=='2023-12-29' and sessions[-1]=='2026-10-20','calendar bounds')
target_path=B/'price-delay-horizon-formations-20261021/candidate_targets.json';auth(target_path,'5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923');targets=read(target_path);codes={c for t in targets.values() for c in t['weights']}
old_manifest=B/'price-delay-raw-dev-20261021/manifest.json';auth(old_manifest,'b179d4e987ad2ee93d0b152d817486c29737c6d605abdad1a15c3fd4713d6b67');om=read(old_manifest);old=set(om['per_code_sha256']);future=codes-old
need(len(targets)==34 and len(codes)==203 and len(old)==151 and len(future)==52 and codes==set(m['per_code_sha256']),'fixed name/target scope')
auth(B/'price-delay-pre2026-formations-20261021/targets.json','03acf78c10c10376b5764b0d1399d1631af08a608aa865575aa1bd56203fad0c')
need({d:t for d,t in targets.items() if d<'2026-01-01'}==read(B/'price-delay-pre2026-formations-20261021/targets.json')['price_delay_d1'],'old24 target prefix')
old_eventdir=B/'price-delay-account-source-events-20261021'
auth(old_eventdir/'derived_events.json','465bab82c1a2c9b8566011230a3858946ef23667c4ba04e5248b088f6b0e70d0');auth(old_eventdir/'event_source_receipts.json','a1de87c2f69544e92256e4c534ecf8d6dad5a3c49291302cd2d6b71269e51cc5')
need(len(read(old_eventdir/'derived_events.json'))==len(read(old_eventdir/'event_source_receipts.json'))==378,'old378')
packets={};active={};excluded={};prefix={};blank=set();positive_cap={};positive_stock={};unmatched_factor={};missing_ref={};samefactor=set();latefactor=set();future_adjustments=[]
for code,h in sorted(m['per_code_sha256'].items()):
 p=RAW/'codes'/(code+'.json');auth(p,h);packet=read(p);packets[code]=packet
 need(packet['instrument']==code and packet['window']==['2023-12-29','2026-10-20'] and [x['date'] for x in packet['bars']]==sessions,'raw identity/calendar')
 if code in old:
  p=B/'price-delay-raw-dev-20261021/codes'/(code+'.json');auth(p,om['per_code_sha256'][code]);original=read(p)
  prefix[code]={f:[r for r in packet[f] if r[k]<'2026-01-01']==original[f] for f,k in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]};need(all(prefix[code].values()),'old prefix')
 for i,row in enumerate(packet['distributions']):
  ex=row['dividOperateDate'];key=code+'|'+ex
  if '2026-01-01'<=ex<='2026-10-20':
   need(key not in active,'duplicate vendor event');active[key]={'instrument':code,'row_index':i,'source_row':row,'source_row_sha256':digest(row),'packet_sha256':h}
   if not row['dividReserveToStockPs']:
    need(D(row['dividCashPsBeforeTax'])>0 and D(row['dividStocksPs'])==0 and row['dividCashStock'].startswith('10派') and '送' not in row['dividCashStock'] and '转' not in row['dividCashStock'] and not row['dividStockMarketDate'],'blank capital is not explicit cash-only');blank.add(key)
   elif D(row['dividReserveToStockPs'])>0:positive_cap[key]=row
   if D(row['dividStocksPs'])>0:positive_stock[key]=row
  elif code in future and ex<'2026-01-01':excluded[(code,i)]={'instrument':code,'row_index':i,'event_key':key,'source_row':row,'source_row_sha256':digest(row),'classification':'OUT_OF_ACCOUNT_SCOPE_FUTURE_ONLY_PRE2026'}
 future_adjustments.extend({'instrument':code,'row_index':i,'source_row':row,'source_row_sha256':digest(row),'classification':'FUTURE_ONLY_PRE2026_ADJUSTMENT_NOT_AN_ACCOUNT_ENTITLEMENT'} for i,row in enumerate(packet['adjustments']) if code in future and row['dividOperateDate']<'2026-01-01')
 exs={r['dividOperateDate'] for r in packet['distributions'] if '2026-01-01'<=r['dividOperateDate']<='2026-10-20'}
 bars=[r for r in packet['bars'] if r['date']>='2025-12-31'];need(bars[0]['date']=='2025-12-31','missing boundary');ix={r['date']:i for i,r in enumerate(bars)};previous=None
 for bar in bars:
  at=bar['date'];ref=D(bar['preclose']) if bar['preclose'] else None
  if at>='2026-01-01' and previous is not None and ref is not None and ref>0 and abs(previous-ref)>D('.005') and at not in exs:
   missing_ref[code+'|'+at]={'bar':bar,'bar_sha256':digest(bar),'previous_valid_close':str(previous)}
  if bar['close'] and D(bar['close'])>0:previous=D(bar['close'])
 for row in packet['adjustments']:
  at=row['dividOperateDate'];key=code+'|'+at
  if not '2026-01-01'<=at<='2026-10-20':continue
  if at in exs:samefactor.add(key)
  elif ix[at]>0 and bars[ix[at]-1]['date'] in exs:latefactor.add(key)
  else:unmatched_factor[key]={'row':row,'sha256':digest(row)}
roots={};proof_map={};docs={}
for root,h in ROOTS.items():
 auth(B/root,h);d=read(B/root);roots[root]=d
 for document in d['documents']:
  p=Path(document['source_path']) if document.get('source_path') else (B/root).parent/document['file']
  if root.startswith('szse-value-momentum-full-') and not document.get('source_path'):p=B/'low-beta60-corporate-reviewed-horizon-20261021'/document['file']
  auth(p,document['sha256']);docs.setdefault(document['sha256'],[]).append({'file':str(p),'sha256':document['sha256'],'document':document,'root_file':str(B/root),'root_sha256':h})
 for field in ['capital_tax','stock_dividend_tax_bases','unresolved_tax','cash_overrides']:
  for key,p in d.get(field,{}).items():
   if key.split('|')[0] in codes and '2026-01-01'<=key.split('|')[1]<='2026-10-20':proof_map.setdefault((field,key),[]).append((root,p))
 for p in d.get('supplementary_distributions',[]):
  key=p['instrument']+'|'+p['record']['dividOperateDate']
  if p['instrument'] in codes and '2026-01-01'<=p['record']['dividOperateDate']<='2026-10-20':proof_map.setdefault(('supplementary_distributions',key),[]).append((root,p))
local_missing={key for field,key in proof_map if field=='supplementary_distributions' and key not in active}
known_cap={key for field,key in proof_map if field=='capital_tax' and key in positive_cap}
unknown_cap=set(positive_cap)-known_cap
need(set(unmatched_factor)==set(missing_ref),'adjustment and preclose gaps disagree')
expected_missing={'SH601598|2026-10-20','SH601918|2026-02-06','SH601966|2026-06-24','SH603233|2026-10-19','SH603605|2026-10-16','SZ002608|2026-10-19','SZ002756|2026-10-20','SZ002812|2026-10-20'}
need(set(unmatched_factor)==expected_missing and len(active)==227 and len(excluded)==131 and len(local_missing)==6,'independent expected counts/sets')
need(unknown_cap=={'SH603596|2026-05-11','SH603606|2026-05-26','SZ000937|2026-06-17','SZ002831|2026-06-04'},'unknown capital set')
def verify_output(output):
 need(output['all_2026_vendor_distribution_rows_count']==len(active) and output['future_only_pre2026_excluded_row_count']==len(excluded),'reported counts')
 rows={x['event_key']:x for x in output['all_2026_vendor_distribution_rows']};need(set(rows)==set(active),'active vendor rows set')
 for key,expected in active.items():
  need(all(rows[key][k]==value for k,value in expected.items()),'literal source row/index/digest mismatch')
  for c in rows[key]['primary_matches']:
   need(c['financial_admission_granted'] is False and c['source_receipt_chain_revalidation_required'] is True,'metadata promoted to admission')
 need({(x['instrument'],x['row_index']):x for x in output['future_only_pre2026_excluded_rows']}==excluded,'future-only excluded rows differ')
 need(output['future_only_pre2026_adjustments_excluded_from_account_entitlements']==future_adjustments,'future-only adjustments differ')
 need(set(output['local_primary_supplement_candidates_missing_vendor'])==local_missing,'six local supplements differ')
 need(set(output['new_unresolved_capital_zero_record_ownership_keys'])==unknown_cap and output['new_unresolved_stock_tax_basis_zero_record_ownership_keys']==[],'unknown tax guards')
 q=output['questions'];factor={x['instrument']+'|'+x['day'] for x in q if x['classification']=='ADJUSTMENT_WITHOUT_VENDOR_DISTRIBUTION_PRIMARY_EVIDENCE_REQUIRED'};refs={x['instrument']+'|'+x['day'] for x in q if x['classification']=='RAW_PRECLOSE_WITHOUT_VENDOR_EVENT'}
 need(factor==refs==set(unmatched_factor),'eight missing event questions differ')
 need(output['question_classification_counts']==dict(Counter(x['classification'] for x in q)),'question count fields')
 need(output['question_classification_counts']=={'VENDOR_EVENT_COMPONENT_OR_PRIMARY_MATCH_QUESTION':227,'ADJUSTMENT_SAME_DAY_VENDOR_EVENT_SOURCE_LABEL_ONLY':227,'ADJUSTMENT_WITHOUT_VENDOR_DISTRIBUTION_PRIMARY_EVIDENCE_REQUIRED':8,'RAW_PRECLOSE_WITHOUT_VENDOR_EVENT':8,'LOCAL_PRIMARY_SUPPLEMENT_CANDIDATE_WITH_NO_VENDOR_EVENT':6},'independent question class counts')
 for flag in ['PDF_authentication_is_financial_admission','new_events_compiled','new_proofs_projected','source_or_repository_modified','account_or_ROI_run','portfolio_returns_computed','historical_PIT_certified','strict_statutory_tax_certification','actual_FIFO_tax_liability_verified','source_or_account_admission','actual_zero_record_ownership_verified']:need(output[flag] is False,'unsupported admission claim')
 need(output['old_unverified_tax_guard_retained']=='SH603596|2024-05-20','old unknown guard lost')
verify_output(v)
for x in v['all_2026_vendor_distribution_rows']:
 key=x['event_key'];need(('BLANK_CAPITAL_EXPLICIT_CASH_ONLY_ZERO_CANDIDATE' in x['component_questions'])==(key in blank),'blank classification differs')
 for c in x['primary_matches']:
  root=Path(c['reviewed_manifest_file']).relative_to(B).as_posix();need(root in ROOTS and c['reviewed_manifest_sha256']==ROOTS[root] and digest(c['proof'])==c['proof_sha256'],'candidate proof root/digest')
  field={'CAPITAL_TAX_PROOF_CANDIDATE':'capital_tax','STOCK_TAX_BASIS_PROOF_CANDIDATE':'stock_dividend_tax_bases','UNRESOLVED_TAX_LITERAL_GUARD':'unresolved_tax','PRIMARY_CASH_PRECISION_CANDIDATE':'cash_overrides'}.get(c['proof_kind'])
  if field:need(c['proof']==roots[root][field][key],'candidate original tax/precision proof changed')
  need(c['metadata_conflicts']==[],'undisclosed metadata contradiction')
# Mutate only in-memory report, not the inventory or original packets.
neg={}
for label in ['wrong_count','drop_missing_event','activate_future_pre2026_row','upgrade_blank_cash_metadata_admission','erase_unknown_tax_guard']:
 bad=copy.deepcopy(v)
 if label=='wrong_count':bad['all_2026_vendor_distribution_rows_count']=228
 elif label=='drop_missing_event':bad['questions']=[x for x in bad['questions'] if not (x.get('instrument')=='SH603233' and x.get('day')=='2026-10-19')]
 elif label=='activate_future_pre2026_row':bad['all_2026_vendor_distribution_rows'].append({**bad['future_only_pre2026_excluded_rows'][0]})
 elif label=='upgrade_blank_cash_metadata_admission':
  row=next(x for x in bad['all_2026_vendor_distribution_rows'] if x['event_key'] in blank and x['primary_matches']);row['primary_matches'][0]['financial_admission_granted']=True
 else:bad['new_unresolved_capital_zero_record_ownership_keys'].remove('SZ000937|2026-06-17')
 try:verify_output(bad)
 except (ValueError,KeyError):neg[label]=True
 else:raise ValueError('negative accepted: '+label)
# Mapping is an analyst's reference, not an evaluator reviewed-manifest/proof.
def provenance(root,p):
 refs=[]
 for h in [p.get('source_sha256'),p.get('implementation',{}).get('source_sha256'),p.get('supplement',{}).get('source_sha256')]:
  if h:refs.extend(docs[h])
 return {'original_reviewed_manifest_file':str(B/root),'original_reviewed_manifest_sha256':ROOTS[root],'original_proof_literal':p,'original_proof_sha256':digest(p),'primary_PDF_references':refs,'PDF_or_metadata_match_is_financial_admission':False}
cashmaps=[]
for key in sorted(local_missing):
 choices=proof_map[('supplementary_distributions',key)];unique={digest(p) for _,p in choices}
 need(len(unique)==1,'duplicate local cash source proof conflict')
 root,p=choices[0];row=p['record'];cashmaps.append({'event_key':key,'source_kind_if_later_admitted':'PRIMARY_NOTICE_SUPPLEMENT',
  'notice_record_template_literal':row,'cash_per_eligible_original_share_CNY':row['dividCashPsBeforeTax'],
  'announced':row['dividPlanDate'],'recorded':row['dividRegistDate'],'ex_date':row['dividOperateDate'],'pay_date':row['dividPayDate'],'listed':row['dividStockMarketDate'] or None,
  'stock_per_share':row['dividStocksPs'],'capital_per_share':row['dividReserveToStockPs'],'same_date_vendor_row_absent':key not in active,
  'source_provenance':[provenance(n,x) for n,x in choices], 'event_compiled':False,'proof_projection_written':False,'admitted':False,
  'must_bind_before_projection':['new frozen full-raw manifest and all packets','source receipt/content review hashes','same issuer/economic ex-date unique, no vendor duplicate','eligible-holder cash, not diluted reference','exact source announcement/record/ex/pay dates; ordinary unrestricted A-share scenario']})
capitalmaps=[]
for key in sorted(known_cap):
 choices=proof_map[('capital_tax',key)];need(len({digest(p) for _,p in choices})==1,'capital tax source conflict')
 row=positive_cap[key];p=choices[0][1];capitalmaps.append({'event_key':key,'literal_raw_vendor_row':row,'source_row_sha256':digest(row),'packet_sha256':m['per_code_sha256'][key.split('|')[0]],
  'source_fields':{'cash':row['dividCashPsBeforeTax'],'capital':row['dividReserveToStockPs'],'stock':row['dividStocksPs'],'announced':row['dividPlanDate'],'recorded':row['dividRegistDate'],'ex_date':row['dividOperateDate'],'pay_date':row['dividPayDate'],'listed':row['dividStockMarketDate']},
  'evidence_level_to_preserve':'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE' if p.get('evidence_kind')=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE' else 'DIRECT_ISSUER_EVENT_SHARE_PREMIUM_NO_TAX_STATEMENT',
  'source_provenance':[provenance(n,x) for n,x in choices],'new_verified_exempt_flag_projected':False,'strict_statutory_certification':False,'admitted':False})
precision=[]
for (field,key),choices in proof_map.items():
 if field=='cash_overrides' and key in active:
  need(len({digest(p) for _,p in choices})==1,'precision cache proofs conflict')
  precision.append({'event_key':key,'original_precision_proof_sources':[provenance(root,p) for root,p in choices],'row_digest_exact_match':all(p['source_row_sha256']==active[key]['source_row_sha256'] for _,p in choices),'admitted':False})
# The new SH603233 review remains outside original inventory allowlist; bind as separate evidence only.
single=R/'experiments/qlib/price-delay-horizon-single-primary-content-review.json';auth(single,'b20a662cc6149c96397089a769f3e43dd96b85039c13ea544441cb4a17c6285f')
single_ind=R/'experiments/qlib/price-delay-horizon-single-primary-independent-review.json';auth(single_ind,'32a97c9f083df960b7b0b111bac72b66c198f684ba96018c8ea0d50b5fe8d97e')
sd=read(single)['documents'][0];auth(B/'price-delay-horizon-missing-primary-20261021'/sd['file'],sd['sha256'])
separate={'event_key':'SH603233|2026-10-19','primary_content_review_file':str(single),'primary_content_review_sha256':sha(single),'independent_review_file':str(single_ind),'independent_review_sha256':sha(single_ind),'primary_PDF_sha256':sd['sha256'],'cash_per_eligible_original_share_CNY':sd['cash_per_original_share_CNY'],'inside_original_six_root_inventory_allowlist':False,'new_proof_projected':False}
notice={'status':'NONBINDING_PRIMARY_FIELD_MAPPING_DRAFT_NOT_A_REVIEWED_MANIFEST', 'inventory_sha256':sha(inventory_path),'mapping_code_sha256':sha(__file__),
 'six_cached_cash_supplement_candidates':cashmaps,'known_capital_tax_candidates':capitalmaps,'cached_cash_precision_reference_only':precision,
 'unknown_capital_source_rows_and_guards':[{'event_key':k,'literal_vendor_row':positive_cap[k],'source_row_sha256':digest(positive_cap[k]),'verified_exempt':False,'actual_zero_record_ownership_verified':False,'existing_unresolved_tax_provenance':[provenance(root,p) for root,p in proof_map.get(('unresolved_tax',k),[])],'source_evidence_question':'Preserve unresolved; raw scalar/display differences are not primary evidence.'} for k in sorted(unknown_cap)],
 'new_SH603233_separate_existing_content_evidence':separate,'SH603605_primary_source_pending_not_inferred_from_factor':True,
 'original378_events_and_receipts_immutable':True,'original_pre2026_SH603596_guard_receipt_literal':next(x for x in read(old_eventdir/'event_source_receipts.json') if x['instrument']=='SH603596' and x['ex_date']=='2024-05-20'),'new_proofs_projected':False,'new_events_compiled':False,'account_admission':False,'portfolio_returns_computed':False}
map_path=Path('/tmp/price-delay-horizon-corporate-proof-field-map-draft-20261021.json');need(not map_path.exists(),'preserve mapping draft');map_path.write_text(json.dumps(notice,indent=2,ensure_ascii=False)+'\n')
for p,h in bound.items():need(sha(p)==h,'input changed during peer review')
report={'status':'INDEPENDENT_HORIZON_CORPORATE_INVENTORY_OUTPUT_COUNTS_SOURCE_ROWS_AND_GUARDS_VERIFIED_NOT_ADMISSION','review_code_sha256':sha(__file__),'request_sha256':sha(request_path),'inventory_sha256':sha(inventory_path),'inventory_code_sha256':v['audit_code_sha256'],'raw_manifest_sha256':sha(RAW/'manifest.json'),
 'all203_raw_packets_authenticated':True,'original151_literal_prefixes_and_original378_event_receipt_files_unchanged':True,
 'names_reconstructed':203,'old_names':151,'future_only_names':52,'sessions':676,'targets':34,'vendor_2026_events_reconstructed':len(active),
 'future_only_pre2026_distribution_rows_excluded_reconstructed':len(excluded),'future_only_pre2026_adjustment_rows_excluded_reconstructed':len(future_adjustments),
 'blank_capital_explicit_cash_only_zero_candidates':len(blank),'blank_capital_is_a_new_tax_exemption_or_admission':False,
 'positive_capital_events':len(positive_cap),'positive_stock_dividend_events':len(positive_stock),'known_capital_proof_candidate_keys':sorted(known_cap),'unresolved_capital_zero_record_ownership_keys':sorted(unknown_cap),
 'same_day_vendor_adjustment_keys':len(samefactor),'late_factor_keys':sorted(latefactor),'eight_missing_vendor_event_question_keys':sorted(unmatched_factor),
 'same_eight_keys_derived_independently_from_preclose_and_adjustments':True,'six_fixed_local_cash_supplement_candidate_keys':sorted(local_missing),
 'new_separately_reviewed_SH603233_not_silently_added_to_inventory_allowlist':True,'SH603605_no_primary_source_admitted':True,
 'all227_original_literal_rows_indices_packet_hashes_and_row_digests_preserved':True,'all131_excluded_rows_literal_digests_and_future_only_scope_verified':True,
 'metadata_candidates_never_grant_financial_admission':True,'all_bound_inputs_unchanged_after_review':True,'negative_controls_rejected':neg,
 'field_mapping_draft_file':str(map_path),'field_mapping_draft_sha256':sha(map_path),
 'source_content_questions_for_next_phase':[{'event_key':'SZ002831|2026-06-04','question':'Scalar cash0.803813/capital0.401906 versus vendor display10转4.019063派8.038127 (0.4019063/0.8038127 per share) is raw internal precision/rounding information only; original primary notice must establish eligible-holder ratios and tax basis before any projection. Do not derive a correction from display/price/factor or silently use a cash-only precision contract on a capital event.'}],
 'critical':[],'important':[],'minor':[],'critical_or_important_findings':[],
 'imports_production_inventory_or_account_code':False,'new_event_or_proof_compilation_run':False,'source_or_repository_modified':False,'network_calls':0,'account_or_ROI_run':False,
 'strict_statutory_tax_certification':False,'actual_FIFO_tax_liability_verified':False,'actual_zero_record_ownership_verified':False,'historical_PIT_certification':False,
 'source_or_account_admission':False,'portfolio_returns_computed':False,
 'limits':['This peer review independently recounts questions and original rows; does not reread all prior PDFs or authenticate actual shareholder entitlements/tax settlement.',
 'No local proof candidate is sufficient by presence alone; the mapping draft preserves original proof levels and still requires frozen source projection/content provenance validation.',
 'Eight date/source gaps are not themselves proof of eight economic dividends. Six have fixed local primary candidates; one has separately reviewed new primary evidence; SH603605 is still pending.',
 'Zero record-date inventory is not established here; all unresolved taxes and the original pre2026 SH603596 guard must remain enforceable.']}
output=Path('/tmp/price-delay-horizon-corporate-inventory-output-review-20261021.json');need(not output.exists(),'preserve peer review');output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print('review',output,sha(output));print('field_mapping_draft',map_path,sha(map_path));print('counts',len(active),len(excluded),len(unmatched_factor),len(blank),len(positive_cap),len(future_adjustments))
