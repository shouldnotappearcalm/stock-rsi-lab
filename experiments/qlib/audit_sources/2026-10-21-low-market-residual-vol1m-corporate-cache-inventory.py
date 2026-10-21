"""Bounded pre2026 source/proof cache inventory; no account or network calls."""
import hashlib,json,re
from collections import Counter,defaultdict
from decimal import Decimal as D
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
REQUEST=R/'experiments/qlib/low-market-residual-vol1m-pre2026-raw-source-request.json'
INVENTORY=R/'experiments/qlib/low-market-residual-vol1m-pre2026-raw-source-inventory.json'
SOURCE_ROOTS=['price-delay-raw-dev-20261021','low-beta60-raw-dev-20261021','szse-value-momentum-raw-dev-20261021','budgeted-residual-raw-dev-20261021','return-families-raw-dev-20261017','szse-value-raw-dev-20261017','illiquidity-raw-source-continuation-20261020']
PUBLIC_MANIFESTS={'price-delay-corporate-reviewed-20261021':'price-delay-corporate-reviewed-manifest.json','low-beta60-corporate-reviewed-20261021':'low-beta60-corporate-reviewed-manifest.json','szse-value-momentum-account-sources-20261021':'szse-value-momentum-source-projection-reviewed-manifest.json','budgeted-residual-corporate-reviewed-20261021':'budgeted-residual-corporate-reviewed-manifest.json','illiquidity-corporate-reviewed-20261020':'illiquidity-corporate-reviewed-manifest.json'}
PROOF_ROOTS=['price-delay-corporate-reviewed-20261021','low-beta60-corporate-reviewed-20261021','szse-value-momentum-account-sources-20261021','budgeted-residual-corporate-reviewed-20261021','illiquidity-corporate-reviewed-20261020']
START,END='2023-12-29','2025-12-31'
def need(v,s):
 if not v:raise ValueError(s)
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
bound={}
def auth(p,h=None):
 p=Path(p);actual=sha(p);need(h is None or actual==h,'frozen original bytes changed '+str(p));bound[str(p)]=actual;return actual
request=read(REQUEST);inventory=read(INVENTORY);auth(REQUEST);auth(INVENTORY,request['inventory_sha256'])
need(request['window']==[START,END] and inventory['source_priority']==SOURCE_ROOTS,'fixed seven pre2026 sources only')
target=Path(inventory['target_file']);auth(target,request['target_sha256']);targets=read(target)['low_market_residual_vol_1m'];codes={c for row in targets.values() for c in row['weights']}
need(len(targets)==24 and len(codes)==361 and sorted(codes)==request['codes'],'fixed24/361 targets required')
source_records=[];alloptions={};chosen={};rawrows=[];cache_rows=defaultdict(list)
for source in inventory['source_directories_checked']:
 root=B/source['directory'];mh=auth(root/'manifest.json',source['manifest_sha256']);ch=auth(root/'calendar.json',source['calendar_sha256']);m=read(root/'manifest.json');sessions=read(root/'calendar.json')['sessions']
 need(m['window']==[START,END] and len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'pre2026 accepted source scope')
 anchor=source['audit_anchor'];auth(R/anchor['file'],anchor['sha256'])
 if 'authenticated_source_manifest_via_request' in anchor:auth(R/anchor['authenticated_source_manifest_via_request'],anchor['request_sha256'])
 source_records.append({'directory':str(root),'manifest_sha256':mh,'calendar_sha256':ch,'source_audit_anchor':anchor,'target_intersection_packets_checked':len(codes & set(m['per_code_sha256']))})
 for code in sorted(codes & set(m['per_code_sha256'])):
  path=root/'codes'/(code+'.json');auth(path,m['per_code_sha256'][code]);p=read(path);need(p['instrument']==code and p['window']==[START,END],'source identity/window')
  # Interpret accepted pre2026 component rows only, never quarantined future rows.
  need(all(START<=row['date']<=END for row in p['bars']) and all(START<=row['dividOperateDate']<=END for row in p['distributions']+p['adjustments']),'accepted source row beyond pre2026')
  option={'path':str(path),'sha256':sha(path),'directory':source['directory'],'manifest_sha256':mh,'complete_calendar':[r['date'] for r in p['bars']]==sessions,'observed_rows':len(p['bars'])}
  alloptions[(code,source['directory'])]=(p,option,sessions)
  for row in p['distributions']:cache_rows[(code,row['dividOperateDate'])].append({'row':row,'source':option})
