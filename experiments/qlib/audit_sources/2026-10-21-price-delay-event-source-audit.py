"""Independent stdlib pre2026 event reconstruction; never imports project code."""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal as D
from pathlib import Path

PLAN_SHA = '059a8265a9c4a260d3bceed41cea8be4a218ab8ddbc73ae943e383757f567901'
REQUEST_SHA = '15d50d8a38fcbe88e2e2304c1680e74d01e132f714eb691f1657799c854568ec'
START, END = '2023-12-29', '2025-12-31'
UNKNOWN = 'SH603596|2024-05-20'
DIRECT = {'SH601128|2024-05-29','SH601128|2025-06-05','SH603737|2025-05-30'}
CONDITIONAL = 'SZ002155|2025-06-13'
# These are actual eligible-holder cash amounts, NOT diluted price references.
CASH = {
 'SH600167|2024-12-27': ('0.12','2024-12-20','2024-12-26','2024-12-27'),
 'SH600482|2024-11-22': ('0.03138','2024-11-15','2024-11-21','2024-11-22'),
 'SZ002508|2024-01-10': ('0.5','2024-01-03','2024-01-09','2024-01-10'),
}


def require(ok, message):
 if not ok: raise ValueError(message)


def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
   separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def day(text):
 require(isinstance(text,str) and date.fromisoformat(text).isoformat()==text,'noncanonical date')
 require(text<=END,'post2025 source economic date')
 return text


