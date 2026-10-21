"""Bounded terminal pre2026 corporate/lifecycle questions, not source admission."""
import argparse,hashlib,json,re
from collections import Counter,defaultdict
from decimal import Decimal as D
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
CAPTURE=B/'low-market-residual-vol1m-raw-pre2026-20261021'
AUDIT=Path('/tmp/low-market-residual-vol1m-pre2026-raw-source-audit-20261021.json')
OLD=Path('/tmp/low-market-residual-vol1m-pre2026-corporate-cache-inventory-20261021.json')
AUDIT_SHA='fa8baf8c5091cd1b96e617b2b41da4a50eb6082517f58dacd32d52ee1e5d36c7'
MANIFEST_SHA='7c7e56f5ec3301a9b1d82748bd90603f255ef8a1c602b64cf34b3ebaedef62b3'
OLD_SHA='e20a92afef7f1b70724516a6c30f1bc16a1d83eeb2015a8ee1da54ee17166663'
ROOTS={B/n for n in ('price-delay-corporate-reviewed-20261021','low-beta60-corporate-reviewed-20261021','szse-value-momentum-account-sources-20261021','budgeted-residual-corporate-reviewed-20261021','illiquidity-corporate-reviewed-20261020')}
PDF_ROOTS=ROOTS|{B/'szse-value-momentum-primary-capture-20261021'}
START,END='2023-12-29','2025-12-31'
def need(v,s):
 if not v:raise ValueError(s)
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
bound={}
def auth(p,h):
 p=Path(p);need(sha(p)==h,'immutable source changed '+str(p));bound[str(p)]=h

def classify(row):
 cash=D(row['dividCashPsBeforeTax']) if row['dividCashPsBeforeTax'] else None
 stock=D(row['dividStocksPs']) if row['dividStocksPs'] else None
 capital=D(row['dividReserveToStockPs']) if row['dividReserveToStockPs'] else None
 display=row.get('dividCashStock','')
 syntax=bool(cash is not None and cash>0 and stock==0 and display.startswith('10派') and '送' not in display and '转' not in display and not row['dividStockMarketDate'])
 return cash,stock,capital,syntax

def source_record(code,row,p):return {'instrument':code,'event_key':code+'|'+row['dividOperateDate'],'source_row_sha256':digest(row),'vendor_row':row,'packet_path':str(CAPTURE/'codes'/(code+'.json')),'packet_sha256':manifest['per_code_sha256'][code],'from_fresh_capture_code':code in fresh}

auth(AUDIT,AUDIT_SHA);audit=read(AUDIT);auth(OLD,OLD_SHA);old=read(OLD);auth(CAPTURE/'manifest.json',MANIFEST_SHA);manifest=read(CAPTURE/'manifest.json')
need(audit['status']=='PASS_INDEPENDENT_SOURCE_CAPTURE_AUDIT' and audit['capture_complete'] is True and audit['manifest_sha256']==MANIFEST_SHA and audit['complete_packets_saved']==361 and audit['critical_or_important_findings']==[] and audit['pending_codes']==[],'terminal source audit gate')
need(audit['source_window']==[START,END] and audit['portfolio_returns_computed'] is False and audit['account_replay_performed'] is False and audit['network_used_by_auditor'] is False,'source-only audit scope')
need(manifest['window']==[START,END] and manifest['capture_complete'] is True and manifest['names']==manifest['requested_names']==361 and manifest['pending_codes']==[] and manifest['errors_sha256']=={} and manifest['abnormal_exit'] is None and manifest['request_sha256']==audit['request_sha256'],'terminal manifest identity/completeness')
need(manifest['per_code_sha256']==audit['packet_sha256'] and manifest['query_reservations_consumed']==240 and manifest['admitted_for_account_replay'] is False and manifest['corporate_action_completeness_verified'] is False,'authenticated terminal packet map/source-admission bounds')
auth(CAPTURE/'calendar.json',manifest['calendar_sha256']);sessions=read(CAPTURE/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'explicit pre2026 window')
index={d:i for i,d in enumerate(sessions)};target=Path(old['target_file']);auth(target,old['target_sha256']);targets=read(target)['low_market_residual_vol_1m'];codes={c for x in targets.values() for c in x['weights']}
need(len(targets)==24 and len(codes)==361 and set(manifest['per_code_sha256'])==codes and manifest['target_sha256']==old['target_sha256'],'fixed361 target union')
fresh=set(manifest['fresh_codes']);need(len(fresh)==60 and len(set(codes)-fresh)==301,'301reuse/60fresh split changed')
# Reauthenticate only the five allowed old pre2026 reviewed source proposals/PDFs.
for root in old['reviewed_roots_authenticated']:
 path=Path(root['path']);need(path.parent in ROOTS,'unregistered proof root');auth(path,root['sha256'])
