"""Independent stdlib reconstruction of255 source events and one listing anchor.
No project imports, source queries, planned source writes, account calls or ROI.
"""
import argparse,copy,hashlib,json
from collections import Counter
from datetime import date
from decimal import Decimal as D
from pathlib import Path
if not __debug__:raise RuntimeError('Audit assertions must remain enabled')
RAW='szse-value-momentum-raw-dev-20261021';PRIMARY='szse-value-momentum-primary-capture-20261021';TARGET='szse-value-momentum-formations-pre2026-20261021/targets.json'
OLD='budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json';OLDRAW='budgeted-residual-raw-dev-20261021'
KEYS=('SZ002155|2025-06-13','SZ002837|2024-05-27','SZ002837|2025-05-30','SZ002984|2024-04-19')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def day(v):assert date.fromisoformat(v).isoformat()==v;return v
def finite(v):d=D(v);assert d.is_finite() and d>=0;return d

def independently_compile(packets,proof,sessions):
 docs={d['file']:d for d in proof['documents']};rows=[]
 for code in sorted(packets):rows.extend((code,row,'VENDOR_DISTRIBUTION',None) for row in packets[code]['distributions'])
 rows.extend((v['instrument'],v['record'],'PRIMARY_NOTICE_SUPPLEMENT',v) for v in proof['supplementary_distributions'])
 seen=set();events=[];receipts=[];consumed=set()
 def bind(p,code,row):
  doc=docs[p['source_file']];assert doc['sha256']==p['source_sha256'] and doc['instrument']==code and doc['day']==row['dividPlanDate'];return doc['sha256']
 assert proof['cash_overrides']=={} and proof['stock_dividend_tax_bases']=={}
 for code,row,kind,supplement in rows:
  assert row['code']==code[:2].lower()+'.'+code[2:]
  key=code+'|'+day(row['dividOperateDate']);assert key not in seen;seen.add(key)
  assert row['dividCashPsBeforeTax'] and row['dividStocksPs'];cash=finite(row['dividCashPsBeforeTax']);stock=finite(row['dividStocksPs']);assert stock==0
  primary=[bind(supplement,code,row)] if supplement else []
  capitaltext=row['dividReserveToStockPs']
  if not capitaltext:
   assert cash>0 and stock==0 and row['dividCashStock'].startswith('10派') and '送' not in row['dividCashStock'] and '转' not in row['dividCashStock'] and not row['dividStockMarketDate']
   capitaltext='0'
  capital=finite(capitaltext);capitalverified=False
  tax=proof['capital_tax'].get(key)
  if tax:
   assert key in KEYS and capital>0 and tax['verified_exempt'] is True
   assert tax['evidence_kind']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE'
   primary.append(bind(tax,code,row));capitalverified=True;consumed.add(key)
  announced,recorded,ex=(day(row[k]) for k in ('dividPlanDate','dividRegistDate','dividOperateDate'))
  paid=day(row['dividPayDate']) if row['dividPayDate'] else None;listed=day(row['dividStockMarketDate']) if row['dividStockMarketDate'] else None
  assert recorded in sessions and ex in sessions and announced<=recorded<ex and ex<=sessions[-1]
  if cash:assert paid and paid>=ex
  if capital:assert listed and listed>=ex
  identity={'instrument':code,'source_kind':kind,'source_distribution':row,'primary_source_sha256':sorted(set(primary)),
   'effective_stock_taxable_income_per_original_share':'0','capital_tax_exempt_verified':capitalverified,'stock_tax_basis_verified':False}
  eid=digest(identity)
  events.append({'event_id':eid,'instrument':code,'announced':announced,'recorded':recorded,'ex_date':ex,'pay_date':paid,'listed':listed,
   'cash_per_share':str(cash),'capital_per_share':str(capital),'capital_tax_exempt_verified':capitalverified,'stock_per_share':str(stock),
   'stock_taxable_income_per_share':'0','stock_tax_basis_verified':False})
  receipts.append({'event_id':eid,'instrument':code,'ex_date':ex,'source_kind':kind,'source_row_sha256':digest(row),'primary_source_sha256':sorted(set(primary)),
   'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),'requires_zero_record_ownership_if_tax_unverified':bool(capital>0 and not capitalverified)})
 assert consumed==set(KEYS) and len(events)==len({e['event_id'] for e in events})==255
 assert Counter(r['source_kind'] for r in receipts)=={'VENDOR_DISTRIBUTION':254,'PRIMARY_NOTICE_SUPPLEMENT':1}
 assert not any(r['requires_zero_record_ownership_if_tax_unverified'] for r in receipts)
 return events,receipts

def independently_anchor(packet,anchor,sessions):
 assert anchor['kind']=='PRIMARY_LISTING_UNIT_ADJUSTMENT_ANCHOR' and anchor['instrument']==packet['instrument']=='SZ001389'
 assert anchor['verified_primary_listing'] is True and anchor['listed_on']=='2024-04-02' and anchor['issue_price']=='17.43'
 assert anchor['source_packet_digest']==digest(packet) and anchor['source_file']=='SZ001389-2024-04-01.pdf'
 assert anchor['primary_listing_page']==13 and anchor['primary_issue_price_page']==29
 listed=anchor['listed_on'];post=[s for s in sessions if s>=listed];missing=[s for s in sessions if s<listed]
 assert [r['date'] for r in packet['bars']]==post and len(post)==426 and len(missing)==60
 assert D(packet['bars'][0]['preclose'])==D('17.43')
 matches=[r for r in packet['adjustments'] if r['dividOperateDate']==listed];assert len(matches)==1 and packet['adjustments'][0]==matches[0]
 row=matches[0];assert row['code']=='sz.001389' and D(row['backAdjustFactor'])==D(row['adjustFactor'])==1 and finite(row['foreAdjustFactor'])>0
 assert digest(row)==anchor['initial_adjustment_row_sha256'] and not any(r['dividOperateDate']<=listed for r in packet['distributions'])
 view=copy.deepcopy(packet);view['adjustments']=view['adjustments'][1:]
 receipt={'kind':'COVERAGE_VALIDATION_ONLY_PRIMARY_LISTING_UNIT_ANCHOR','instrument':'SZ001389','listed_on':listed,
  'primary_document_sha256':anchor['primary_document_sha256'],'source_packet_digest':digest(packet),'validation_projection_digest':digest(view),
  'initial_adjustment_row_sha256':digest(row),'separated_anchor_row':row,'prelisting_missing_sessions':missing,'postlisting_observed_sessions':len(post),
  'account_uses_original_bars':True,'entitlement_inferred':False,'zero_distribution_certified':False,'synthetic_prices_created':0}
 return view,receipt

def independent_coverage(packets):
 adjacent=[]
 for code,p in packets.items():
  assert not p['quarantine'];exdates={r['dividOperateDate'] for r in p['distributions']};bars=p['bars'];indices={r['date']:i for i,r in enumerate(bars)};previous=None
  for row in bars:
   ref=finite(row['preclose']) if row['preclose'] else None
   assert previous is None or ref is None or ref<=0 or abs(ref-previous)<=D('.005') or row['date'] in exdates,(code,row['date'],'unexplained reference')
   if row['close'] and finite(row['close'])>0:previous=D(row['close'])
  for r in p['adjustments']:
   at=r['dividOperateDate'];assert at in indices;i=indices[at]
   assert at in exdates or i>0 and bars[i-1]['date'] in exdates,(code,at,'unexplained adjustment')
   if at not in exdates:adjacent.append({'instrument':code,'adjustment_day':at,'preceding_source_distribution_day':bars[i-1]['date'],'adjustment_row_sha256':digest(r)})
 assert len(adjacent)==4
 return adjacent

def expected_projection(base,repo,planfile,expected_sha):
 assert sha(planfile)==expected_sha;p=read(planfile)
 assert p['status']=='FROZEN_VALUE_MOMENTUM_PRE2026_PHYSICAL_DAILY_DEVELOPMENT' and p['candidate']=='szse_value_momentum_equal' and p['window']==['2023-12-29','2025-12-31']
 assert p['initial_CNY']=='1000000' and p['extra_cost_bps']==[20,40] and p['reference_extra_bps']==40 and p['candidate_budget']==1 and p['investment_controls_promoted'] is False
 assert p['capital_tax_inferences_unchanged']==4 and p['primary_cash_supplements']==1 and p['primary_listing_unit_anchor_validation_exceptions']==1
 assert p['new_source_queries']==0 and p['new_2026_market_queries'] is False and p['raw_account_outcomes_observed'] is False
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for f,h in p[field].items():assert not Path(f).is_absolute() and '..' not in Path(f).parts and sha(parent/f)==h,(field,f)
 rawm=read(base/RAW/'manifest.json');primary=read(base/PRIMARY/'manifest.json');content=read(repo/'experiments/qlib/szse-value-momentum-primary-content-review.json')
 assert rawm['names']==103 and not rawm['errors_sha256'] and not rawm['pending_codes'] and not primary['errors'] and not primary['pending_files'] and len(primary['documents'])==6
 assert content['all_six_originals_byte_authenticated'] is True and content['capture_manifest_sha256']==sha(base/PRIMARY/'manifest.json')
 assert content['capture_audit_sha256']==sha(repo/'experiments/qlib/szse-value-momentum-primary-source-independent-audit.json')
 rawaudit=read(repo/'experiments/qlib/szse-value-momentum-raw-source-independent-audit.json');assert rawaudit['capture_complete'] is True and rawaudit['capture_manifest_sha256']==sha(base/RAW/'manifest.json')
 sessions=read(base/RAW/'calendar.json')['sessions'];assert sessions==sorted(set(sessions)) and len(sessions)==486 and [sessions[0],sessions[-1]]==p['window']
 assert sha(base/RAW/'calendar.json')==rawm['calendar_sha256']
 packets={};hashes={}
 for code,h in rawm['per_code_sha256'].items():
  f=base/RAW/'codes'/(code+'.json');assert Path(code).name==code and sha(f)==h;hashes[str(f)]=h;v=read(f)
  assert v['instrument']==code and v['window']==p['window'] and not v['quarantine']
  if code!='SZ001389':assert [r['date'] for r in v['bars']]==sessions
  packets[code]=v
 targets=read(base/TARGET)['szse_value_momentum_equal'];assert len(targets)==24 and {c for t in targets.values() for c in t['weights']}==set(packets) and sha(base/TARGET)==rawm['target_sha256']
 docs=[]
 for d in primary['documents'].values():
  f=base/PRIMARY/d['file'];assert Path(d['file']).name==d['file'] and d['day']<='2025-12-31' and sha(f)==d['sha256'];hashes[str(f)]=d['sha256'];docs.append(copy.deepcopy(d))
 assert {d['file']:d['sha256'] for d in docs}=={d['file']:d['sha256'] for d in content['documents']}
 old=read(base/OLD);om=read(base/OLDRAW/'manifest.json');assert old['raw_manifest_sha256']==sha(base/OLDRAW/'manifest.json')
 oldcomponents={c['case_id']:c for c in old['distribution_component_reviews']};inferences={r['event']:r for r in content['four_original_noncash_inferences_preserved']};assert set(inferences)==set(KEYS)
 capital={}
 for key in KEYS:
  code,ex=key.split('|');f=base/OLDRAW/'codes'/(code+'.json');assert sha(f)==om['per_code_sha256'][code]==oldcomponents[key]['original_source_packet_sha256'];hashes[str(f)]=sha(f)
  assert [r for r in read(f)['distributions'] if r['dividOperateDate']==ex]==[r for r in packets[code]['distributions'] if r['dividOperateDate']==ex]
  tax=old['capital_tax'][key];review=inferences[key]
  assert tax['evidence_kind']==review['classification_retained']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE' and review['new_strict_statutory_tax_certification'] is False
  assert tax['source_file']==review['file'] and tax['source_sha256']==review['sha256'];capital[key]=copy.deepcopy(tax)
 cash=content['SZ002508_special_cash'];listing=content['SZ001389_listing']
 assert cash['cash_per_original_share_CNY']=='0.50' and cash['price_reference_cash_per_share_CNY']=='0.497403' and cash['announcement_and_signature_day']=='2024-01-03'
 assert [cash[k] for k in ('record_date','ex_date','cash_payment_date')]==['2024-01-09','2024-01-10','2024-01-10']
 assert listing['listing_date_verified_from_original_primary_text'] is True and listing['primary_stated_listing_date']=='2024-04-02' and listing['issue_price_CNY_per_share']=='17.43'
 byfile={d['file']:d for d in docs};d=byfile['SZ002508-2024-01-03.pdf']
 row={'code':'sz.002508','dividPreNoticeDate':'','dividAgmPumDate':'','dividPlanAnnounceDate':'','dividPlanDate':'2024-01-03','dividRegistDate':'2024-01-09','dividOperateDate':'2024-01-10','dividPayDate':'2024-01-10','dividStockMarketDate':'','dividCashPsBeforeTax':'0.50','dividCashPsAfterTax':'','dividStocksPs':'0','dividCashStock':'PRIMARY_NOTICE_CASH_ONLY_10派5元（含税）','dividReserveToStockPs':'0'}
 supplement={'instrument':'SZ002508','source_file':d['file'],'source_sha256':d['sha256'],'record':row,'source_role':'PRIMARY_NOTICE_SUPPLEMENT_NOT_VENDOR_REWRITE','primary_pages_one_based':[1,2,3,4],'price_reference_per_share_not_entitlement':'0.497403'}
 assert not any(r['dividOperateDate']=='2024-01-10' for r in packets['SZ002508']['distributions'])
 d=byfile['SZ001389-2024-04-01.pdf'];packet=packets['SZ001389']
 anchor={'kind':'PRIMARY_LISTING_UNIT_ADJUSTMENT_ANCHOR','instrument':'SZ001389','listed_on':'2024-04-02','issue_price':'17.43','verified_primary_listing':True,'source_file':d['file'],'primary_document_sha256':d['sha256'],'primary_listing_page':13,'primary_issue_price_page':29,'source_packet_digest':digest(packet),'initial_adjustment_row_sha256':digest(packet['adjustments'][0])}
 lifecycle={'SZ001389':{'kind':'LISTING_BEGIN','effective_date':'2024-04-02','verified_primary_boundary':True,'primary_document_sha256':d['sha256'],'source_file':d['file'],'primary_page_one_based':13}}
 proof={'status':'EVALUATOR_ONLY_COMPOSITE_SOURCE_PROJECTION','documents':docs,'capital_tax':capital,'cash_overrides':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[supplement],'lifecycles':lifecycle,'listing_anchor':anchor,'tax_inferences_unchanged':content['four_original_noncash_inferences_preserved'],'historical_arrival_verified':False,'strict_statutory_capital_tax_certification':False,'source_packets_modified':False}
 view,anchor_receipt=independently_anchor(packet,anchor,sessions);validation=copy.deepcopy(packets);validation['SZ001389']=view;validation['SZ002508']['distributions'].append(copy.deepcopy(row));adjacent=independent_coverage(validation)
 events,receipts=independently_compile(packets,proof,sessions)
 expected={'reviewed-manifest.json':proof,'derived_events.json':events,'event_source_receipts.json':receipts,'listing_anchor_receipt.json':anchor_receipt,'lifecycles.json':lifecycle}
 return p,packets,hashes,sessions,expected,adjacent

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','repo-root','plan','expected-plan-sha256','projection-dir','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv);base=Path(a.source_root);repo=Path(a.repo_root);planfile=Path(a.plan);out=Path(a.output);root=Path(a.projection_dir)
 assert not out.exists();plan,packets,hashes,sessions,expected,adjacent=expected_projection(base,repo,planfile,a.expected_plan_sha256)
 if a.preflight_only:print('Independent source-only reconstruction:255events,4unchangedinferences,1primarycash,1unitanchor/60missingprefix; no output/account/ROI');return 0
 assert root.resolve()==(base/plan['source_projection_directory']).resolve();summary=read(root/'summary.json')
 assert summary['status']=='FIXED_COMPOSITE_EVALUATOR_PROJECTION_COMPILED_NO_RETURNS' and summary['plan_sha256']==sha(planfile)
 assert set(summary['artifact_sha256'])==set(expected)
 actual={}
 for name,value in expected.items():
  assert sha(root/name)==summary['artifact_sha256'][name];actual[name]=read(root/name);assert actual[name]==value,(name,'independent source projection reconstruction')
 assert summary['original_packet_digests']=={c:digest(p) for c,p in packets.items()}
 for flag in ('original_packets_modified','account_replay_performed','portfolio_returns_computed','new_2026_market_queries','full_PIT_or_minute_admission','objective_achieved'):assert summary[flag] is False
 for key,count in (('events',255),('vendor_events',254),('primary_supplements',1),('inherited_capital_tax_inferences',4),('listing_anchors',1),('prelisting_absent_sessions',60),('new_source_queries',0)):assert summary[key]==count
 assert summary['blank_capital_cash_only_receipts']==sum(r['blank_capital_resolved_as_zero'] for r in expected['event_source_receipts.json'])==250
 assert summary['raw_manifest_sha256']==sha(base/RAW/'manifest.json') and summary['primary_capture_manifest_sha256']==sha(base/PRIMARY/'manifest.json') and summary['target_sha256']==sha(base/TARGET)
 negatives={}
 for mode in ('cash_rewrite','wrong_record_date','lost_event','receipt_rewrite','inference_upgrade','anchor_entitlement','zero_distribution_claim','lifecycle_rewrite'):
  changed=copy.deepcopy(actual)
  if mode=='cash_rewrite':changed['derived_events.json'][-1]['cash_per_share']='0.497403'
  elif mode=='wrong_record_date':changed['derived_events.json'][-1]['recorded']='2024-01-10'
  elif mode=='lost_event':changed['derived_events.json'].pop();changed['event_source_receipts.json'].pop()
  elif mode=='receipt_rewrite':changed['event_source_receipts.json'][-1]['source_kind']='PRICE_GAP_INFERENCE'
  elif mode=='inference_upgrade':changed['reviewed-manifest.json']['strict_statutory_capital_tax_certification']=True
  elif mode=='anchor_entitlement':changed['listing_anchor_receipt.json']['entitlement_inferred']=True
  elif mode=='zero_distribution_claim':changed['listing_anchor_receipt.json']['zero_distribution_certified']=True
  else:changed['lifecycles.json']['SZ001389']['effective_date']='2024-04-01'
  try:assert changed==expected
  except AssertionError:negatives[mode]=True
  else:raise AssertionError('semantic output mutation accepted:'+mode)
 anchor=expected['reviewed-manifest.json']['listing_anchor']
 for mode in ('nonunit_anchor','missing_postlisting','present_prelisting','duplicate_anchor','wrong_initial_reference','unbound_anchor_digest'):
  packet=copy.deepcopy(packets['SZ001389']);proof=copy.deepcopy(anchor)
  if mode=='nonunit_anchor':packet['adjustments'][0]['backAdjustFactor']='1.01'
  elif mode=='missing_postlisting':packet['bars'].pop()
  elif mode=='present_prelisting':row=copy.deepcopy(packet['bars'][0]);row['date']='2024-04-01';packet['bars'].insert(0,row)
  elif mode=='duplicate_anchor':packet['adjustments'].insert(0,copy.deepcopy(packet['adjustments'][0]))
  elif mode=='wrong_initial_reference':packet['bars'][0]['preclose']='17.42'
  else:proof['source_packet_digest']='0'*64
  if mode!='unbound_anchor_digest':proof['source_packet_digest']=digest(packet);proof['initial_adjustment_row_sha256']=digest(packet['adjustments'][0])
  try:independently_anchor(packet,proof,sessions)
  except AssertionError:negatives[mode]=True
  else:raise AssertionError('semantic anchor mutation accepted:'+mode)
 for f,h in hashes.items():assert sha(f)==h
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for f,h in plan[field].items():assert sha(parent/f)==h
 assert sha(planfile)==a.expected_plan_sha256
 result={'status':'INDEPENDENT255_SOURCE_EVENTS_AND_PRIMARY_BOUND_UNIT_ANCHOR_RECONSTRUCTED_NO_ACCOUNT_ADMISSION','audit_code_sha256':sha(__file__),'plan_sha256':sha(planfile),'summary_sha256':sha(root/'summary.json'),
  'all_original103_packet_digests_and_sixPDF_hashes_unchanged':True,'all255_eventIDs_and_receipts_independently_reconstructed':True,'vendor_events':254,'primary_supplements':1,'events_reconstructed':255,'imports_project_code':False,'inherited_four_capital_inference_objects_literal_unchanged':True,
  'primary_supplement':expected['derived_events.json'][-1],'listing_anchor_receipt':expected['listing_anchor_receipt.json'],'listing_lifecycle':expected['lifecycles.json'],
  'all_raw_reference_and_adjustment_coverage_reconstructed':True,'four_adjacent_adjustment_explanations':adjacent,'blank_capital_cash_only_receipts':250,
  'semantic_negative_controls_rejected':negatives,'negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,'eventID_algorithm_uses_project_imports':False,
  'source_coverage_validation_copy_not_used_for_event_compilation':True,'primary_listing_unit_anchor_creates_no_entitlement':True,'zero_distribution_certified':False,'strict_statutory_capital_tax_certification':False,
  'account_replay_performed':False,'account_replay_admitted':False,'portfolio_returns_computed':False,'source_queries_performed':0,'new_2026_market_queries':False,'objective_achieved':False,
  'limitations':['Authenticates previously completed primary content/capture review; no repeated legal/content determination. Four ordinary-investor tax interpretations remain event-specific inferences, including SZ0028372024metadata/signature caveat.',
   'Verifies source projection only. Primary listing boundary and unit-anchor coverage exception do not synthesize missing bars or certify zero distributions; actual lifecycle ownership/pending-order/mark guards require the separately frozen account replay.',
   'No physical execution, actualFIFO tax settlement, queue/impact, historical arrival, account acceptance or portfolio performance is established.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independently reconstructed255eventIDs/receipts and primary-bound listing unit anchor; no account/ROI')
 return 0
if __name__=='__main__':raise SystemExit(main())
