"""Fixed composite physical-share daily proxy; two profiles and no2026 outcomes."""
import argparse,json,math
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts.compile_value_momentum_pre2026_sources import load_inputs,build_projection,RAW,PRIMARY,TARGET,COMPILED
from scripts.fundamental_query_journal import file_sha
from scripts.replay_budgeted_stock_distribution_targets import simulate_budgeted_fixed_targets
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from scripts.run_low_risk_feedback_cost_stress import write_case
from stock_rsi.data import digest
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount


def main(argv=None):
 parser=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):parser.add_argument('--'+n,required=True)
 parser.add_argument('--source-preflight-only',action='store_true');a=parser.parse_args(argv)
 base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('raw diagnostic output already exists')
 plan,calendar,packets,targets,docs,content=load_inputs(base,repo,a.plan,a.expected_plan_sha256)
 before={c:digest(v) for c,v in packets.items()}
 proof,events,receipts,anchor=build_projection(base,calendar,packets,docs,content)
 source=base/COMPILED;ss=json.loads((source/'summary.json').read_text())
 if (ss['plan_sha256']!=a.expected_plan_sha256 or ss['raw_manifest_sha256']!=file_sha(base/RAW/'manifest.json')
     or ss['primary_capture_manifest_sha256']!=file_sha(base/PRIMARY/'manifest.json')
     or ss['target_sha256']!=file_sha(base/TARGET) or ss['original_packet_digests']!=before):
  raise ValueError('compiled projection differs from original authenticated inputs')
 expected={'reviewed-manifest.json':proof,'derived_events.json':clean([asdict(e) for e in events]),
  'event_source_receipts.json':list(receipts),'listing_anchor_receipt.json':anchor,'lifecycles.json':proof['lifecycles']}
 if set(ss['artifact_sha256'])!=set(expected):raise ValueError('complete source projection artifact identities required')
 for name,v in expected.items():
  if file_sha(source/name)!=ss['artifact_sha256'][name] or json.loads((source/name).read_text())!=v:
   raise ValueError('independently retained source projection not reproduced')
 if before!={c:digest(v) for c,v in packets.items()}:raise ValueError('source projection mutated original packet')
 if a.source_preflight_only:
  print('255 events,60primary-bound absent sessions,24targets; no output/return/network',flush=True);return 0
 bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()}
 out.mkdir(parents=True);results={}
 for bps in plan['extra_cost_bps']:
  folder=out/str(bps);folder.mkdir();holders=[]
  def factory(cal,cash,distributions,**kw):
   account=StockDistributionAccount(cal,cash,distributions,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
   holders.append(account);return account
  print('composite raw daily development',bps,'bp',flush=True)
  try:
   case=simulate_budgeted_fixed_targets(calendar,bars,events,targets,plan['initial_CNY'],
    lifecycles=proof['lifecycles'],account_factory=factory,policy_id='szse_value_momentum_equal')
   if len(case['intents'])!=24:raise ValueError('complete24 monthly decisions required')
   missing=case['lifecycle_source_audit']
   if len(missing)!=60 or any(r['instrument']!='SZ001389' or r['reason']!='BEFORE_PRIMARY_LISTING_BOUNDARY'
      or r['original_row_present'] is not False or r['synthetic_price_created'] is not False for r in missing):
    raise ValueError('only original60 primary-bound unrequired prelisting sessions allowed')
   artifacts=write_case(folder,case)
   days=[r for r in case['days'] if r['day']>='2024-01-02']
   exposure=float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100)
   r={'status':'DAILY_PROXY_ACCOUNT_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_VOLUME',
    **summarize_case(case,plan['initial_CNY']),'average_exposure_pct':exposure,
    'verified_no_required_premarket_listing_state':True,'primary_bound_absent_sessions':len(missing),
    'artifact_sha256':artifacts}
  except (ValueError,KeyError,ArithmeticError) as exc:
   r={'status':'INVALID_ACCOUNT_OR_SOURCE','error_type':type(exc).__name__,'error':str(exc)}
   if holders:
    acct=holders[0]
    state=clean({'last_account_clock':acct._last_clock,'cash':acct.broker.cash,'positions':acct.broker.positions,
     'orders':acct.broker.orders,'fills':acct.broker.fills,'owned_shares':acct.owned_quantities(),
     'corporate_ledger':acct.corporate_ledger,'cash_claims':acct.cash_claims,'stock_claims':acct.stock_claims})
    (folder/'failed_account_state.json').write_text(json.dumps(state,indent=2)+'\n')
   (folder/'error.json').write_text(json.dumps(r,indent=2)+'\n')
   r['failure_artifact_sha256']={f.name:file_sha(f) for f in folder.iterdir()}
  results[str(bps)]=r;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
 reference=results['40'];values=[reference.get(k,float('nan')) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
 passes=(reference['status']=='DAILY_PROXY_ACCOUNT_RECONCILED'
  and reference.get('verified_no_required_premarket_listing_state') is True
  and all(math.isfinite(v) for v in values) and min(values[:2])>0 and values[2]>=90)
 summary={'status':'FIXED_COMPOSITE_RAW_DAILY_DEVELOPMENT_COMPLETE','plan_sha256':a.expected_plan_sha256,
  'method_code_sha256':plan['method_code_sha256'],'source_projection_summary_sha256':file_sha(source/'summary.json'),
  'results_by_extra_bps':results,'reference_CNY':'1000000','reference_extra_bps':40,
  'raw_daily_proxy_development_gate_passes':passes,
  'reference_gate':'40bp composite2024>0 and2025>0 and meanexposure>=90 and original source/account checks',
  'source_evidence_level':'RECONSTRUCTED_RAW_SHARE_DAILY_OPEN_PROXY_ONLY','minute_execution_admitted':False,
  'historical_arrival_certified':False,'strict_statutory_tax_certification':False,'tax_model':'FIXED20PCT_CASH_STRESS_NOT_FIFO',
  'inherited_capital_tax_inferences':4,'queue_and_impact_calibrated':False,'new_2026_market_queries':False,
  'candidate_promoted':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('composite raw daily development complete; gate',passes,flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
