"""Separate counterfactual tax scenario; original source gate remains false."""
import argparse,json,hashlib
from datetime import date
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts.fundamental_query_journal import file_sha
from scripts.replay_budgeted_stock_distribution_targets import simulate_budgeted_fixed_targets
from scripts.run_low_risk_raw_share_validation import clean,summarize_case,validate_source_coverage
from scripts.run_low_risk_feedback_cost_stress import write_case
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.capital_income_stress_account import CapitalIncomeStressAccount,load_capital_income_basis

from scripts.run_budgeted_residual_raw_development import METHOD_FILES as ORIGINAL_METHOD_FILES

METHOD_FILES=ORIGINAL_METHOD_FILES+('scripts/run_budgeted_capital_income_stress_development.py',
 'src/stock_rsi/capital_income_stress_account.py')


def account_state_bytes(acct):
 state=clean({'last_account_clock':acct._last_clock,'cash':acct.broker.cash,'positions':acct.broker.positions,
    'orders':acct.broker.orders,'fills':acct.broker.fills,'owned_shares':acct.owned_quantities(),
    'corporate_ledger':acct.corporate_ledger,'cash_claims':acct.cash_claims,'stock_claims':acct.stock_claims})
 return (json.dumps(state,indent=2)+'\n').encode()


def verify_prefix_state(account,day,expected_sha256,evidence):
 actual=hashlib.sha256(account_state_bytes(account)).hexdigest()
 if actual!=expected_sha256:raise ValueError('original failed account prefix not reproduced; scenario prohibited')
 evidence.append({'day':day.isoformat(),'account_prefix_sha256':actual,'original_failure_bytes_reproduced':True})


