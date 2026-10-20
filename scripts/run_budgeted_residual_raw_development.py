"""Frozen two-profile raw daily diagnostic; never minute admission or2026 ROI."""
import argparse,json,math
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
from stock_rsi.stock_distribution_account import StockDistributionAccount

METHOD_FILES=('scripts/run_budgeted_residual_raw_development.py','scripts/replay_budgeted_stock_distribution_targets.py',
 'scripts/replay_stock_distribution_targets.py','src/stock_rsi/budgeted_raw_orders.py','src/stock_rsi/budgeted_lot_orders.py',
 'src/stock_rsi/prior_close_orders.py','src/stock_rsi/distribution_event_compiler.py','src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/broker.py','src/stock_rsi/execution_cost.py','src/stock_rsi/calendar.py',
 'src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py','src/stock_rsi/lifecycle_source_rows.py',
 'scripts/run_low_risk_raw_share_validation.py','scripts/run_low_risk_feedback_cost_stress.py','scripts/fundamental_query_journal.py')


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('raw diagnostic output already exists')
 if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('raw diagnostic plan changed')
 plan=json.loads(Path(a.plan).read_text())
 if (plan['status']!='FROZEN_BEFORE_BUDGETED_RAW_DAILY_DEVELOPMENT_OUTCOMES'
     or plan['initial_CNY']!='1000000' or plan['extra_cost_bps']!=[20,40]
     or plan['window']!=['2023-12-29','2025-12-31']
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
 out.mkdir(parents=True);results={}
 for bps in plan['extra_cost_bps']:
  folder=out/str(bps);folder.mkdir();holders=[]
  def factory(cal,cash,distributions,**kw):
   account=StockDistributionAccount(cal,cash,distributions,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
   holders.append(account);return account
  print('budgeted raw daily development',bps,'bp',flush=True)
  try:
   case=simulate_budgeted_fixed_targets(calendar,bars,events,targets,plan['initial_CNY'],lifecycles={},account_factory=factory)
   if len(case['intents'])!=24:raise ValueError('complete24monthly decisions required')
   record={r['event_id']:r['quantity'] for r in case['corporate_ledger'] if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id'] in zero_ids}
   ex={r['event_id']:r['registered_quantity'] for r in case['corporate_ledger'] if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id'] in zero_ids}
   if set(record)!=zero_ids or set(ex)!=zero_ids or any(record[k] or ex[k] for k in zero_ids):raise ValueError('unverified income has actual record ownership')
   artifacts=write_case(folder,case);days=[r for r in case['days'] if r['day']>='2024-01-02']
   exposure=float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100)
   r={'status':'DAILY_PROXY_ACCOUNT_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_VOLUME',
       **summarize_case(case,plan['initial_CNY']),'average_exposure_pct':exposure,'actual_zero_unverified_entitlements_verified':True,
       'zero_entitlement_receipts':{'record':record,'ex':ex},'artifact_sha256':artifacts}
  except (ValueError,KeyError,ArithmeticError) as exc:
   r={'status':'INVALID_ACCOUNT_OR_SOURCE','error_type':type(exc).__name__,'error':str(exc)}
   if holders:
    acct=holders[0]
    state=clean({'last_account_clock':acct._last_clock,'cash':acct.broker.cash,'positions':acct.broker.positions,
       'orders':acct.broker.orders,'fills':acct.broker.fills,'owned_shares':acct.owned_quantities(),
       'corporate_ledger':acct.corporate_ledger,'cash_claims':acct.cash_claims,'stock_claims':acct.stock_claims})
    (folder/'failed_account_state.json').write_text(json.dumps(state,indent=2)+'\n')
   (folder/'error.json').write_text(json.dumps(r,indent=2)+'\n');r['failure_artifact_sha256']={f.name:file_sha(f) for f in folder.iterdir()}
  results[str(bps)]=r;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
 reference=results['40'];values=[reference.get(k,float('nan')) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
 passes=(reference['status']=='DAILY_PROXY_ACCOUNT_RECONCILED' and reference.get('actual_zero_unverified_entitlements_verified') is True
     and all(math.isfinite(v) for v in values) and min(values[:2])>0 and values[2]>=90)
 summary={'status':'BUDGETED_RAW_DAILY_DEVELOPMENT_DIAGNOSTIC_COMPLETE','plan_sha256':a.expected_plan_sha256,
   'method_code_sha256':plan['method_code_sha256'],'results_by_extra_bps':results,'reference_CNY':'1000000','reference_extra_bps':40,
   'raw_daily_proxy_development_gate_passes':passes,'reference_gate':'2024>0 and2025>0 and averageexposure>=90 and all original source/account checks pass',
   'source_evidence_level':'RECONSTRUCTED_DAILY_OPEN_PROXY_ONLY','minute_execution_admitted':False,'historical_arrival_certified':False,
   'queue_and_impact_calibrated':False,'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('raw daily diagnostic complete; gate',passes,flush=True)
 return 0


if __name__=='__main__':raise SystemExit(main())
