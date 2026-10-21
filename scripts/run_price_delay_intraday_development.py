"""Frozen price-delay, six pre2026 execution profiles, original fixed integer allocator."""
import argparse,json,math
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts import admit_price_delay_minutes_pre2026 as admission
from scripts import run_price_delay_raw_pre2026 as raw
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
RAW="price-delay-raw-dev-20261021"
TARGET="price-delay-pre2026-formations-20261021/targets.json"
COMPILED="price-delay-account-source-events-20261021"
RAW_METHODS=raw.METHOD_FILES
from scripts.fundamental_query_journal import file_sha
from scripts.replay_ordinary_stock_distribution_targets import simulate_fixed_targets
from scripts import prepare_price_delay_ordinary_scope_pre2026 as scope_source
from scripts.run_low_risk_intraday_replay import write_case
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

PARTICIPATION=(100,500,1000);EXTRA_BPS=(20,40);CAPITAL='1000000'
ADMITTED='price-delay-ordinary-source-scope-20261021'
RAW_PLAN='experiments/qlib/price-delay-raw-daily-plan.json'
ADMISSION_PLAN='experiments/qlib/price-delay-ordinary-source-scope-plan.json'
AUDIT='experiments/qlib/price-delay-ordinary-source-scope-independent-audit.json'
METHOD_FILES=tuple(dict.fromkeys((*RAW_METHODS,*scope_source.METHOD_FILES,
 'scripts/run_price_delay_intraday_development.py','scripts/run_low_beta60_intraday_development.py',
 'scripts/run_low_risk_intraday_replay.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
 'scripts/replay_ordinary_stock_distribution_targets.py','src/stock_rsi/ordinary_source_scope.py',
 'src/stock_rsi/intraday_broker.py','src/stock_rsi/intraday_tape.py')))
PUBLIC_FILES=(RAW_PLAN,ADMISSION_PLAN,AUDIT,
 'experiments/qlib/price-delay-ordinary-source-scope-summary.json',
 'experiments/qlib/price-delay-ordinary-source-scope-verification.json',
 'experiments/qlib/price-delay-raw-daily-independent-ledger-audit.json',
 'docs/research/price-delay-intraday-plan-2026-10-21.md')
LOCAL_FILES=(ADMITTED+'/summary.json',ADMITTED+'/scope.json',COMPILED+'/summary.json',
 'price-delay-raw-daily-pre2026-20261021/summary.json',admission.CAPTURE+'/manifest.json')

def read(p):return json.loads(Path(p).read_text())


def validate_profile(plan):
 required={'allocator':'plan_integer_targets','account_guard':'ordinary_source_rows_on',
  'original_strict_2502_admission_remains_failed':True,'network_calls_permitted':0,
  'new_2026_market_values_queried':False,'investment_rule_changed':False,'candidate_budget':1}
 if (any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in required.items())
     or plan['status']!='FROZEN_PRICE_DELAY_PRE2026_INTRADAY_DEVELOPMENT'
     or plan['candidate']!='price_delay_d1' or plan['candidate_budget']!=1
     or plan['participation_bps']!=list(PARTICIPATION) or plan['extra_cost_bps']!=list(EXTRA_BPS)
     or plan.get('output_relative')!='price-delay-intraday-pre2026-20261021'
     or plan['initial_CNY']!=CAPITAL or plan['window']!=['2023-12-29','2025-12-31']
     or set(plan['method_code_sha256'])!=set(METHOD_FILES)
     or set(plan['public_evidence_sha256'])!=set(PUBLIC_FILES)
     or set(plan['local_source_sha256'])!=set(LOCAL_FILES)):
  raise ValueError('one frozen price-delay and all six pre2026 execution profiles required')


