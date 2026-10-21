"""Frozen composite, six pre2026 execution profiles, unchanged budgeted allocator."""
import argparse,json,math
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts import admit_value_momentum_minutes_pre2026 as admission
from scripts.compile_value_momentum_pre2026_sources import load_inputs as raw_inputs,build_projection,RAW,TARGET,COMPILED,METHOD_FILES as RAW_METHODS
from scripts.fundamental_query_journal import file_sha
from scripts.replay_budgeted_stock_distribution_targets import simulate_budgeted_fixed_targets
from scripts.run_low_beta60_intraday_development import CompletePrefixTapeBank
from scripts.run_low_risk_intraday_replay import write_case
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from stock_rsi.data import digest
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

PARTICIPATION=(100,500,1000);EXTRA_BPS=(20,40);CAPITAL='1000000'
ADMITTED='szse-value-momentum-minute-admission-20261021'
RAW_PLAN='experiments/qlib/szse-value-momentum-raw-daily-plan.json'
ADMISSION_PLAN='experiments/qlib/szse-value-momentum-minute-admission-plan.json'
AUDIT='experiments/qlib/szse-value-momentum-minute-admission-independent-audit.json'
METHOD_FILES=tuple(dict.fromkeys((*RAW_METHODS,*admission.METHOD_FILES,
 'scripts/run_value_momentum_intraday_development.py','scripts/run_low_beta60_intraday_development.py',
 'scripts/run_low_risk_intraday_replay.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
 'src/stock_rsi/intraday_broker.py','src/stock_rsi/intraday_tape.py')))
PUBLIC_FILES=(RAW_PLAN,ADMISSION_PLAN,AUDIT,
 'experiments/qlib/szse-value-momentum-minute-admission-summary.json',
 'experiments/qlib/szse-value-momentum-minute-admission-verification.json',
 'experiments/qlib/szse-value-momentum-raw-daily-ledger-audit.json',
 'docs/research/szse-value-momentum-intraday-plan-2026-10-21.md')
LOCAL_FILES=(ADMITTED+'/summary.json',ADMITTED+'/details.json',COMPILED+'/summary.json',
 'szse-value-momentum-raw-daily-dev-20261021/summary.json',admission.CAPTURE+'/manifest.json')

def read(p):return json.loads(Path(p).read_text())


def validate_profile(plan):
 if (plan['status']!='FROZEN_COMPOSITE_PRE2026_INTRADAY_DEVELOPMENT'
     or plan['candidate']!='szse_value_momentum_equal' or plan['candidate_budget']!=1
     or plan['participation_bps']!=list(PARTICIPATION) or plan['extra_cost_bps']!=list(EXTRA_BPS)
     or plan['initial_CNY']!=CAPITAL or plan['window']!=['2023-12-29','2025-12-31']
     or set(plan['method_code_sha256'])!=set(METHOD_FILES)
     or set(plan['public_evidence_sha256'])!=set(PUBLIC_FILES)
     or set(plan['local_source_sha256'])!=set(LOCAL_FILES)):
  raise ValueError('one frozen composite and all six pre2026 execution profiles required')