for code in sorted(codes):
 route=request['reuse_routes'].get(code)
 if route:
  p,option,sessions=alloptions[(code,route['directory'])];need(option['sha256']==route['packet_sha256'] and option['complete_calendar'],'selected complete reuse route changed');chosen[code]=(p,option,sessions)
 else:
  options=[(SOURCE_ROOTS.index(folder),value) for (c,folder),value in alloptions.items() if c==code]
  if options:chosen[code]=min(options,key=lambda pair:pair[0])[1]
need(len(request['reuse_routes'])==301 and len(request['fresh_codes'])==60,'frozen301reuse/60fresh partition')
# Five bounded reviewed-proof roots; SZSE logical root is the compiled source proposal,
# with PDF bytes in its original pre2026 primary-capture root, not any full/horizon tree.
proof_records=[];proofs=[];documents=[];component_reviews=[];adjustment_links=[];lifecycle=[];gaps=[]
for name in PROOF_ROOTS:
 root=B/name;manifest=root/'reviewed-manifest.json';m=read(manifest);auth(manifest)
 public=R/'experiments/qlib'/PUBLIC_MANIFESTS[name];auth(public);need(manifest.read_bytes()==public.read_bytes(),'local/public reviewed literal manifest changed')
 pdfroot=B/'szse-value-momentum-primary-capture-20261021' if name.startswith('szse-value-momentum-account') else root
 docs={d['file']:d for d in m['documents']};need(len(docs)==len(m['documents']),'duplicate source PDF names')
 for doc in docs.values():
  need(doc['day']<=END,'post2025 proof document excluded');path=pdfroot/doc['file'];auth(path,doc['sha256'])
  if doc['instrument'] in codes:documents.append({'reviewed_manifest':str(manifest),'reviewed_manifest_sha256':sha(manifest),'pdf_path':str(path),'pdf_sha256':doc['sha256'],'instrument':doc['instrument'],'announcement_day':doc['day'],'original_metadata':doc,'fresh_content_review_performed':False})
 proof_records.append({'path':str(manifest),'sha256':sha(manifest),'status':m['status'],'public_byte_exact_counterpart':{'path':str(public),'sha256':sha(public)},'PDFs_authenticated':len(docs),'in_scope_document_count':sum(d['instrument'] in codes for d in docs.values()),'raw_manifest_sha256':m.get('raw_manifest_sha256'),'strict_statutory_capital_tax_certification':m.get('strict_statutory_capital_tax_certification',False),'account_admission_transferred':False})
 for field in ('capital_tax','stock_dividend_tax_bases','cash_overrides'):
  for key,proof in m.get(field,{}).items():
   code,ex=key.split('|')
   if code not in codes or not START<=ex<=END:continue
   doc=docs[proof['source_file']];need(doc['sha256']==proof['source_sha256'] and doc['instrument']==code,'proof/PDF identity mismatch')
   alternatives=cache_rows.get((code,ex),[]);matches=[x for x in alternatives if x['row']['dividPlanDate']==doc['day']]
   if field=='cash_overrides':matches=[x for x in matches if digest(x['row'])==proof['source_row_sha256'] and D(x['row']['dividCashPsBeforeTax'])==D(proof['expected_vendor_cash_per_share'])]
   if field=='stock_dividend_tax_bases':matches=[x for x in matches if D(x['row']['dividStocksPs'])==D(proof['expected_stock_per_original_share'])]
   if field=='capital_tax':matches=[x for x in matches if x['row']['dividReserveToStockPs'] and D(x['row']['dividReserveToStockPs'])>0]
   proofs.append({'event_key':key,'proof_type':field,'reviewed_manifest':str(manifest),'reviewed_manifest_sha256':sha(manifest),'proof_literal':proof,'pdf_path':str(pdfroot/proof['source_file']),'pdf_sha256':proof['source_sha256'],'source_rows_matching_announcement_and_component':matches,'proof_to_vendor_match_found':bool(matches),'matching_scope':'original PDF bytes, issuer/announcement and component applicability; full economic ratios/date review stays the existing reviewed literal, not re-reviewed here','primary_reuse_candidate_only':True,'old_zero_ownership_or_current_admission_transferred':False})
 for supplement in m.get('supplementary_distributions',[]):
  code=supplement['instrument'];ex=supplement['record']['dividOperateDate']
  if code not in codes or not START<=ex<=END:continue
  doc=docs[supplement['source_file']];need(doc['sha256']==supplement['source_sha256'] and doc['instrument']==code and doc['day']==supplement['record']['dividPlanDate'],'primary cash supplement identity mismatch')
  proofs.append({'event_key':code+'|'+ex,'proof_type':'primary_cash_supplement','reviewed_manifest':str(manifest),'reviewed_manifest_sha256':sha(manifest),'proof_literal':supplement,'pdf_path':str(pdfroot/supplement['source_file']),'pdf_sha256':supplement['source_sha256'],'vendor_row_already_present':bool(cache_rows.get((code,ex))),'needs_duplicate_check_against_terminal_fresh_packet':True,'primary_reuse_candidate_only':True,'old_zero_ownership_or_current_admission_transferred':False})
 for review in m.get('distribution_component_reviews',[]):
  key=review['case_id'];code=key.split('|')[0]
  if code in codes:component_reviews.append({'event_key':key,'reviewed_manifest':str(manifest),'reviewed_manifest_sha256':sha(manifest),'review_literal':review,'not_reclassified_as_tax_exempt_if_no_tax_proof':True})
 for link in m.get('adjustment_relationships',[]):
  if link['instrument'] in codes:adjustment_links.append({'reviewed_manifest':str(manifest),'reviewed_manifest_sha256':sha(manifest),'link_literal':link,'new_income_inferred':False})
 for code,proof in m.get('lifecycles',{}).items():
  if code in codes:lifecycle.append({'instrument':code,'reviewed_manifest':str(manifest),'reviewed_manifest_sha256':sha(manifest),'proof_literal':proof,'pdf_path':str(pdfroot/proof['source_file']),'current_candidate_target_days':[d for d,t in targets.items() if code in t['weights']],'actual_flat_inventory_verified':False})