def decimal(text):
 require(isinstance(text,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',text) is not None,'plain nonnegative source decimal')
 value=D(text)
 require(value.is_finite() and value>=0,'nonfinite or negative amount')
 return value


def proof_semantics(proposal, docs, noncash, adjustment, packets, inherited):
 require(proposal['cash_overrides']=={} and proposal['stock_dividend_tax_bases']=={},'unsupported cash precision or stock-tax proof')
 require(set(proposal['capital_tax'])==DIRECT|{CONDITIONAL},'capital proof scope changed')
 require(proposal['unknown_capital_tax']==[UNKNOWN],'unknown capital guard changed')
 require(proposal['strict_statutory_capital_tax_certification'] is False,'statutory certification upgraded')
 require(proposal['direct_primary_capital_tax_statements']==3 and proposal['conditional_capital_tax_inferences']==1,'tax evidence classification changed')
 for c in noncash['cases']:
  key=c['case_id']; code=c['instrument']; doc=docs[c['file']]
  require(doc['sha256']==c['sha256'],'noncash review PDF mismatch')
  require(c['raw_packet_sha256']==sha(Path(c['raw_packet_path'])),'noncash original packet mismatch')
  rows=[r for r in packets[code]['distributions'] if r['dividOperateDate']==c['ex_date']]
  require(len(rows)==1,'noncash original row absent or ambiguous'); row=rows[0]
  require(D(row['dividCashPsBeforeTax'])==D(c['cash_per_original_entitled_share_CNY']) and
    D(row['dividReserveToStockPs'])==D(c['capital_per_original_entitled_share']) and
    D(row['dividStocksPs'])==D(c['stock_dividend_per_original_entitled_share']),'primary noncash economics mismatch')
  require((row['dividRegistDate'],row['dividPayDate'],row['dividStockMarketDate'])==
    (c['record_date'],c['cash_payment_date'],c['new_unrestricted_shares_listing_date']),'primary noncash dates mismatch')
  if key in DIRECT:
   require(c['issuer_explicit_capital_transfer_no_tax_statement'] is True and
     c['tax_evidence_level']=='DIRECT_ISSUER_EVENT_NO_TAX_STATEMENT','direct evidence strengthened or lost')
  elif key==CONDITIONAL:
   require(c['issuer_explicit_capital_transfer_no_tax_statement'] is False and
     c['tax_evidence_level']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','conditional tax evidence upgraded')
  else:
   require(key==UNKNOWN and c['existing_capital_tax_record_for_comparison_only'] is None and
     c['tax_evidence_level']=='INSUFFICIENT_FOR_CAPITAL_TRANSFER_EXEMPTION','unknown capital evidence upgraded')
  if key in proposal['capital_tax']:
   proof=proposal['capital_tax'][key]
   require(proof==c['existing_capital_tax_record_for_comparison_only']==inherited['capital_tax'][key],
     'inherited tax proof changed')
   require(proof['verified_exempt'] is True,'capital source flag lost')
 conditional=proposal['capital_tax'][CONDITIONAL]
 require(conditional['evidence_kind']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','inference marker lost')
 examples=conditional['tax_examples']
 require(D(examples['cash_per_ten'])*D('.2')==D(examples['one_month_tax_per_ten']) and
   D(examples['cash_per_ten'])*D('.1')==D(examples['one_year_tax_per_ten']),'conditional cash-tax arithmetic mismatch')
 require(len(proposal['supplementary_distributions'])==3,'duplicate or missing supplement')
 require({s['instrument']+'|'+s['record']['dividOperateDate'] for s in proposal['supplementary_distributions']}==set(CASH),'supplement scope changed')
 for s in proposal['supplementary_distributions']:
  key=s['instrument']+'|'+s['record']['dividOperateDate']; row=s['record']; facts=adjustment['cases'][key]['primary_economic_facts']
  amount,announcement,record,pay=CASH[key]
  require((D(row['dividCashPsBeforeTax']),row['dividPlanDate'],row['dividRegistDate'],row['dividPayDate'])==
    (D(amount),announcement,record,pay),'cash supplement actual entitlement/date mismatch')
  require((D(facts['cash_per_eligible_original_share_gross']),facts['record_day'],facts['ex_day'],facts['cash_payment_day'])==
    (D(amount),record,key.split('|')[1],pay),'cash supplement differs from independent content review')
  require(D(row['dividStocksPs'])==D(row['dividReserveToStockPs'])==0 and row['dividStockMarketDate']=='','cash supplement contains noncash')
  require(s['source_sha256']==docs[s['source_file']]['sha256']==adjustment['cases'][key]['source_pdf']['sha256'],'cash source binding mismatch')
 require(len(proposal['adjustment_relationships'])==7,'seven factor relationships required')
 for rel in proposal['adjustment_relationships']:
  code=rel['instrument']; key=code+'|'+rel['adjustment_source_day']; c=adjustment['cases'][key]
  require(rel['adjustment_date_semantics_verified'] is False and rel['additional_entitlement_inferred_from_adjustment'] is False,'factor semantics/entitlement upgraded')
  require(rel['vendor_dividend_record'] in packets[code]['distributions'] and
    rel['vendor_dividend_record']==c['related_existing_vendor_distribution'],'earlier original distribution altered')
  require(rel['source_sha256']==docs[rel['source_file']]['sha256']==c['source_pdf']['sha256'],'factor PDF binding changed')
  require(rel['notice_confirmed_ex_date']==c['primary_economic_facts']['ex_day'] and
    rel['notice_confirmed_pay_date']==c['primary_economic_facts']['cash_payment_day'],'factor date relationship changed')


def reconstruct(packets, proposal, docs, sessions):
 source=[]
 for code,packet in sorted(packets.items()):
  source.extend((code,row,'VENDOR_DISTRIBUTION',None) for row in packet['distributions'])
 for s in proposal['supplementary_distributions']:
  require(s['instrument'] in packets,'supplement outside source universe')
  source.append((s['instrument'],s['record'],'PRIMARY_NOTICE_SUPPLEMENT',s))
 events=[]; receipts=[]; seen=set(); used=set()
 def bind(proof,code,row):
  d=docs[proof['source_file']]
  require((d['sha256'],d['instrument'],d['day'])==(proof['source_sha256'],code,row['dividPlanDate']),'primary binding mismatch')
  return d['sha256']
 for code,row,kind,supplement in source:
  require(row['code']==code[:2].lower()+'.'+code[2:],'source instrument mismatch')
  key=code+'|'+row['dividOperateDate']; require(key not in seen,'duplicate issuer/ex-date entitlement');seen.add(key)
  primary=[]
  if supplement:primary.append(bind(supplement,code,row))
  cash=decimal(row['dividCashPsBeforeTax']);stock=decimal(row['dividStocksPs']);capital_text=row['dividReserveToStockPs']
  require(stock==0,'unexpected stock dividend without tax basis')
  if not capital_text:
   display=row.get('dividCashStock','')
   require(cash>0 and display.startswith('10派') and '送' not in display and '转' not in display and not row['dividStockMarketDate'],
     'blank capital cannot be resolved as zero')
   capital_text='0'
  capital=decimal(capital_text);capital_verified=False
  if key in proposal['capital_tax']:
   proof=proposal['capital_tax'][key];used.add(key);primary.append(bind(proof,code,row))
   require(proof['verified_exempt'] is True and capital>0,'capital proof applicability mismatch');capital_verified=True
  announced,recorded,ex=map(day,(row['dividPlanDate'],row['dividRegistDate'],row['dividOperateDate']))
  paid=day(row['dividPayDate']) if row['dividPayDate'] else None
  listed=day(row['dividStockMarketDate']) if row['dividStockMarketDate'] else None
  require(announced<recorded<ex and recorded in sessions and ex in sessions,'invalid record/ex source timing')
  require((cash==0 or paid is not None and paid>=ex) and (capital==0 or listed is not None and listed>=ex),'invalid pay/list timing')
  identity={'instrument':code,'source_kind':kind,'source_distribution':row,'primary_source_sha256':sorted(set(primary)),
   'effective_stock_taxable_income_per_original_share':'0','capital_tax_exempt_verified':capital_verified,'stock_tax_basis_verified':False}
  eid=digest(identity)
  events.append({'event_id':eid,'instrument':code,'announced':announced,'recorded':recorded,'ex_date':ex,'pay_date':paid,
   'listed':listed,'cash_per_share':str(cash),'capital_per_share':str(capital),'capital_tax_exempt_verified':capital_verified,
   'stock_per_share':str(stock),'stock_taxable_income_per_share':'0','stock_tax_basis_verified':False})
  receipts.append({'event_id':eid,'instrument':code,'ex_date':ex,'source_kind':kind,'source_row_sha256':digest(row),
   'primary_source_sha256':sorted(set(primary)),'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),
   'requires_zero_record_ownership_if_tax_unverified':bool(capital>0 and not capital_verified)})
 require(used==set(proposal['capital_tax']),'orphan capital proof')
 return events,receipts


def main():
 parser=argparse.ArgumentParser()
 for n in ('source-root','repo-root','event-dir','output'):parser.add_argument('--'+n,required=True)
 args=parser.parse_args();base=Path(args.source_root);repo=Path(args.repo_root);eventdir=Path(args.event_dir);output=Path(args.output)
 require(not output.exists(),'preserve existing independent report')
 frozen={}
 def auth(path, expected):
  path=Path(path);require(sha(path)==expected,'frozen bytes changed: '+str(path));frozen[str(path)]=expected
 planfile=repo/'experiments/qlib/price-delay-event-source-plan.json';auth(planfile,PLAN_SHA);plan=read(planfile)
 require(plan['window']==[START,END] and plan['portfolio_returns_to_compute'] is False and plan['new_2026_queries_allowed'] is False,'plan scope changed')
 for key,root in [('method_code_sha256',repo),('local_source_sha256',base),('public_evidence_sha256',repo)]:
  for name,h in plan[key].items():auth(root/name,h)
 auth(repo/'experiments/qlib/price-delay-corporate-source-request.json',REQUEST_SHA)
 summary=read(eventdir/'summary.json');frozen[str(eventdir/'summary.json')]=sha(eventdir/'summary.json')
 require(summary['plan_sha256']==PLAN_SHA and summary['method_code_sha256']==plan['method_code_sha256'],'summary plan/method mismatch')
 require(set(summary['artifact_sha256'])=={'derived_events.json','event_source_receipts.json','effective_proofs.json'},'unexpected artifact set')
 for name,h in summary['artifact_sha256'].items():auth(eventdir/name,h)
 raw=base/'price-delay-raw-dev-20261021';reviewed=base/'price-delay-corporate-reviewed-20261021';capture_dir=base/'price-delay-corporate-primary-20261021'
 manifest=read(raw/'manifest.json');proposal=read(reviewed/'reviewed-manifest.json');capture=read(capture_dir/'manifest.json')
 require(summary['raw_manifest_sha256']==proposal['raw_manifest_sha256']==sha(raw/'manifest.json') and
   summary['reviewed_manifest_sha256']==sha(reviewed/'reviewed-manifest.json'),'source manifest binding mismatch')
 sessions=read(raw/'calendar.json')['sessions'];require(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'calendar scope mismatch')
 auth(raw/'calendar.json',manifest['calendar_sha256'])
 targetfile=base/'price-delay-pre2026-formations-20261021/targets.json';auth(targetfile,manifest['target_sha256'])
 require(manifest['target_sha256']==proposal['target_sha256']==summary['target_sha256'],'target binding mismatch')
 targets=read(targetfile)['price_delay_d1'];codes={c for t in targets.values() for c in t['weights']}
 require(len(targets)==24 and len(codes)==151 and codes==set(manifest['per_code_sha256']) and
   summary['source_packet_sha256']==manifest['per_code_sha256'],'target union/source scope mismatch')
 require(all(t['as_of'] in sessions and d in sessions and t['as_of']<d for d,t in targets.items()),'noncausal targets')
 packets={}
 for code,h in sorted(manifest['per_code_sha256'].items()):
  path=raw/'codes'/(code+'.json');auth(path,h);packet=read(path)
  require(packet['instrument']==code and packet['window']==[START,END] and [r['date'] for r in packet['bars']]==sessions,'raw packet scope/calendar mismatch')
  packets[code]=packet
 require(sum(len(p['distributions']) for p in packets.values())==375,'vendor source count changed')
 content=read(repo/'experiments/qlib/price-delay-primary-content-review.json')
 noncash=read(repo/content['noncash_review_file']);adjustment=read(repo/content['adjustment_review_file'])
 require(content['scoped_primary_content_review_completed'] is True and content['documents_read']==15 and content['pages_read']==54 and
   content['capture_manifest_sha256']==proposal['capture_manifest_sha256']==sha(capture_dir/'manifest.json'),'content/capture bindings mismatch')
 for kind in ('noncash','adjustment'):auth(repo/content[kind+'_review_file'],content[kind+'_review_sha256'])
 require(capture['request_sha256']==REQUEST_SHA and not capture['errors'] and not capture['pending_cases'],'capture incomplete')
 docs={d['file']:d for d in proposal['documents']}
 require(len(docs)==len(proposal['documents'])==15 and set(docs)=={d['file'] for d in capture['documents'].values()},'PDF set mismatch')
 for d in docs.values():
  require(Path(d['file']).name==d['file'] and day(d['day'])<=END,'unsafe/future PDF identity')
  auth(reviewed/d['file'],d['sha256']);auth(capture_dir/d['file'],d['sha256'])
 for key,d in capture['documents'].items():
  require(content['all15_PDF_sha256'][key]==docs[d['file']]['sha256']==d['sha256'],'capture/content PDF mismatch')
 for name,h in proposal['inherited_source_manifests'].items():
  require(plan['local_source_sha256'].get(name)==h,'inherited source missing from plan');auth(base/name,h)
 inherited=read(base/'budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json')
 require(proposal['event_compilation_admitted'] is False and proposal['admitted_for_account_replay'] is False,'original proposal admission changed')
 projected=copy.deepcopy(proposal);projected.update(status='EVALUATOR_SOURCE_PROJECTION_NO_ACCOUNT_ADMISSION',
  original_cash_override_contract_label=proposal['cash_override_contract'],cash_override_contract='PRIMARY_NOTICE_CASH_PRECISION_V1',
  source_reviewed_manifest_sha256=sha(reviewed/'reviewed-manifest.json'))
 require(projected==read(eventdir/'effective_proofs.json'),'effective projection is not literal preserved source interpretation')
 proof_semantics(proposal,docs,noncash,adjustment,packets,inherited)
 expected_events,expected_receipts=reconstruct(packets,proposal,docs,sessions)
 require(len(expected_events)==len({e['event_id'] for e in expected_events})==378,'378 unique events required')
 def verify(events,receipts):
  require(events==expected_events and receipts==expected_receipts,'independent economics/identity/receipt comparison failed')
 actual_events=read(eventdir/'derived_events.json');actual_receipts=read(eventdir/'event_source_receipts.json');verify(actual_events,actual_receipts)
 require([r['instrument']+'|'+r['ex_date'] for r in expected_receipts if r['requires_zero_record_ownership_if_tax_unverified']]==[UNKNOWN],'unique zero ownership guard mismatch')
 kinds={kind:sum(r['source_kind']==kind for r in expected_receipts) for kind in ['VENDOR_DISTRIBUTION','PRIMARY_NOTICE_SUPPLEMENT','PRIMARY_CASH_PRECISION_CORRECTION']}
 require(kinds==summary['source_kind_counts']=={'VENDOR_DISTRIBUTION':375,'PRIMARY_NOTICE_SUPPLEMENT':3,'PRIMARY_CASH_PRECISION_CORRECTION':0},'source kind counts mismatch')
 require(sum(e['capital_tax_exempt_verified'] for e in expected_events)==summary['verified_capital_tax_exemptions']==4 and
   sum(e['stock_tax_basis_verified'] for e in expected_events)==summary['verified_stock_tax_basis_events']==0,'tax flag counts mismatch')
 require(summary['compiled_events']==378 and summary['source_names']==151 and summary['source_sessions']==486 and summary['monthly_targets']==24 and
   summary['direct_primary_capital_tax_statements']==3 and summary['conditional_capital_tax_inferences']==1 and
   summary['unverified_tax_proof_receipts']==1 and summary['unexplained_later_factor_date_labels']==7,'summary counts mismatch')
 for flag in ['original_source_proposal_modified','adjustment_factors_used_to_infer_entitlements','event_compilation_independently_verified',
   'strict_statutory_capital_tax_certification','raw_account_replay_admitted','full_corporate_actions_certified',
   'actual_FIFO_tax_liability_verified','historical_arrival_certified','portfolio_returns_computed','new_2026_queries','objective_achieved']:
  require(summary[flag] is False,'unsupported summary claim: '+flag)
 negative={}
 def reject(label,fn):
  try:fn()
  except (ValueError,KeyError,AssertionError):negative[label]=True
  else:raise ValueError('negative control accepted: '+label)
 def semantics(p=proposal,d=docs):return proof_semantics(p,d,noncash,adjustment,packets,inherited)
 tampered=copy.deepcopy(packets);tampered['SH600167']['distributions'][0]['dividCashPsBeforeTax']='9.99'
 reject('changed_original_vendor_economics_not_hash_gate',lambda:verify(*reconstruct(tampered,proposal,docs,sessions)))
 p=copy.deepcopy(proposal);p['supplementary_distributions'].append(copy.deepcopy(p['supplementary_distributions'][0]))
 reject('duplicate_supplement_same_issuer_ex_date',lambda:reconstruct(packets,p,docs,sessions))
 p=copy.deepcopy(proposal);next(s for s in p['supplementary_distributions'] if s['instrument']=='SZ002508')['record']['dividCashPsBeforeTax']='0.497403'
 reject('price_reference_instead_of_eligible_cash',lambda:semantics(p))
 d=copy.deepcopy(docs);d['SZ002508-1218790856.pdf']['sha256']='0'*64
 reject('altered_PDF_binding_in_memory',lambda:semantics(proposal,d))
 p=copy.deepcopy(proposal);p['capital_tax'][UNKNOWN]=copy.deepcopy(p['capital_tax'][CONDITIONAL])
 reject('unknown_capital_exemption_injected',lambda:semantics(p))
 events=copy.deepcopy(actual_events);receipts=copy.deepcopy(actual_receipts);idx=next(i for i,e in enumerate(events) if e['instrument']+'|'+e['ex_date']==UNKNOWN)
 events[idx]['capital_tax_exempt_verified']=True;receipts[idx]['requires_zero_record_ownership_if_tax_unverified']=False
 reject('unknown_receipt_guard_and_event_flag_upgraded',lambda:verify(events,receipts))
 events=copy.deepcopy(actual_events);receipts=copy.deepcopy(actual_receipts);events.append(copy.deepcopy(events[0]));receipts.append(copy.deepcopy(receipts[0]))
 reject('second_entitlement_from_factor_label',lambda:verify(events,receipts))
 receipts=copy.deepcopy(actual_receipts);receipts[-1]['source_row_sha256']='0'*64
 reject('erased_original_source_row_receipt',lambda:verify(actual_events,receipts))
 events=copy.deepcopy(actual_events);events[-1]['recorded']='2024-01-08'
 reject('wrong_supplement_record_date',lambda:verify(events,actual_receipts))
 p=copy.deepcopy(proposal);p['capital_tax'][CONDITIONAL]['evidence_kind']='DIRECT_STATUTORY_CERTIFICATE'
 reject('conditional_tax_inference_upgraded',lambda:semantics(p))
 for path,h in frozen.items():require(sha(path)==h,'source changed during audit: '+path)
 result={'status':'INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED',
  'audit_code_sha256':sha(__file__),'plan_sha256':PLAN_SHA,'summary_sha256':sha(eventdir/'summary.json'),
  'reviewed_manifest_sha256':sha(reviewed/'reviewed-manifest.json'),'raw_manifest_sha256':sha(raw/'manifest.json'),
  'source_names':151,'source_sessions':486,'monthly_targets':24,'events_reconstructed':378,'source_kind_counts':kinds,
  'all151_source_packets_authenticated':True,'all15_primary_PDF_bytes_and_two_content_reviews_authenticated':True,
  'all378_economics_dates_event_IDs_and_receipts_identical':True,'all_frozen_inputs_unchanged_after_audit':True,
  'primary_cash_supplements':{key:values[0] for key,values in CASH.items()},'cash_precision_proofs_bound':0,
  'direct_capital_tax_proofs_bound':sorted(DIRECT),'conditional_capital_tax_inference_bound':CONDITIONAL,
  'unverified_capital_tax_zero_record_ownership_required':[UNKNOWN],'actual_zero_record_ownership_verified':False,
  'seven_later_factor_labels_remain_unexplained':True,'additional_entitlements_from_factor_labels':0,
  'negative_controls_rejected':negative,'semantic_negative_controls_use_only_hash_gate':False,
  'imports_project_code':False,'production_compile_function_called':False,'account_instantiated_or_replayed':False,
  'source_inputs_modified':False,'repository_modified':False,'network_calls':0,'new_2026_values_read':False,
  'strict_statutory_capital_tax_certification':False,'actual_FIFO_tax_liability_verified':False,
  'historical_arrival_certified':False,'true_point_in_time_certified':False,'full_corporate_actions_certified':False,
  'raw_account_replay_admitted':False,'portfolio_returns_computed':False,'objective_achieved':False,
  'critical_or_important_findings':0,
  'limitations':['Reconstructs source projection, not all 375 vendor events from independent primary notices.',
    'Four inherited event flags retain three direct issuer statements and one conditional inference; no statutory or final investor tax certification.',
    'SH603596 zero record inventory remains an obligation for a separately frozen actual-share replay, not established by this source audit.',
    'Seven late vendor factor labels do not authenticate factor methodology or support second income.',
    'No queue, actual payment arrival, registry fractional allocation, historical PIT arrival, FIFO tax, account or ROI validation.']}
 output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
 print('Independent378 events/economics/IDs/receipts matched; '+str(len(negative))+' semantic controls rejected; no account/ROI')


if __name__=='__main__':main()