for doc in old['in_scope_PDFs']:
 path=Path(doc['pdf_path']);need(path.parent in PDF_ROOTS,'unregistered pre2026 PDF root');auth(path,doc['pdf_sha256'])
# No old account/ROI, full/horizon proof directory, or new primary source is read.
proofs=old['proof_candidates'];docs=old['in_scope_PDFs'];components=old['independently_previously_reviewed_components'];links=old['known_later_factor_relationships']
bykey=defaultdict(list)
for i,p in enumerate(proofs):bykey[p['event_key']].append((i,p))
oldrows={x['event_key']:x for x in old['all_selected_existing_vendor_events']};oldunmatched={(x['instrument'],x['day']) for x in old['source_coverage_questions'] if x['issue']=='ADJUSTMENT_WITHOUT_SAME_DATE_VENDOR_DISTRIBUTION'}
allrows=[];noncash=[];unmatched=[];without_adjust=[];blank_bad=[];blank_good=[];preclose=[];gap_notcontinuous=[];packetfacts=[];lifecycles=[];old_row_changes=[];newrows=[];duplicatekeys=[]
seen=set();counts=Counter();packets={}
for code,h in sorted(manifest['per_code_sha256'].items()):
 need(re.fullmatch('(SH|SZ)[0-9]{6}',code),'unsafe issuer path');path=CAPTURE/'codes'/(code+'.json');auth(path,h);p=read(path);packets[code]=p
 need(p['instrument']==code and p['window']==[START,END] and [r['date'] for r in p['bars']]==sorted({r['date'] for r in p['bars']}) and all(r['date'] in index for r in p['bars']),'packet source identity/calendar')
 need(all(START<=r['dividOperateDate']<=END for r in p['distributions']+p['adjustments']) and not p['quarantine'],'accepted pre2026 components only')
 counts.update({'bar_rows':len(p['bars']),'distributions':len(p['distributions']),'adjustments':len(p['adjustments']),'quarantines':len(p['quarantine'])})
 exs={r['dividOperateDate'] for r in p['distributions']};ads={r['dividOperateDate'] for r in p['adjustments']};missing=sorted(set(sessions)-{r['date'] for r in p['bars']})
 packetfacts.append({'instrument':code,'packet_sha256':h,'from_fresh_capture_code':code in fresh,'bars':len(p['bars']),'vendor_distributions':len(p['distributions']),'adjustments':len(p['adjustments']),'missing_sessions':missing})
 for row in p['distributions']:
  fact=source_record(code,row,p);key=fact['event_key'];allrows.append(fact)
  if key in seen:duplicatekeys.append(key)
  seen.add(key)
  if key in oldrows:
   if digest(row)!=oldrows[key]['row_sha256']:old_row_changes.append({'event_key':key,'old_row':oldrows[key]['vendor_row'],'terminal_row':row})
  else:newrows.append(fact)
  cash,stock,capital,syntax=classify(row)
  support=[{'old_inventory_proof_index':i,'proof_type':q['proof_type'],'reviewed_manifest':q['reviewed_manifest'],'reviewed_manifest_sha256':q['reviewed_manifest_sha256'],'pdf_path':q['pdf_path'],'pdf_sha256':q['pdf_sha256'],'proof_literal':q['proof_literal']} for i,q in bykey[key]]
  comp=[q for q in components if q['event_key']==key]
  md=[q for q in docs if q['instrument']==code and q['announcement_day']==row['dividPlanDate']]
  for sp in support:
   proof=sp['proof_literal'];need(proof.get('source_sha256')==sp['pdf_sha256'],'source proof PDF mismatch')
   if sp['proof_type']=='cash_overrides':need(proof['source_row_sha256']==digest(row) and D(proof['expected_vendor_cash_per_share'])==cash,'precision proof cannot rebind a different vendor row')
   if sp['proof_type']=='stock_dividend_tax_bases':need(D(proof['expected_stock_per_original_share'])==stock,'stock basis ratio mismatch')
  if stock is None or stock>0 or capital is not None and capital>0:
   taxsupport=[q for q in support if q['proof_type'] in ('capital_tax','stock_dividend_tax_bases')]
   noncash.append({**fact,'cached_proof_matches':taxsupport,'cached_component_reviews':comp,'matching_original_announcement_PDFs':md,'requires_missing_event_specific_tax_or_stock_basis':not bool(taxsupport),'component_economics_re_reviewed_now':False,'actual_registered_ownership_unknown':True,'source_only_not_account_admission':True})
  if capital is None or cash is None or stock is None:
   record={**fact,'cash_only_blank_capital_syntax':syntax,'blank_cash':cash is None,'blank_stock':stock is None,'blank_capital':capital is None,'cached_component_or_tax_support':support,'tax_exemption_or_income_inferred_from_blank':False}
   (blank_good if capital is None and syntax and cash is not None and stock is not None else blank_bad).append(record)
  if row['dividOperateDate'] not in ads:without_adjust.append({**fact,'additional_income_or_adjustment_synthesized':False})
 for row in p['adjustments']:
  day=row['dividOperateDate']
  if day in exs:continue
  prior=sessions[index[day]-1] if index[day]>0 else None;earlier=[r for r in p['distributions'] if r['dividOperateDate']==prior]
  known=[q for q in links if q['link_literal']['instrument']==code and q['link_literal']['adjustment_source_day']==day]
  life=[q for q in old['lifecycle_candidates'] if q['instrument']==code and q['proof_literal']['effective_date']==day]
  supplements=[{'old_inventory_proof_index':i,**q} for i,q in bykey[code+'|'+day] if q['proof_type']=='primary_cash_supplement']
  unmatched.append({'instrument':code,'day':day,'adjustment_row_sha256':digest(row),'raw_adjustment':row,'packet_sha256':h,'from_fresh_capture_code':code in fresh,'not_seen_in_old_inventory':(code,day) not in oldunmatched,
   'previous_explicit_session':prior,'vendor_distributions_on_previous_session':earlier,'cached_later_factor_relationships':known,'cached_primary_supplements':supplements,'cached_lifecycle_boundary':life,
   'factor_date_semantics_proven':False,'new_cash_or_equity_inferred':False,'question':'Same-date vendor row absent; a prior-session dividend/source label is not evidence of a second entitlement. Original primary or separately reviewed source-date semantics may resolve the coverage question.'})
 previous=None
 for row in p['bars']:
  if previous is not None:
   a=D(previous['close']) if previous.get('close') else None;b=D(row['preclose']) if row.get('preclose') else None
   if a is not None and a>0 and b is not None and b>0 and abs(a-b)>D('.005'):
    adjacent=index[row['date']]==index[previous['date']]+1
    traded=all(str(z.get('tradestatus'))=='1' and D(z.get('volume') or '0')>0 for z in (previous,row))
    q={'instrument':code,'day':row['date'],'previous_source_day':previous['date'],'previous_source_close':str(a),'source_preclose':str(b),'difference_reference_only':str(b-a),'previous_bar':previous,'current_bar':row,'packet_sha256':h,'from_fresh_capture_code':code in fresh,'calendar_adjacent':adjacent,'both_source_rows_traded':traded,'same_date_vendor_event':row['date'] in exs,'same_date_adjustment':row['date'] in ads,'cached_primary_supplement_indices':[i for i,v in bykey[code+'|'+row['date']] if v['proof_type']=='primary_cash_supplement'],'cash_not_derived_from_difference':True}
    (preclose if adjacent and traded else gap_notcontinuous).append(q)
  previous=row
