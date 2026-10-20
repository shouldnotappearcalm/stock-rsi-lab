"""Independently identify the original event blocking both raw diagnostics."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('source-root','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();b=Path(a.source_root);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
root=b/'budgeted-residual-raw-daily-development-20261021';summary=read(root/'summary.json')
plan=repo/'experiments/qlib/budgeted-residual-raw-daily-development-plan.json'
assert sha(plan)==summary['plan_sha256']=='db9ab472409450ecfff462779d0e24e62c10cd31f22100b47fa39f86a8bf9a7a'
assert summary['method_code_sha256']==read(plan)['method_code_sha256']
assert all(sha(repo/f)==h for f,h in summary['method_code_sha256'].items())
frozen=read(plan)
for n,h in frozen['local_source_sha256'].items():
 assert not Path(n).is_absolute() and '..' not in Path(n).parts and sha(b/n)==h
for n,h in frozen['public_evidence_sha256'].items():
 assert not Path(n).is_absolute() and '..' not in Path(n).parts and sha(repo/n)==h
events=read(b/'budgeted-residual-account-source-events-20261021/derived_events.json')
receipt=read(b/'budgeted-residual-account-source-events-20261021/event_source_receipts.json')
unknown={r['event_id'] for r in receipt if r['requires_zero_record_ownership_if_tax_unverified']}
assert len(unknown)==3
assert len(events)==len(receipt)==510
assert {e['event_id'] for e in events}=={r['event_id'] for r in receipt}
assert {(e['instrument'],e['ex_date']) for e in events if e['event_id'] in unknown}=={('SH600161','2024-06-20'),('SH600580','2025-06-27'),('SH603596','2024-05-20')}
assert all(r['instrument']==next(e['instrument'] for e in events if e['event_id']==r['event_id']) for r in receipt)
proofs=[]
for cost,result in summary['results_by_extra_bps'].items():
 assert result['status']=='INVALID_ACCOUNT_OR_SOURCE' and result['error']=='applicable capital transfer tax treatment is unverified'
 folder=root/cost
 assert {f.name:sha(f) for f in folder.iterdir()}==result['failure_artifact_sha256']
 state=read(folder/'failed_account_state.json');assert state['last_account_clock']==['2025-06-26',1]
 assert state['owned_shares']['SH600580']==1100
 corporate=state['corporate_ledger'];rows=[]
 for event in events:
  if event['event_id'] not in unknown:continue
  key=event['event_id'];records=[r for r in corporate if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id']==key]
  ex=[r for r in corporate if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id']==key]
  assert len(records)==1 and records[0]['day']==event['recorded']
  if event['instrument']=='SH600580':
   assert event['recorded']=='2025-06-26' and event['ex_date']=='2025-06-27' and event['capital_per_share']=='0.200000'
   assert records[0]['quantity']==1100 and not ex and event['capital_tax_exempt_verified'] is False
   status='NONZERO_REGISTERED_OWNERSHIP_UNKNOWN_TAX_REJECTED_BEFORE_EX_LEDGER'
  else:
   assert event['instrument'] in ('SH600161','SH603596') and len(ex)==1
   assert records[0]['quantity']==ex[0]['registered_quantity']==0
   status='ACTUAL_RECORD_AND_EX_DATE_ZERO_OWNERSHIP_OBSERVED_IN_FAILED_PREFIX_ONLY'
  rows.append({'instrument':event['instrument'],'event_id':key,'recorded':event['recorded'],'ex_date':event['ex_date'],
     'registered_quantity':records[0]['quantity'],'status':status})
 assert len(rows)==3
 proofs.append({'extra_cost_bps':int(cost),'last_account_clock':state['last_account_clock'],'events':rows,
    'failed_state_sha256':sha(folder/'failed_account_state.json')})
assert len(proofs)==2 and summary['raw_daily_proxy_development_gate_passes'] is False
r={'status':'TWO_FROZEN_RAW_DIAGNOSTICS_BLOCKED_ON_ORIGINAL_WOLONG_CAPITAL_TAX_SOURCE',
 'audit_code_sha256':sha(__file__),'summary_sha256':sha(root/'summary.json'),'plan_sha256':sha(plan),'profiles':proofs,
 'all_six_frozen_local_inputs_and_six_public_evidence_hashes_verified':True,
 'completed_annual_returns_available':False,'source_tax_override_added':False,'investment_rule_changed':False,
 'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(r,indent=2)+'\n')
print('Both profiles blocked at the same original1100share taxable-source gap; other2unknown event entitlements actuallyzero')
