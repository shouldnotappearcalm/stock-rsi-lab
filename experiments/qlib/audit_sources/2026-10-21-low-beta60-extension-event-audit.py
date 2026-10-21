"""Stdlib reconstruction of 87 appended events with original179 byte continuity."""
import argparse,copy,hashlib,json
from collections import Counter
from decimal import Decimal as D,ROUND_DOWN
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('source-root','event-dir','expected-summary-sha256','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);outdir=Path(a.event_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
planfile=repo/'experiments/qlib/low-beta60-extension-event-plan.json'
assert sha(planfile)=='124b94a62ed55a8641107a04e17054abc493a5d824794ded73667e2b143bb112'
plan=read(planfile);summary=read(outdir/'summary.json')
assert sha(outdir/'summary.json')==a.expected_summary_sha256 and summary['plan_sha256']==sha(planfile)
for key,parent in (('method_code_sha256',repo),('local_source_sha256',base),('public_evidence_sha256',repo)):
 for f,h in plan[key].items():assert not Path(f).is_absolute() and '..' not in Path(f).parts and sha(parent/f)==h
for name,h in summary['artifact_sha256'].items():assert Path(name).name==name and sha(outdir/name)==h
original=base/'low-beta60-raw-dev-20261021';raw=base/'low-beta60-raw-extension-20261021'
om=read(original/'manifest.json');m=read(raw/'manifest.json');assert len(om['per_code_sha256'])==69 and len(m['per_code_sha256'])==79
sessions=read(raw/'calendar.json')['sessions'];old_sessions=read(original/'calendar.json')['sessions']
assert len(sessions)==671 and sessions==sorted(set(sessions)) and sessions[:486]==old_sessions
assert [sessions[0],sessions[-1]]==['2023-12-29','2026-10-13']
assert m['calendar_sha256']==sha(raw/'calendar.json') and summary['raw_manifest_sha256']==sha(raw/'manifest.json')
reviewed=base/'low-beta60-corporate-reviewed-2026-20261021';proposal=read(reviewed/'reviewed-manifest.json')
assert sha(reviewed/'reviewed-manifest.json')==summary['reviewed_2026_manifest_sha256']
assert (outdir/'effective_2026_proofs.json').read_bytes()==(reviewed/'reviewed-manifest.json').read_bytes()
docs={d['file']:d for d in proposal['documents']};assert len(docs)==6
for name,d in docs.items():assert sha(reviewed/name)==d['sha256'] and d['day']<='2026-10-13'
assert set(proposal['unresolved_tax'])=={'SZ000937|2026-06-17'}
assert 'SZ000937|2026-06-17' not in proposal['capital_tax']
assert proposal['unresolved_tax']['SZ000937|2026-06-17']['verified_exempt'] is False
assert proposal['unresolved_tax']['SZ000937|2026-06-17']['later_data_may_enter_decision_snapshot'] is False
old_dir=base/'low-beta60-account-source-events-20261021';old_summary=read(old_dir/'summary.json')
assert read(base/'low-beta60-event-source-independent-audit-20261021.json')['summary_sha256']==sha(old_dir/'summary.json')
for name,h in old_summary['artifact_sha256'].items():assert sha(old_dir/name)==h
old_events=read(old_dir/'derived_events.json');old_receipts=read(old_dir/'event_source_receipts.json')
assert len(old_events)==len(old_receipts)==179
for name in ('derived_events.json','event_source_receipts.json'):
 assert (outdir/('original_'+name)).read_bytes()==(old_dir/name).read_bytes()
source=[];ignored=0
for code,h in sorted(m['per_code_sha256'].items()):
 f=raw/'codes'/(code+'.json');assert sha(f)==h;packet=read(f)
 assert packet['instrument']==code and packet['window']==['2023-12-29','2026-10-13']
 assert [r['date'] for r in packet['bars']]==sessions
 if code in om['per_code_sha256']:
  f0=original/'codes'/(code+'.json');assert sha(f0)==om['per_code_sha256'][code];oldpacket=read(f0)
  for field,daykey in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
   assert [r for r in packet[field] if r[daykey]<'2026-01-01']==oldpacket[field]
 else:ignored+=sum(r['dividOperateDate']<'2026-01-01' for r in packet['distributions'])
 for row in packet['distributions']:
  if row['dividOperateDate']<'2026-01-01':continue
  assert '2026-01-01'<=row['dividRegistDate']<row['dividOperateDate']<='2026-10-13'
  source.append((code,row,'VENDOR_DISTRIBUTION',None))
assert len(source)==86 and ignored==25
for s in proposal['supplementary_distributions']:source.append((s['instrument'],s['record'],'PRIMARY_NOTICE_SUPPLEMENT',s))
assert len(source)==87
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

new_events=expected_events;new_receipts=expected_receipts
assert len(new_events)==len(new_receipts)==87
expected_events=old_events+new_events;expected_receipts=old_receipts+new_receipts
assert sorted(r['instrument']+'|'+r['ex_date'] for r in new_receipts if r['requires_zero_record_ownership_if_tax_unverified'])==['SZ000937|2026-06-17']
assert all(not e['capital_tax_exempt_verified'] for e in new_events if e['instrument']=='SZ000937' and e['ex_date']=='2026-06-17')
def verify(events,receipts):
 assert events==expected_events and receipts==expected_receipts
 assert len(events)==len(receipts)==len({e['event_id'] for e in events})==266
actual_events=read(outdir/'derived_events.json');actual_receipts=read(outdir/'event_source_receipts.json');verify(actual_events,actual_receipts)
assert actual_events[:179]==old_events and actual_receipts[:179]==old_receipts
negative={}
for label in ('old_event_rewrite','vendor_cash_instead_of_primary','wrong_new_record_date','missing_supplement','silent_tax_exemption','erased_unknown_tax_guard'):
 events=copy.deepcopy(actual_events);receipts=copy.deepcopy(actual_receipts)
 cash_i=next(i for i,e in enumerate(events) if e['instrument']=='SZ000975' and e['ex_date']=='2026-04-24')
 supp_i=next(i for i,r in enumerate(receipts) if r['source_kind']=='PRIMARY_NOTICE_SUPPLEMENT' and r['ex_date']=='2026-02-06')
 tax_i=next(i for i,e in enumerate(events) if e['instrument']=='SZ000937' and e['ex_date']=='2026-06-17')
 if label=='old_event_rewrite':events[0]['cash_per_share']='999'
 elif label=='vendor_cash_instead_of_primary':events[cash_i]['cash_per_share']='0.480402'
 elif label=='wrong_new_record_date':events[cash_i]['recorded']='2026-04-24'
 elif label=='missing_supplement':del events[supp_i];del receipts[supp_i]
 elif label=='silent_tax_exemption':events[tax_i]['capital_tax_exempt_verified']=True
 else:receipts[tax_i]['requires_zero_record_ownership_if_tax_unverified']=False
 try:verify(events,receipts)
 except AssertionError:negative[label]=True
 else:raise AssertionError('bad source/economic projection accepted: '+label)
kinds=dict(Counter(r['source_kind'] for r in actual_receipts))
assert kinds==summary['source_kind_counts']=={'VENDOR_DISTRIBUTION':262,'PRIMARY_NOTICE_SUPPLEMENT':2,'PRIMARY_CASH_PRECISION_CORRECTION':2}
assert summary['original_events']==179 and summary['appended_events']==87 and summary['compiled_events']==266
assert summary['earlier_rows_of_future_only_names_ignored']==25 and summary['unverified_tax_event_keys']==['SZ000937|2026-06-17']
for flag in ('account_replay_admitted','historical_arrival_verified','actual_FIFO_tax_liability_verified','full_corporate_actions_certified','portfolio_returns_computed','full_requested_October_complete','candidate_promoted','objective_achieved'):assert summary[flag] is False
result={'status':'INDEPENDENT266_EVENTS_RECONSTRUCTED_ORIGINAL179_UNCHANGED_ONE_UNKNOWN_TAX_GUARD',
 'audit_code_sha256':sha(__file__),'plan_sha256':sha(planfile),'summary_sha256':sha(outdir/'summary.json'),
 'source_names':79,'source_sessions':671,'original_events_preserved':179,'appended_events_reconstructed':87,'events_reconstructed':266,
 'source_kind_counts':kinds,'original_event_and_receipt_files_copied_byte_exact':True,
 'original69_raw_prefixes_identical':True,'earlier_future_only_name_rows_excluded':ignored,
 'unverified_tax_event_keys':['SZ000937|2026-06-17'],
 'verified_capital_events_combined':sum(e['capital_tax_exempt_verified'] for e in expected_events),
 'verified_stock_tax_basis_events_combined':sum(e['stock_tax_basis_verified'] for e in expected_events),
 'negative_controls_rejected':negative,'negative_controls_use_hash_gate':False,'imports_project_code':False,
 'source_inputs_modified':False,'account_replay_admitted':False,'historical_arrival_verified':False,
 'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
 'portfolio_returns_computed':False,'candidate_promoted':False,'objective_achieved':False}
with Path(a.output).open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(result['status'])