def confirmation_passes(results):
 if set(results)!={f'{p}/{c}' for p in PARTICIPATION for c in EXTRA_BPS}:return False
 for p in PARTICIPATION:
  r=results[f'{p}/40'];values=[r.get(k) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
  if (r.get('status')!='NESTED_EXECUTION_ACCOUNT_RECONCILED' or r.get('monthly_decisions')!=24
      or r.get('account_sessions')!=485 or r.get('primary_bound_absent_sessions')!=60
      or r.get('whole_day_volume_violations')!=0 or r.get('noncash_entitlements_supported') is not True
      or r.get('all_children_within_1million_shares') is not True
      or not all(type(v) in (int,float) and math.isfinite(v) for v in values)
      or min(values[:2])<=0 or values[2]<90):return False
 return True


def load_inputs(base,repo,plan):
 validate_profile(plan)
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(parent/n)!=h:raise ValueError('frozen composite intraday input changed: '+n)
 rp,calendar,packets,targets,docs,content=raw_inputs(base,repo,repo/RAW_PLAN,plan['raw_daily_plan_sha256'])
 before={c:digest(v) for c,v in packets.items()}
 proof,events,receipts,anchor=build_projection(base,calendar,packets,docs,content)
 source=base/COMPILED;ss=read(source/'summary.json')
 expected={'reviewed-manifest.json':proof,'derived_events.json':clean([asdict(e) for e in events]),
  'event_source_receipts.json':list(receipts),'listing_anchor_receipt.json':anchor,'lifecycles.json':proof['lifecycles']}
 if (ss['plan_sha256']!=plan['raw_daily_plan_sha256'] or ss['raw_manifest_sha256']!=file_sha(base/RAW/'manifest.json')
     or ss['target_sha256']!=file_sha(base/TARGET) or ss['original_packet_digests']!=before
     or set(ss['artifact_sha256'])!=set(expected)):raise ValueError('frozen source projection identity changed')
 for n,v in expected.items():
  if file_sha(source/n)!=ss['artifact_sha256'][n] or read(source/n)!=v:raise ValueError('original255events/primary lifecycle changed')
 if before!={c:digest(v) for c,v in packets.items()}:raise ValueError('source projection modified original packets')
 daily_dir=base/'szse-value-momentum-raw-daily-dev-20261021';daily=read(daily_dir/'summary.json')
 da=read(repo/'experiments/qlib/szse-value-momentum-raw-daily-ledger-audit.json')
 if (daily['raw_daily_proxy_development_gate_passes'] is not True
     or da['raw_daily_proxy_development_gate_passes_independently'] is not True
     or da['summary_sha256']!=file_sha(daily_dir/'summary.json')):raise ValueError('passed original daily account missing')
 for cost,r in daily['results_by_extra_bps'].items():
  for n,h in r['artifact_sha256'].items():
   if Path(n).name!=n or file_sha(daily_dir/cost/n)!=h:raise ValueError('prior daily account evidence changed')
 ad=base/ADMITTED;am=read(ad/'summary.json');audit=read(repo/AUDIT)
 capture=base/admission.CAPTURE;cm=read(capture/'manifest.json')
 if (am['admitted_for_reconstructed_execution'] is not True
     or am['plan_sha256']!=file_sha(repo/ADMISSION_PLAN)
     or am['status_counts']!={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1744}
     or file_sha(ad/'details.json')!=am['details_sha256']
     or am['capture_manifest_sha256']!=file_sha(capture/'manifest.json')
     or audit['admission_summary_sha256']!=file_sha(ad/'summary.json')
     or audit['reconstructed_source_admission_passes'] is not True
     or audit['source_pairs_reconstructed']!=1744 or audit['imports_project_code'] is not False
     or not audit['semantic_negative_controls_rejected'] or not all(audit['semantic_negative_controls_rejected'].values())
     or audit['audit_code_sha256']!=file_sha(repo/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-minute-admission-audit.py')):
  raise ValueError('complete independent minute source admission required')
 request=read(repo/admission.RQ);cp=read(repo/admission.CP)
 admission.authenticate(base,repo,request,cp)
 if not admission.verify_capture_scope(read(capture/'composite-scope.json'),cm,read(capture/'client_cleanup.json'),
  capture_plan_sha256=file_sha(repo/admission.CP),request_sha256=file_sha(repo/admission.RQ),
  manifest_sha256=file_sha(capture/'manifest.json'),cleanup_sha256=file_sha(capture/'client_cleanup.json')):
  raise ValueError('source client cleanup failed')
 admission.verify_journal_bytes(capture,read(repo/admission.AUDIT))
 bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()};bank=CompletePrefixTapeBank(capture,bars)
 if set(bank.index)!={(c,d) for c,d in request['active_requests']}:raise ValueError('complete1744 potential execution prefix required')
 return calendar,bars,events,receipts,targets,proof['lifecycles'],bank


def run_profiles(out,calendar,bars,events,targets,lifecycles,bank):
 out=Path(out)
 if out.exists():raise ValueError('preserve previous complete or partial composite intraday run')
 out.mkdir(parents=True);results={};byid={e.event_id:e for e in events}
 for participation in PARTICIPATION:
  for cost in EXTRA_BPS:
   label=f'{participation}/{cost}';folder=out/label;folder.mkdir(parents=True);holders=[]
   print('composite intraday pre2026',label,'CNY',CAPITAL,flush=True)
   def factory(cal,cash,distributions,**kwargs):
    broker=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=cost,tape_provider=bank)
    account=StockDistributionAccount(cal,cash,distributions,broker_factory=broker,**kwargs);holders.append(account);return account
   try:
    case=simulate_budgeted_fixed_targets(calendar,bars,events,targets,CAPITAL,lifecycles=lifecycles,account_factory=factory,policy_id='szse_value_momentum_equal')
    days=[r for r in case['days'] if r['day']>='2024-01-02'];missing=case['lifecycle_source_audit']
    if len(days)!=485 or len(case['days'])!=486 or len(case['intents'])!=24:raise ValueError('complete continuous account required')
    if len(missing)!=60 or any(r['instrument']!='SZ001389' or r['reason']!='BEFORE_PRIMARY_LISTING_BOUNDARY'
       or r['original_row_present'] is not False or r['synthetic_price_created'] is not False for r in missing):
     raise ValueError('only60 primary-bound unrequired prelisting sessions allowed')
    for row in case['corporate_ledger']:
     if row['kind']!='EX_DATE_ENTITLEMENT' or not row['registered_quantity']:continue
     e=byid[row['event_id']]
     if e.capital_per_share and not e.capital_tax_exempt_verified or e.stock_per_share and not e.stock_tax_basis_verified:
      raise ValueError('owned noncash entitlement unsupported')
    case['parent_instructions']=case.pop('orders');case['orders']=holders[0].broker.child_orders
    artifacts=write_case(folder,case)
    r={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_CAPACITY',
     **summarize_case(case,CAPITAL),'account_sessions':len(days),'primary_bound_absent_sessions':60,
     'average_exposure_pct':float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100),
     'noncash_entitlements_supported':True,'parent_instructions':len(case['parent_instructions']),
     'child_orders':len(case['orders']),'unfilled_parents':sum(p['remaining']>0 for p in case['parent_instructions']),
     'all_children_within_1million_shares':all(0<o['quantity']<=1000000 for o in case['orders']),
     'artifact_sha256':artifacts}
    peak=Decimal(CAPITAL);dd=Decimal(0)
    for row in days:peak=max(peak,row['equity']);dd=min(dd,row['equity']/peak-1)
    r['max_drawdown_pct']=float(dd*100)
   except (ValueError,KeyError,ArithmeticError,OSError) as exc:
    r={'status':'INVALID_SOURCE_OR_ACCOUNT','error_type':type(exc).__name__,'error':str(exc)}
    if holders:
     acc=holders[0];state=clean({'last_account_clock':acc._last_clock,'last_intraday_end':acc.broker._last_end,
      'cash':acc.broker.cash,'positions':acc.broker.positions,'owned_shares':acc.owned_quantities(),
      'parent_instructions':acc.broker.orders,'child_orders':acc.broker.child_orders,'fills':acc.broker.fills,
      'corporate_ledger':acc.corporate_ledger,'entitlements':acc.entitlements,'cash_claims':acc.cash_claims,'stock_claims':acc.stock_claims})
     (folder/'failed_account_state.json').write_text(json.dumps(state,indent=2)+'\n')
    (folder/'error.json').write_text(json.dumps(r,indent=2)+'\n');r['failure_artifact_sha256']={f.name:file_sha(f) for f in sorted(folder.iterdir())}
   results[label]=r;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
 return results


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
 base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('preserve prior intraday development attempt')
 if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen intraday plan changed')
 plan=read(a.plan);calendar,bars,events,receipts,targets,lifecycles,bank=load_inputs(base,repo,plan)
 if a.preflight_only:print('source-only intraday preflight passed; no account/ROI/network',flush=True);return 0
 results=run_profiles(out,calendar,bars,events,targets,lifecycles,bank)
 (out/'derived_events.json').write_text(json.dumps(clean([asdict(e) for e in events]),indent=2)+'\n')
 (out/'event_source_receipts.json').write_text(json.dumps(list(receipts),indent=2)+'\n')
 summary={'status':'FIXED_COMPOSITE_PRE2026_INTRADAY_DEVELOPMENT_COMPLETE','candidate':'szse_value_momentum_equal',
  'phase':'dev','window':['2023-12-29','2025-12-31'],'plan_sha256':a.expected_plan_sha256,
  'method_code_sha256':plan['method_code_sha256'],'results_by_profile':results,
  'raw_development_confirmation_passes':confirmation_passes(results),
  'tape_accessed_pairs':len(bank.accessed),'source_prefix_pairs':len(bank.index),
  'derived_events_sha256':file_sha(out/'derived_events.json'),'event_source_receipts_sha256':file_sha(out/'event_source_receipts.json'),
  'all_profiles_independently_audited':False,'historical_arrival_verified':False,'full_corporate_actions_certified':False,
  'queue_and_impact_calibrated':False,'actual_FIFO_tax_liability_verified':False,'strict_statutory_tax_certification':False,
  'tax_model':'FIXED20PCT_CASH_STRESS_NOT_FIFO','inherited_capital_tax_inferences':4,
  '2026_strategy_returns_queried':False,'candidate_promoted':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('composite intraday development complete; all three40bp confirmation',confirmation_passes(results),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