def confirmation_passes(results):
 if set(results)!={f'{p}/{c}' for p in PARTICIPATION for c in EXTRA_BPS}:return False
 for p in PARTICIPATION:
  r=results[f'{p}/40'];values=[r.get(k) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
  if (r.get('status')!='NESTED_EXECUTION_ACCOUNT_RECONCILED' or r.get('monthly_decisions')!=24
      or r.get('account_sessions')!=485 or r.get('unused_ST_intervals_verified')!=241 or r.get('ordinary_dependency_guard_passes') is not True
      or r.get('whole_day_volume_violations')!=0 or r.get('noncash_entitlements_supported') is not True
      or r.get('all_children_within_1million_shares') is not True
      or not isinstance(r.get('unproved_noncash_record_ownership'),list)
      or len(r['unproved_noncash_record_ownership'])!=1
      or not isinstance(r['unproved_noncash_record_ownership'][0],dict)
      or type(r['unproved_noncash_record_ownership'][0].get('quantity')) is not int
      or r['unproved_noncash_record_ownership'][0].get('quantity')!=0
      or not all(type(v) in (int,float) and math.isfinite(v) for v in values)
      or min(values[:2])<=0 or values[2]<90):return False
 return True


def load_inputs(base,repo,plan):
 validate_profile(plan)
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(parent/n)!=h:raise ValueError('frozen price-delay intraday input changed: '+n)
 # Reuse the frozen raw runner's complete source-only authentication. Its
 # output remains absent; this branch computes neither an account nor ROI.
 raw.main(['--source-root',str(base),'--plan',str(repo/RAW_PLAN),
  '--expected-plan-sha256',plan['raw_daily_plan_sha256'],
  '--output-dir',str(base/plan['output_relative']),'--source-preflight-only'])
 calendar=TradingCalendar(read(base/RAW/'calendar.json')['sessions'])
 rm=read(base/RAW/'manifest.json')
 packets={code:read(base/RAW/'codes'/(code+'.json')) for code in rm['per_code_sha256']}
 targets=read(base/TARGET)['price_delay_d1']
 proof=read(base/COMPILED/'effective_proofs.json')
 events,receipts=compile_distribution_events_v2(packets,proof,calendar)
 if len(events)!=378 or len(targets)!=24 or len(packets)!=151:
  raise ValueError('same378events/24targets/151names required')
 daily_dir=base/'price-delay-raw-daily-pre2026-20261021';daily=read(daily_dir/'summary.json')
 da=read(repo/'experiments/qlib/price-delay-raw-daily-independent-ledger-audit.json')
 if (daily['raw_daily_proxy_development_gate_passes'] is not True
     or da['daily_proxy_development_gate_passes_independently'] is not True
     or da['summary_sha256']!=file_sha(daily_dir/'summary.json')):raise ValueError('passed original daily account missing')
 for cost,r in daily['results_by_extra_bps'].items():
  for n,h in r['artifact_sha256'].items():
   if Path(n).name!=n or file_sha(daily_dir/cost/n)!=h:raise ValueError('prior daily account evidence changed')
 ad=base/ADMITTED;am=read(ad/'summary.json');audit=read(repo/AUDIT)
 sp=read(repo/ADMISSION_PLAN)
 scope_source.validate_plan(sp,base,ad)
 observed_scope=scope_source.authenticate_sources(base,repo,sp)
 if (am['status']!='ORDINARY_SOURCE_SCOPE_PREPARED_ACCOUNT_PROOF_REQUIRED'
     or am['plan_sha256']!=file_sha(repo/ADMISSION_PLAN)
     or am['scope_sha256']!=file_sha(ad/'scope.json')
     or observed_scope!=read(ad/'scope.json')
     or am['ordinary_packets_content_verified']!=2490 or am['rejected_packets_retained']!=12
     or am['nonordinary_daily_intervals']!=241 or am['account_dependency_guard_required'] is not True
     or am['all_account_dependencies_ordinary_proven'] is not False
     or am['admitted_for_unconditional_execution'] is not False
     or audit['source_summary_sha256']!=file_sha(ad/'summary.json')
     or audit['source_scope_sha256']!=file_sha(ad/'scope.json')
     or audit['ordinary_scope_reconstructed'] is not True
     or audit['ordinary_samples_reconstructed']!=2490
     or audit['nonordinary_intervals_reconstructed']!=241 or audit['imports_project_code'] is not False
     or not raw.valid_negative_controls(audit['semantic_negative_controls_rejected'])
     or audit['audit_code_sha256']!=file_sha(repo/'experiments/qlib/audit_sources/2026-10-21-price-delay-ordinary-source-scope-audit.py')):
  raise ValueError('independent ordinary source scope and retained failed admission required')
 bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()}
 bank=scope_source.OrdinaryScopeTapeBank(base/admission.CAPTURE,bars,observed_scope)
 if len(bank.index)!=2490:raise ValueError('ordinary-only2490 tape index required')
 return calendar,bars,events,receipts,targets,{},bank,observed_scope['nonordinary_source_intervals']