# Selected complete caches and the two known partial source options only;
# fresh output is deliberately untouched until source process terminal notification.
noncash=[];blank=[];coverage=[];vendor_summary=[]
for code,(packet,option,sessions) in sorted(chosen.items()):
 exs={r['dividOperateDate'] for r in packet['distributions']};missing=sorted(set(sessions)-{r['date'] for r in packet['bars']})
 vendor_summary.append({'instrument':code,'source':option,'vendor_distributions':len(packet['distributions']),'adjustments':len(packet['adjustments']),'missing_sessions':missing})
 for row in packet['distributions']:
  key=code+'|'+row['dividOperateDate'];record={'event_key':key,'row_sha256':digest(row),'vendor_row':row,'source':option};rawrows.append(record)
  stock=D(row['dividStocksPs']) if row['dividStocksPs'] else None;cap=D(row['dividReserveToStockPs']) if row['dividReserveToStockPs'] else None
  if stock is None or stock>0 or cap is not None and cap>0:
   related=[p for p in proofs if p['event_key']==key and p['proof_type'] in ('capital_tax','stock_dividend_tax_bases')]
   noncash.append({**record,'matching_cached_primary_proof_indices':[proofs.index(p) for p in related],'separate_content_review_indices':[i for i,x in enumerate(component_reviews) if x['event_key']==key],'proven_for_this_candidate_account':False,'missing_cached_component_or_tax_proof':not bool(related)})
  if cap is None:
   display=row.get('dividCashStock','');syntactic=(row['dividCashPsBeforeTax'] and D(row['dividCashPsBeforeTax'])>0 and stock==0 and display.startswith('10派') and '送' not in display and '转' not in display and not row['dividStockMarketDate'])
   blank.append({**record,'cash_only_blank_capital_syntax_matches_prior_contract':bool(syntactic),'actual_tax_exemption_or_primary_completeness_inferred':False})
 for adjust in packet['adjustments']:
  d=adjust['dividOperateDate']
  if d not in exs:
   links=[x for x in adjustment_links if x['link_literal']['instrument']==code and x['link_literal']['adjustment_source_day']==d]
   life=[x for x in lifecycle if x['instrument']==code and x['proof_literal']['effective_date']==d]
   coverage.append({'instrument':code,'day':d,'issue':'ADJUSTMENT_WITHOUT_SAME_DATE_VENDOR_DISTRIBUTION','raw_adjustment':adjust,'source':option,'cached_later_factor_relationship_indices':[adjustment_links.index(x) for x in links],'cached_lifecycle_indices':[lifecycle.index(x) for x in life],'additional_income_inferred':False,'factor_date_semantics_verified':False})
 previous=None
 for row in packet['bars']:
  close=D(row['close']) if row.get('close') else None;preclose=D(row['preclose']) if row.get('preclose') else None
  if previous is not None and preclose is not None and preclose>0 and abs(preclose-previous)>D('.005') and row['date'] not in exs:
   coverage.append({'instrument':code,'day':row['date'],'issue':'RAW_PRECLOSE_GAP_WITHOUT_SAME_DATE_VENDOR_DISTRIBUTION','previous_positive_close':str(previous),'source_preclose':str(preclose),'source':option,'matching_primary_cash_supplement_indices':[i for i,p in enumerate(proofs) if p['event_key']==code+'|'+row['date'] and p['proof_type']=='primary_cash_supplement'],'cash_not_inferred_from_difference':True})
  if close is not None and close>0:previous=close
