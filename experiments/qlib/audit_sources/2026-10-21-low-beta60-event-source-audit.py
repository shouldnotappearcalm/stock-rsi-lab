"""Stdlib independent reconstruction of source event economics and identities."""
import argparse,copy,hashlib,json
from collections import Counter
from decimal import Decimal as D,ROUND_DOWN
from pathlib import Path

p=argparse.ArgumentParser()
for n in ('source-root','event-dir','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);outdir=Path(a.event_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
planfile=repo/'experiments/qlib/low-beta60-event-source-plan.json'
assert sha(planfile)=='401943c5843e66b437e0c5dd0e645623947eb2bec416494cadc2c55371a43bd6'
plan=read(planfile);summary=read(outdir/'summary.json')
assert summary['plan_sha256']==sha(planfile)
for key,root in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
 assert all(sha(root/f)==h for f,h in plan[key].items())
assert summary['method_code_sha256']==plan['method_code_sha256']
assert all(sha(outdir/f)==h for f,h in summary['artifact_sha256'].items())
raw=base/'low-beta60-raw-dev-20261021';reviewed=base/'low-beta60-corporate-reviewed-20261021'
m=read(raw/'manifest.json');proposal=read(reviewed/'reviewed-manifest.json')
assert summary['raw_manifest_sha256']==sha(raw/'manifest.json')==proposal['raw_manifest_sha256']
assert summary['reviewed_manifest_sha256']==sha(reviewed/'reviewed-manifest.json')
assert summary['source_packet_sha256']==m['per_code_sha256'] and len(m['per_code_sha256'])==69
sessions=read(raw/'calendar.json')['sessions'];assert len(sessions)==486 and sessions==sorted(set(sessions))
assert [sessions[0],sessions[-1]]==['2023-12-29','2025-12-31']
assert sha(raw/'calendar.json')==m['calendar_sha256']
targetfile=base/'low-beta60-pre2026-formations-20261021/targets.json';targets=read(targetfile)['low_beta60']
assert sha(targetfile)==m['target_sha256']==proposal['target_sha256']==summary['target_sha256']
assert len(targets)==24 and set(m['per_code_sha256'])=={c for t in targets.values() for c in t['weights']}
projected=copy.deepcopy(proposal);projected.update(status='EVALUATOR_SOURCE_PROJECTION_NO_ACCOUNT_ADMISSION',
 original_cash_override_contract_label=proposal['cash_override_contract'],cash_override_contract='PRIMARY_NOTICE_CASH_PRECISION_V1',
 source_reviewed_manifest_sha256=sha(reviewed/'reviewed-manifest.json'))
assert projected==read(outdir/'effective_proofs.json')
docs={d['file']:d for d in proposal['documents']};assert len(docs)==10
for name,d in docs.items():assert sha(reviewed/name)==d['sha256'] and d['day']<='2025-12-31'
source=[]
for code,h in sorted(m['per_code_sha256'].items()):
 f=raw/'codes'/(code+'.json');assert sha(f)==h;packet=read(f)
 assert packet['instrument']==code and packet['window']==['2023-12-29','2025-12-31']
 assert [r['date'] for r in packet['bars']]==sessions
 source.extend((code,r,'VENDOR_DISTRIBUTION',None) for r in packet['distributions'])
assert len(source)==178
for s in proposal['supplementary_distributions']:source.append((s['instrument'],s['record'],'PRIMARY_NOTICE_SUPPLEMENT',s))
assert len(source)==179

def bind(proof,code,row):
 d=docs[proof['source_file']]
 assert d['sha256']==proof['source_sha256'] and d['instrument']==code and d['day']==row['dividPlanDate']
 return d['sha256']

expected_events=[];expected_receipts=[];seen=set();used_cash=set();used_capital=set();used_stock=set()
for code,row,kind,supplement in source:
 key=code+'|'+row['dividOperateDate'];assert key not in seen;seen.add(key)
 assert row['code']==code[:2].lower()+'.'+code[2:]
 primary=[]
 if supplement:primary.append(bind(supplement,code,row))
 cash,stock=D(row['dividCashPsBeforeTax']),D(row['dividStocksPs']);income=D(0);stock_verified=False
 sp=proposal['stock_dividend_tax_bases'].get(key)
 if sp:
  primary.append(bind(sp,code,row));used_stock.add(key)
  assert sp['verified'] is True and stock==D(sp['expected_stock_per_original_share'])>0
  income=D(sp['taxable_income_per_original_share']);assert income>0;stock_verified=True
 text=row['dividReserveToStockPs']
 if not text:
  display=row['dividCashStock']
  assert (cash>0 and stock==0 and display.startswith('10派') and '送' not in display and '转' not in display and not row['dividStockMarketDate']) or (stock_verified and display.startswith('10送') and '转' not in display)
  text='0'
 capital=D(text);capital_verified=False;cp=proposal['capital_tax'].get(key)
 if cp:
  primary.append(bind(cp,code,row));used_capital.add(key)
  assert cp['verified_exempt'] is True and capital>0;capital_verified=True
 assert all(v.is_finite() and v>=0 for v in (cash,stock,capital,income))
 assert row['dividRegistDate'] in sessions and row['dividOperateDate'] in sessions
 assert row['dividPlanDate']<=row['dividRegistDate']<row['dividOperateDate']
 identity={'instrument':code,'source_kind':kind,'source_distribution':row,'primary_source_sha256':sorted(set(primary)),
  'effective_stock_taxable_income_per_original_share':str(income),'capital_tax_exempt_verified':capital_verified,'stock_tax_basis_verified':stock_verified}
 event_id=digest(identity)
 event={'event_id':event_id,'instrument':code,'announced':row['dividPlanDate'],'recorded':row['dividRegistDate'],
  'ex_date':row['dividOperateDate'],'pay_date':row['dividPayDate'] or None,'listed':row['dividStockMarketDate'] or None,
  'cash_per_share':str(cash),'capital_per_share':str(capital),'capital_tax_exempt_verified':capital_verified,
  'stock_per_share':str(stock),'stock_taxable_income_per_share':str(income),'stock_tax_basis_verified':stock_verified}
 receipt={'event_id':event_id,'instrument':code,'ex_date':event['ex_date'],'source_kind':kind,
  'source_row_sha256':digest(row),'primary_source_sha256':sorted(set(primary)),
  'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),
  'requires_zero_record_ownership_if_tax_unverified':bool(capital>0 and not capital_verified or stock>0 and not stock_verified)}
 correction=proposal['cash_overrides'].get(key)
 if correction:
  used_cash.add(key);primary_sha=bind(correction,code,row);effective=D(correction['effective_cash_per_share'])
  assert correction['verified'] is True and correction['kind']=='PRIMARY_NOTICE_CASH_PRECISION'
  assert correction['source_row_sha256']==digest(row) and D(correction['expected_vendor_cash_per_share'])==cash
  assert stock==capital==0 and event['listed'] is None and kind=='VENDOR_DISTRIBUTION'
  assert effective.is_finite() and effective>cash and effective.quantize(D(1).scaleb(cash.as_tuple().exponent),rounding=ROUND_DOWN)==cash
  corrected_id=digest({'original_event_id':event_id,'source_kind':'PRIMARY_CASH_PRECISION_CORRECTION',
   'source_row_sha256':digest(row),'primary_source_sha256':primary_sha,'cash_precision_proof_sha256':digest(correction),
   'vendor_cash_per_share':str(cash),'effective_cash_per_share':str(effective)})
  event.update(event_id=corrected_id,cash_per_share=str(effective))
  receipt.update(event_id=corrected_id,original_event_id=event_id,source_kind='PRIMARY_CASH_PRECISION_CORRECTION',
   primary_source_sha256=sorted(set(receipt['primary_source_sha256']+[primary_sha])),vendor_cash_per_share=str(cash),
   effective_cash_per_share=str(effective),cash_precision_proof_sha256=digest(correction))
 expected_events.append(event);expected_receipts.append(receipt)
assert used_cash==set(proposal['cash_overrides']) and used_capital==set(proposal['capital_tax']) and used_stock==set(proposal['stock_dividend_tax_bases'])

def verify(events,receipts):
 assert events==expected_events and receipts==expected_receipts
 assert len(events)==len({e['event_id'] for e in events})==179

actual_events=read(outdir/'derived_events.json');actual_receipts=read(outdir/'event_source_receipts.json');verify(actual_events,actual_receipts)
negative={}
for label in ('vendor_cash_instead_of_primary','wrong_record_date','missing_supplement','duplicate_factor_entitlement','erased_source_receipt'):
 events=copy.deepcopy(actual_events);receipts=copy.deepcopy(actual_receipts)
 cash_i=next(i for i,r in enumerate(receipts) if r['source_kind']=='PRIMARY_CASH_PRECISION_CORRECTION')
 supp_i=next(i for i,r in enumerate(receipts) if r['source_kind']=='PRIMARY_NOTICE_SUPPLEMENT')
 if label=='vendor_cash_instead_of_primary':events[cash_i]['cash_per_share']='0.240097'
 elif label=='wrong_record_date':events[cash_i]['recorded']='2025-08-13'
 elif label=='missing_supplement':del events[supp_i];del receipts[supp_i]
 elif label=='duplicate_factor_entitlement':events.append(copy.deepcopy(events[0]));receipts.append(copy.deepcopy(receipts[0]))
 else:receipts[cash_i]['source_row_sha256']='0'*64
 try:verify(events,receipts)
 except AssertionError:negative[label]=True
 else:raise AssertionError('negative control accepted: '+label)
kinds=dict(Counter(r['source_kind'] for r in expected_receipts))
assert kinds==summary['source_kind_counts']=={'VENDOR_DISTRIBUTION':177,'PRIMARY_NOTICE_SUPPLEMENT':1,'PRIMARY_CASH_PRECISION_CORRECTION':1}
assert sum(e['capital_tax_exempt_verified'] for e in expected_events)==summary['verified_capital_tax_exemptions']==3
assert sum(e['stock_tax_basis_verified'] for e in expected_events)==summary['verified_stock_tax_basis_events']==1
assert not any(r['requires_zero_record_ownership_if_tax_unverified'] for r in expected_receipts)
for flag in ('raw_account_replay_admitted','full_corporate_actions_certified','actual_FIFO_tax_liability_verified','historical_arrival_certified','portfolio_returns_computed','new_2026_queries','objective_achieved'):assert summary[flag] is False
result={'status':'INDEPENDENT_179_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED',
 'audit_code_sha256':sha(__file__),'plan_sha256':sha(planfile),'summary_sha256':sha(outdir/'summary.json'),
 'source_names':69,'source_sessions':486,'monthly_targets':24,'events_reconstructed':179,'source_kind_counts':kinds,
 'capital_exemption_proofs_bound':3,'stock_tax_basis_proofs_bound':1,'cash_precision_proofs_bound':1,
 'negative_controls_rejected':negative,'negative_controls_use_hash_gate':False,
 'effective_primary_cash_per_share':'0.2400974','original_vendor_cash_per_share':'0.240097',
 'imports_project_code':False,'input_sources_modified':False,'unexplained_later_factor_date_labels':5,
 'raw_account_replay_admitted':False,'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
 'historical_arrival_certified':False,'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('Independent179events and receipts match; five arithmetic/source tamper controls rejected; no ROI')