def prefix_checked_factory(bps,basis,prefix_day,expected_sha256,evidence):
 class PrefixAccount(CapitalIncomeStressAccount):
  def start_day(self,day):
   if day==prefix_day and not evidence:
    verify_prefix_state(self,day,expected_sha256,evidence)
   return super().start_day(day)
 def factory(cal,cash,distributions,**kw):
  return PrefixAccount(cal,cash,distributions,capital_income_basis=basis,
      broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
 return factory


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('raw diagnostic output already exists')
 if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('raw diagnostic plan changed')
 plan=json.loads(Path(a.plan).read_text())
 if (plan['status']!='FROZEN_BEFORE_FULL_CAPITAL_INCOME_COUNTERFACTUAL_OUTCOMES'
     or plan['initial_CNY']!='1000000' or plan['extra_cost_bps']!=[20,40]
     or plan['window']!=['2023-12-29','2025-12-31']
     or plan['tax_scenario']!='COUNTERFACTUAL_FULL_CAPITAL_INCOME_TAX_STRESS'
     or plan['reserve_rate']!='.2' or plan['prefix_checkpoint']!='2025-06-27'
     or plan['original_source_gate_remains_false'] is not True
     or set(plan['method_code_sha256'])!=set(METHOD_FILES)
     or any(file_sha(repo/n)!=h for n,h in plan['method_code_sha256'].items())):
  raise ValueError('raw diagnostic method/profile scope changed')
 for n,h in plan['local_source_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(base/n)!=h:raise ValueError('raw diagnostic frozen input changed')
 for n,h in plan['public_evidence_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(repo/n)!=h:raise ValueError('raw diagnostic public evidence changed')
 raw=base/'budgeted-residual-raw-dev-20261021';proofdir=base/'budgeted-residual-corporate-reviewed-20261021'
 source=base/'budgeted-residual-account-source-events-20261021'
 m=json.loads((raw/'manifest.json').read_text());proof=json.loads((proofdir/'reviewed-manifest.json').read_text())
 ss=json.loads((source/'summary.json').read_text());targetsfile=base/'budgeted-residual-development-targets-20261021.json'
 if m['window']!=plan['window'] or file_sha(targetsfile)!=m['target_sha256'] or file_sha(raw/'calendar.json')!=m['calendar_sha256']:
  raise ValueError('raw target/calendar provenance changed')
 for key,path in (('raw_manifest_sha256',raw/'manifest.json'),('reviewed_manifest_sha256',proofdir/'reviewed-manifest.json'),('target_sha256',targetsfile)):
  if ss[key]!=file_sha(path):raise ValueError('source compilation differs from replay inputs')
 for name,h in ss['artifact_sha256'].items():
  if Path(name).name!=name or file_sha(source/name)!=h:raise ValueError('compiled event artifact changed')
 for d in proof['documents']:
  if Path(d['file']).name!=d['file'] or d['day']>'2025-12-31' or file_sha(proofdir/d['file'])!=d['sha256']:
   raise ValueError('reviewed primary source changed')
 sessions=json.loads((raw/'calendar.json').read_text())['sessions']
 if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=plan['window']:
  raise ValueError('explicit complete pre2026 sessions required')
 calendar=TradingCalendar(sessions);packets={}
 for code,h in m['per_code_sha256'].items():
  path=raw/'codes'/(code+'.json')
  if file_sha(path)!=h:raise ValueError('original raw source packet changed')
  v=json.loads(path.read_text())
  if v['instrument']!=code or v['window']!=plan['window'] or [r['date'] for r in v['bars']]!=sessions:
   raise ValueError('raw source security/date identity changed')
  packets[code]=v
 validate_source_coverage(packets)
 targets=json.loads(targetsfile.read_text())
 if len(targets)!=24 or {c for t in targets.values() for c in t['weights']}!=set(packets) or len(packets)!=210:
  raise ValueError('complete frozen24target/210source universe required')
 events,receipts=compile_distribution_events(packets,proof,calendar)
 if clean([asdict(e) for e in events])!=json.loads((source/'derived_events.json').read_text()) or list(receipts)!=json.loads((source/'event_source_receipts.json').read_text()):
  raise ValueError('source compilation not reproduced')
 bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()}
 zero_ids={r['event_id'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']}
 if len(zero_ids)!=3:raise ValueError('original unverified-tax scope changed')
 if plan['par_registry'] not in plan['public_evidence_sha256']:
  raise ValueError('par registry must be bound to frozen public evidence')
 registry=json.loads((repo/plan['par_registry']).read_text())
 basis=load_capital_income_basis(registry,base,events)
 if set(basis)!={plan['scenario_event_id']} or not set(basis)<=zero_ids:
  raise ValueError('frozen single event scenario scope changed')
 # Both original prefixes must reproduce BEFORE either complete scenario outcome.
 cutoff=date.fromisoformat(plan['prefix_checkpoint'])
 prefix_calendar=TradingCalendar([d for d in sessions if d<cutoff.isoformat()])
 controls={}
 for bps in plan['extra_cost_bps']:
  accounts=[];evidence=[]
  def prefix_factory(cal,cash,distributions,**kw):
   # Full account calendar preserves original future claim-availability dates;
   # the replay itself still stops on the prior explicit exchange session.
   account=CapitalIncomeStressAccount(calendar,cash,distributions,capital_income_basis=basis,
       broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
   accounts.append(account);return account
  simulate_budgeted_fixed_targets(prefix_calendar,bars,events,targets,plan['initial_CNY'],lifecycles={},account_factory=prefix_factory)
  verify_prefix_state(accounts[0],cutoff,plan['original_failed_prefix_sha256'][str(bps)],evidence)
  controls[str(bps)]=evidence[0]
  print('original prefix reproduced',bps,'bp',flush=True)
 out.mkdir(parents=True);results={}
 (out/'both_original_prefix_controls.json').write_text(json.dumps(controls,indent=2)+'\n')
 for bps in plan['extra_cost_bps']:
  folder=out/str(bps);folder.mkdir();holders=[];prefix=[]
  original=prefix_checked_factory(bps,basis,date.fromisoformat(plan['prefix_checkpoint']),
      plan['original_failed_prefix_sha256'][str(bps)],prefix)
  def factory(cal,cash,distributions,**kw):
   account=original(cal,cash,distributions,**kw);holders.append(account);return account
  print('capital-income counterfactual development',bps,'bp',flush=True)
  try:
   case=simulate_budgeted_fixed_targets(calendar,bars,events,targets,plan['initial_CNY'],lifecycles={},account_factory=factory)
   if len(case['intents'])!=24 or len(prefix)!=1:raise ValueError('complete24monthly decisions and original prefix required')
   record={r['event_id']:r['quantity'] for r in case['corporate_ledger'] if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id'] in zero_ids}
   ex={r['event_id']:r['registered_quantity'] for r in case['corporate_ledger'] if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id'] in zero_ids}
   remaining=zero_ids-set(basis)
   if (set(record)!=zero_ids or set(ex)!=zero_ids or any(record[k] or ex[k] for k in remaining)
       or record[plan['scenario_event_id']]!=1100 or ex[plan['scenario_event_id']]!=1100):
    raise ValueError('actual unknown-capital entitlements differ from fixed scope')
   case['capital_stress_ledger']=holders[0].capital_stress_ledger
   if len(case['capital_stress_ledger'])!=1:raise ValueError('exactly one counterfactual capital-income entry required')
   artifacts=write_case(folder,case)
   for name,value in (('capital_stress_ledger.json',case['capital_stress_ledger']),('original_prefix_receipt.json',prefix)):
    (folder/name).write_text(json.dumps(clean(value),indent=2)+'\n');artifacts[name]=file_sha(folder/name)
   days=[r for r in case['days'] if r['day']>='2024-01-02']
   exposure=float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100)
   r={'status':'COUNTERFACTUAL_COMPLETE_UNAUDITED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_VOLUME',
      **summarize_case(case,plan['initial_CNY']),'average_exposure_pct':exposure,
      'unknown_tax_entitlements':{'record':record,'ex':ex},'original_prefix_receipt':prefix,
      'capital_stress_ledger':clean(case['capital_stress_ledger']),'artifact_sha256':artifacts}
  except (ValueError,KeyError,ArithmeticError) as exc:
   r={'status':'INVALID_COUNTERFACTUAL_ACCOUNT_OR_SOURCE','error_type':type(exc).__name__,'error':str(exc)}
   if holders:(folder/'failed_account_state.json').write_bytes(account_state_bytes(holders[0]))
   (folder/'error.json').write_text(json.dumps(r,indent=2)+'\n');r['failure_artifact_sha256']={f.name:file_sha(f) for f in folder.iterdir()}
  results[str(bps)]=r;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
 summary={'status':'COUNTERFACTUAL_FULL_CAPITAL_INCOME_TAX_STRESS','plan_sha256':a.expected_plan_sha256,
   'method_code_sha256':plan['method_code_sha256'],'both_original_prefix_controls':controls,'results_by_extra_bps':results,'reference_CNY':'1000000','reference_extra_bps':40,
   'raw_daily_proxy_development_gate_passes':False,'raw_source_admitted_for_account_replay':False,
   'actual_tax_exemption_certified':False,'actual_tax_settlement_reproduced':False,'actual_net_return_lower_bound':False,
   'source_evidence_level':'CONDITIONAL_COUNTERFACTUAL_DAILY_OPEN_PROXY_ONLY','minute_execution_admitted':False,
   'historical_arrival_certified':False,'queue_and_impact_calibrated':False,'new_2026_queries':False,
   'candidate_promoted':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('counterfactual complete; original source gate unchanged',flush=True)
 return 0


if __name__=='__main__':raise SystemExit(main())