def run_profiles(out,calendar,bars,events,targets,lifecycles,bank,nonordinary_intervals):
 out=Path(out)
 if out.exists():raise ValueError('preserve previous complete or partial price-delay intraday run')
 out.mkdir(parents=True);results={};byid={e.event_id:e for e in events}
 for participation in PARTICIPATION:
  for cost in EXTRA_BPS:
   label=f'{participation}/{cost}';folder=out/label;folder.mkdir(parents=True);holders=[]
   print('price-delay intraday pre2026',label,'CNY',CAPITAL,flush=True)
   def factory(cal,cash,distributions,**kwargs):
    broker=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=cost,tape_provider=bank)
    account=StockDistributionAccount(cal,cash,distributions,broker_factory=broker,**kwargs);holders.append(account);return account
   try:
    case=simulate_fixed_targets(calendar,bars,events,targets,CAPITAL,lifecycles=lifecycles,account_factory=factory,policy_id='price_delay_d1')
    days=[r for r in case['days'] if r['day']>='2024-01-02'];missing=case['lifecycle_source_audit']
    if len(days)!=485 or len(case['days'])!=486 or len(case['intents'])!=24:raise ValueError('complete continuous account required')
    expected_unused=[{'instrument':r['instrument'],'session':r['day'],
      'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,
      'source_isST':'1','required_by_account':False,'synthetic_price_created':False}
      for r in nonordinary_intervals]
    if len(expected_unused)!=241 or missing!=expected_unused:
     raise ValueError('every original ST interval requires actual absent account dependency proof')
    unproved=raw.verify_unproved_record_ownership(events,case['corporate_ledger'])
    for row in case['corporate_ledger']:
     if row['kind']!='EX_DATE_ENTITLEMENT' or not row['registered_quantity']:continue
     e=byid[row['event_id']]
     if e.capital_per_share and not e.capital_tax_exempt_verified or e.stock_per_share and not e.stock_tax_basis_verified:
      raise ValueError('owned noncash entitlement unsupported')
    case['parent_instructions']=case.pop('orders');case['orders']=holders[0].broker.child_orders
    (folder/'source_scope_audit.json').write_text(json.dumps(clean(missing),indent=2)+'\n')
    artifacts=write_case(folder,case)
    r={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_CAPACITY',
     **summarize_case(case,CAPITAL),'account_sessions':len(days),'unused_ST_intervals_verified':241,'ordinary_dependency_guard_passes':True,'unproved_noncash_record_ownership':clean(unproved),
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
 plan=read(a.plan)
 if out.resolve()!=(base/plan['output_relative']).resolve():raise ValueError('frozen account output path required')
 calendar,bars,events,receipts,targets,lifecycles,bank,nonordinary_intervals=load_inputs(base,repo,plan)
 if a.preflight_only:print('source-only intraday preflight passed; no account/ROI/network',flush=True);return 0
 results=run_profiles(out,calendar,bars,events,targets,lifecycles,bank,nonordinary_intervals)
 (out/'derived_events.json').write_text(json.dumps(clean([asdict(e) for e in events]),indent=2)+'\n')
 (out/'event_source_receipts.json').write_text(json.dumps(list(receipts),indent=2)+'\n')
 summary={'status':'FIXED_PRICE_DELAY_PRE2026_INTRADAY_DEVELOPMENT_COMPLETE','candidate':'price_delay_d1',
  'phase':'dev','window':['2023-12-29','2025-12-31'],'plan_sha256':a.expected_plan_sha256,
  'method_code_sha256':plan['method_code_sha256'],'results_by_profile':results,
  'raw_development_confirmation_passes':confirmation_passes(results),
  'tape_accessed_pairs':len(bank.accessed),'source_prefix_pairs':len(bank.index),'rejected_ST_packets_retained':12,
  'strict_original_2502_admission_stays_failed':True,'original_fixed_integer_allocator_preserved':True,
  'derived_events_sha256':file_sha(out/'derived_events.json'),'event_source_receipts_sha256':file_sha(out/'event_source_receipts.json'),
  'all_profiles_independently_audited':False,'historical_arrival_verified':False,'full_corporate_actions_certified':False,
  'queue_and_impact_calibrated':False,'actual_FIFO_tax_liability_verified':False,'strict_statutory_tax_certification':False,
  'tax_model':'FIXED20PCT_CASH_STRESS_NOT_FIFO','inherited_conditional_capital_tax_inferences':1,
  '2026_strategy_returns_queried':False,'candidate_promoted':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('price-delay intraday development complete; all three40bp confirmation',confirmation_passes(results),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