life_public=R/'experiments/qlib/illiquidity-lifecycle-source-evidence.json';auth(life_public);le=read(life_public)
for item in lifecycle:
 code=item['instrument'];review=next(x for x in le['reviews'] if x['instrument']==code);p=chosen[code][0];source=chosen[code][1];needed=sorted(set(chosen[code][2])-{r['date'] for r in p['bars']})
 need(sha(Path(item['pdf_path']))==review['primary_document_sha256'] and item['proof_literal']['effective_date']==review['listing_or_delisting_boundary'] and source['sha256']==review['raw_packet_sha256'],'lifecycle original source boundary anchors changed')
 need(len(needed)==review['missing_sessions'] and all(d<review['listing_or_delisting_boundary'] if review['missing_relation']=='BEFORE' else d>review['listing_or_delisting_boundary'] for d in needed),'missing dates conflict with primary lifecycle boundary')
 item['authenticated_public_lifecycle_review']={'path':str(life_public),'sha256':sha(life_public),'literal':review};item['existing_partial_packet']=source;item['missing_sessions_match_primary_boundary']=True;item['missing_sessions']=needed
wolong_limits=R/'experiments/qlib/budgeted-residual-wolong-primary-review-limits.json';auth(wolong_limits);wolong=read(wolong_limits)
need(wolong['actual_2025_event_capital_source_verified'] is False and wolong['capital_tax_exemption_granted'] is False,'known Wolong evidence cannot be upgraded')
unique_proofs=sorted({(x['event_key'],x['proof_type']) for x in proofs});unique_pdfs={x['pdf_sha256'] for x in documents}
report={'status':'BOUNDED_PRE2026_CORPORATE_AND_LIFECYCLE_CACHE_INVENTORY_SOURCE_LEADS_ONLY','candidate':'low_market_residual_vol_1m','source_window':[START,END],'target_sha256':sha(target),'target_file':str(target),'target_months':24,'target_union_names':361,'request_sha256':sha(REQUEST),'source_inventory_sha256':sha(INVENTORY),'inventory_code_sha256':sha(Path(__file__)),
 'source_roots_authenticated':source_records,'reviewed_roots_authenticated':proof_records,'logical_missing_root_resolution':'szse-value-momentum-corporate-reviewed-20261021 is absent; use source-only szse-value-momentum-account-sources-20261021/reviewed-manifest.json with the six original PDF bytes in szse-value-momentum-primary-capture-20261021. No full/horizon proof was read.',
 'counts':{'source_cache_packet_options_authenticated':len(alloptions),'cached_codes_with_selected_existing_packet':len(chosen),'complete_selected_reuse':301,'known_partial_existing_packets':len(chosen)-301,'fresh_requested':60,'no_registered_existing_packet':len(codes-set(chosen)),'selected_existing_vendor_rows':len(rawrows),'noncash_or_unknown_stock_component_rows':len(noncash),'cash_only_blank_capital_rows':sum(x['cash_only_blank_capital_syntax_matches_prior_contract'] for x in blank),'unique_reusable_event_proof_types':len(unique_proofs),'in_scope_original_pdf_hashes':len(unique_pdfs),'in_scope_PDF_references':len(documents),'existing_lifecycle_boundaries':len(lifecycle)},
 'wolong_known_primary_evidence_limit':{'event_key':'SH600580|2025-06-27','public_review_path':str(wolong_limits),'public_review_sha256':sha(wolong_limits),'review_literal':wolong,'underlying_proposal_and_annual_PDFs_not_opened_in_this_bounded_inventory':True,'capital_tax_guard_must_remain_unresolved':True},
 'noncash_tax_and_basis_reuse_policy':'Preserve source literal evidence scope; SZ002984 and SZ003031 premium-source plus cash-tax arithmetic are conditional, not direct statutory certificates. SH603826 is taxable stock, not exempt capital. SH600580 has reviewed component economics but no event-specific tax exemption.',
 'unique_reusable_event_proof_types':[{'event_key':k,'type':t} for k,t in unique_proofs],'proof_candidates':proofs,'in_scope_PDFs':documents,'independently_previously_reviewed_components':component_reviews,'known_later_factor_relationships':adjustment_links,'noncash_and_unproven_component_vendor_rows':noncash,'blank_capital_source_rows':blank,'existing_packet_source_receipts':vendor_summary,'all_selected_existing_vendor_events':rawrows,'source_coverage_questions':coverage,'lifecycle_candidates':lifecycle,
 'pending_source_names_without_registered_packet':sorted(codes-set(chosen)),'fresh_capture_directory_read':False,'pending_output':'low-market-residual-vol1m-raw-pre2026-20261021 NOT READ; final fresh sources may add events/questions',
 'bounded_gaps':['Only the five explicitly allowed pre2026 proof roots (one logical SZSE path substitution) and seven registered source roots were inspected. No global proof-completeness or absence claim.','For fresh source names absent from old caches, no vendor economics can yet be authenticated. The terminal fresh capture must be audited before mapping any new proof.','Copied tax/source evidence remains event-specific and conditionally inferred where originally conditional; no strict statutory exemption/FIFO/registry or source completeness certification.','Lifecycle boundaries explain source missing prefix/suffix only. Current target intent is not actual inventory: do not transfer old strategies actual-flat/zero-registered-ownership findings.','Cash-only blank capital syntax is a limited source compiler convention, not independent primary verification or capital-tax admission.','Original content was not re-rendered/reviewed in this inventory; this authenticates existing reviewed literals/PDF bytes and local source rows.','No factor/preclose gap is converted to cash. Existing later-factor labels may support an earlier vendor event without proving factor-date semantics.'],
 'source_queries':0,'account_replay_run':False,'portfolio_returns_computed':False,'source_admission_for_account_replay':False,'current_candidate_actual_zero_ownership_verified':False,'2026_accepted_market_or_financial_records_interpreted':False,'source_or_strategy_modified':False,'critical_or_important_findings':[],
 'authenticated_file_sha256':bound}
for p,h in bound.items():need(sha(Path(p))==h,'source bytes changed during read-only inventory')
out=Path('/tmp/low-market-residual-vol1m-pre2026-corporate-cache-inventory-20261021.json');need(not out.exists(),'preserve original inventory');out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
print(json.dumps({'report':str(out),'sha256':sha(out),'counts':report['counts'],'unique_proof_types':report['unique_reusable_event_proof_types'],'noncash_missing_cached_proof':[x['event_key'] for x in noncash if x['missing_cached_component_or_tax_proof']]},ensure_ascii=False))