# This is a question inventory: preserve same-key conflicts as explicit blockers,
# never drop/merge them to force the downstream event compiler to pass.
duplicate_groups=[{'event_key':key,'raw_rows':[q for q in allrows if q['event_key']==key],'economic_resolution_required_before_compilation':True,'rows_merged_or_deleted':False} for key in sorted(set(duplicatekeys))]
need(dict(counts)==manifest['totals']==audit['totals_reconstructed'] and counts['distributions']==860 and counts['adjustments']==875,'independent terminal source totals mismatch')
need(len(noncash)==13 and len(unmatched)==16,'independent13noncash/16unmatched counts mismatch')
need({(x['instrument'],x['vendor_row']['dividOperateDate'],x['source_row_sha256'],x['packet_sha256']) for x in noncash}=={(x['instrument'],x['ex_date'],digest(x['source_record']),x['packet_sha256']) for x in audit['noncash_distribution_records']},'noncash source identities disagree with independently bound capture audit')
need({(x['instrument'],x['day'],x['adjustment_row_sha256'],x['packet_sha256']) for x in unmatched}=={(x['instrument'],x['ex_date'],digest(x['source_record']),x['packet_sha256']) for x in audit['adjustment_without_same_exdate_distribution']},'unmatched source identities disagree with capture audit')
# Recheck old primary lifecycle identities and newly captured missing dates. No inventory claim.
for item in old['lifecycle_candidates']:
 code=item['instrument'];proof=item['proof_literal'];path=Path(item['pdf_path']);need(path.parent in PDF_ROOTS,'lifecycle PDF root');auth(path,proof['primary_document_sha256']);rows=packets[code]['bars'];missing=sorted(set(sessions)-{r['date'] for r in rows});review=item['authenticated_public_lifecycle_review']['literal'];boundary=proof['effective_date']
 need(boundary==review['listing_or_delisting_boundary'] and len(missing)==review['missing_sessions'] and all(d<boundary if review['missing_relation']=='BEFORE' else d>boundary for d in missing),'terminal missing lifecycle dates conflict with old primary boundary')
 need([rows[0]['date'],rows[-1]['date']]==[review['first_observed_session'],review['last_observed_session']],'terminal source observed lifecycle extent changed')
 lifecycles.append({'instrument':code,'original_PDF':str(path),'PDF_sha256':sha(path),'reviewed_manifest':item['reviewed_manifest'],'reviewed_manifest_sha256':item['reviewed_manifest_sha256'],'primary_boundary_proof_literal':proof,'new_packet_sha256':manifest['per_code_sha256'][code],'known_old_partial_packet_sha256':item['existing_partial_packet']['sha256'],'observed_rows':len(rows),'missing_sessions':missing,'missing_boundary_matches_primary':True,'current_candidate_target_days':[d for d,t in targets.items() if code in t['weights']],'actual_flat_inventory_at_missing_dates_verified':False,'actual_record_date_entitlement_verified':False,'rows_synthesized':False})
freshfacts=[q for q in packetfacts if q['from_fresh_capture_code']];missingproof=[x['event_key'] for x in noncash if x['requires_missing_event_specific_tax_or_stock_basis']]
need({x['event_key'] for x in oldrows.values()}<={x['event_key'] for x in allrows},'old cached event disappeared')
report={'status':'TERMINAL_PRE2026_CORPORATE_SOURCE_QUESTIONS_RECONSTRUCTED_NOT_PROJECTED_OR_ADMITTED','candidate':'low_market_residual_vol_1m','window':[START,END],
 'source_audit':{'path':str(AUDIT),'sha256':AUDIT_SHA,'status':audit['status']},'manifest_sha256':MANIFEST_SHA,'raw_request_sha256':manifest['request_sha256'],'old_cache_inventory':{'path':str(OLD),'sha256':OLD_SHA},'target_sha256':sha(target),'code_sha256':sha(Path(__file__)),
 'counts':{'authenticated_packets':361,'explicit_sessions':486,**dict(counts),'fresh_names':len(fresh),'fresh_vendor_distributions':sum(q['vendor_distributions'] for q in freshfacts),'fresh_adjustments':sum(q['adjustments'] for q in freshfacts),'vendor_events_not_in_old_cache_inventory':len(newrows),'duplicate_vendor_event_keys':len(duplicate_groups),'noncash':len(noncash),'noncash_without_reusable_tax_or_basis_proof':len(missingproof),'unmatched_adjustment_dates':len(unmatched),'distributions_without_same_date_adjustment':len(without_adjust),'cash_only_blank_capital_syntax':len(blank_good),'blank_component_syntax_not_cash_only':len(blank_bad),'contiguous_traded_preclose_anomalies_over_half_cent':len(preclose),'contiguous_traded_preclose_anomalies_without_same_date_vendor':sum(not q['same_date_vendor_event'] for q in preclose),'noncontiguous_or_nontraded_reference_changes_reported_separately':len(gap_notcontinuous),'lifecycle_boundaries':len(lifecycles)},
 'duplicate_vendor_event_groups':duplicate_groups,'compiler_has_unresolved_same_date_source_conflict':bool(duplicate_groups),
 'noncash_missing_event_specific_tax_or_basis':missingproof,'noncash_vendor_events':noncash,'unmatched_adjustments':unmatched,'blank_component_syntax_not_cash_only':blank_bad,'distributions_without_same_date_adjustment':without_adjust,
 'contiguous_traded_preclose_anomalies':preclose,'reference_changes_not_contiguous_traded_pair':gap_notcontinuous,'new_source_vendor_event_facts':newrows,'fresh60_packet_facts':freshfacts,'all361_packet_source_receipts':packetfacts,
 'unmatched_partition':{'prior_session_vendor_event':sum(bool(q['vendor_distributions_on_previous_session']) for q in unmatched),'prior_session_vendor_and_existing_reviewed_PDF_relationship':sum(bool(q['vendor_distributions_on_previous_session']) and bool(q['cached_later_factor_relationships']) for q in unmatched),'existing_primary_cash_supplement':sum(bool(q['cached_primary_supplements']) for q in unmatched),'existing_primary_listing_anchor':sum(bool(q['cached_lifecycle_boundary']) for q in unmatched),'no_vendor_or_cached_supplement_or_lifecycle':[(q['instrument'],q['day']) for q in unmatched if not q['vendor_distributions_on_previous_session'] and not q['cached_primary_supplements'] and not q['cached_lifecycle_boundary']]},
 'shortest_bounded_next_steps':[{'step':1,'action':'Use source-only primary notice capture/content review to resolve SH6019662024Jun14 two conflicting gross rows before any event compilation; retain both original rows unchanged.','event_keys':[g['event_key'] for g in duplicate_groups]}, {'step':2,'action':'Obtain original source/issuer entitlement and record/ex/pay evidence for SH6019662025Oct23 and SZ0007282025Jan21. Differences0.11/0.06 are reference discrepancies only, never primary cash amounts.','event_keys':['SH601966|2025-10-23','SZ000728|2025-01-21']}, {'step':3,'action':'Reuse authenticated old9 event/proof types plus lifecycle boundaries; retain cash precision and supplementary cash as separate contracts, without carrying over ownership proof.','old_inventory_sha256':OLD_SHA}, {'step':4,'action':'For five noncash events lacking an in-scope original notice, capture/review bounded original implementation notices. Wolong already has reviewed component notice and explicit insufficient-tax limits; keep its tax unknown unless a separately reviewed event-funding source closes that gap.','five_without_in_scope_notice':[q['event_key'] for q in noncash if q['requires_missing_event_specific_tax_or_stock_basis'] and not q['matching_original_announcement_PDFs']],'existing_Wolong_tax_guard':'SH600580|2025-06-27'}, {'step':5,'action':'After independent source projection and unchanged event guards pass, separately freeze original-share replay with zero-ownership/fractional/tax/lifecycle checks; no source inventory claims account admission. Factor-label adjacency does not create another income event.'}],
 'old_nine_event_proof_types':old['unique_reusable_event_proof_types'],'old_vendor_row_changes_in_terminal_source':old_row_changes,'old_vendor_rows_retained_literal':not old_row_changes,'known_primary_evidence_limits':old['wolong_known_primary_evidence_limit'],'lifecycle_boundaries':lifecycles,
 'next_projection_questions':['Authenticate existing event-specific proof/PDF/source binding before literal reuse; no double supplement for an already present vendor event.','Resolve the six identified noncash tax/basis gaps using actual original notices or retain explicit unknown ownership guards; a PDF/component review alone does not authorize capital exemption.','SZ002508 Jan10 cash supplement0.50 is entitlement; diluted price reference0.497403 must not become cash. SZ001914 V1 cash0.2400974 is separate from reference0.2397745.','SH603826 stock0.4 and taxable-income0.4 remain stock-tax evidence, not capital transfer; SZ002984/SZ003031 conditional tax evidence must not be upgraded.','Two lifecycle boundaries establish missing source dates only; current target intent does not prove actual flat inventory. Listing initial-adjustment/preclose anchors need their own validated source interpretation; never invent cash.','Same/prior-session factor-date relationships and distributions_without_adjustment are source questions, not authorization to create/delete/re-date corporate income.','The post-anchor continuous-traded preclose comparison is reference-only; no amount or tax is derived from a price gap.'],
 'source_only_boundaries':{'source_queries':0,'network_used':False,'account_replay_run':False,'portfolio_returns_computed':False,'corporate_events_compiled':False,'proof_projection_run':False,'source_admitted_for_account_replay':False,'actual_flat_inventory_proven':False,'2026_market_or_financial_values_read':False,'repository_or_sources_modified':False,'primary_content_re_reviewed_in_this_inventory':False},
 'preserved_initial_execution_differences':[{'log':'/tmp/low-market-residual-vol1m-pre2026-terminal-corporate-questions-first-20261021.log','cause':'Inventory initially expectedFalse for abnormal_exit; authenticated terminal schema usesnull. Corrected only the inventory schema expectation.'},{'log':'/tmp/low-market-residual-vol1m-pre2026-terminal-corporate-questions-second-20261021.log','cause':'Inventory initially aborted on real same-date duplicate. Changed to retain full duplicate groups as explicit Important source blockers; no row or economics was dropped/merged.'}],
 'critical_or_important_findings':[{'severity':'Important','issue':'Conflicting same-issuer/ex-date vendor cash rows require primary/source semantic resolution before event compilation','event_key':g['event_key']} for g in duplicate_groups],'authenticated_file_sha256':bound}
for name,h in bound.items():need(sha(Path(name))==h,'source changed during terminal question inventory')
parser=argparse.ArgumentParser();parser.add_argument('--output',default='/tmp/low-market-residual-vol1m-pre2026-terminal-corporate-questions-20261021.json');arguments=parser.parse_args();out=Path(arguments.output);need(not out.exists(),'do not overwrite existing terminal questions');out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
print(json.dumps({'report':str(out),'sha256':sha(out),'counts':report['counts'],'missing_noncash_proofs':missingproof,'uncovered_contiguous_preclose_dates':[(x['instrument'],x['day']) for x in preclose if not x['same_date_vendor_event']],'blank_noncash_keys':[x['event_key'] for x in blank_bad]},ensure_ascii=False))
