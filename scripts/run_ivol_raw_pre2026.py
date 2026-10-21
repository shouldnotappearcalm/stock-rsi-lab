"""Two frozen continuous pre2026 physical-share daily diagnostics.

Source evidence and lifecycle boundaries are evaluator-only. Failed guards keep
state and partial evidence; annual scoring waits for both complete profiles and
the immutable-input postcheck. No strategy, tax or execution policy is changed.
"""
import argparse
import json
import math
import traceback
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.replay_ordinary_budgeted_stock_distribution_targets import simulate_ordinary_budgeted_fixed_targets
from scripts.run_low_risk_raw_share_validation import clean, validate_source_coverage
from scripts.run_low_risk_feedback_cost_stress import write_case
from stock_rsi.primary_event_components import compile_primary_event_components
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

RAW='low-market-residual-vol1m-raw-pre2026-20261021'
DEVELOPMENT='low-market-residual-vol1m-budgeted-pre2026-development-20261021'
SOURCE='low-market-residual-vol1m-account-source-events-pre2026-20261021'
OUTPUT='low-market-residual-vol1m-raw-development-pre2026-20261021'
POLICY='low_market_residual_vol_1m_budgeted'
PROTOCOL='docs/research/low-market-residual-vol1m-raw-development-protocol-2026-10-21.md'
SOURCE_REQUEST='experiments/qlib/low-market-residual-vol1m-event-source-request.json'
SOURCE_AUDIT='experiments/qlib/low-market-residual-vol1m-event-source-independent-audit.json'
SOURCE_ARTIFACTS=('effective_proofs.json','derived_events.json','event_source_receipts.json',
                  'lifecycles.json','initial_listing_classification.json','coverage_validation.json')
LOCAL_FILES=(RAW+'/manifest.json',RAW+'/calendar.json',DEVELOPMENT+'/targets.json',
             DEVELOPMENT+'/summary.json',SOURCE+'/summary.json',*(SOURCE+'/'+n for n in SOURCE_ARTIFACTS))
PUBLIC_FILES=(SOURCE_REQUEST,SOURCE_AUDIT,
    'experiments/qlib/low-market-residual-vol1m-raw-source-independent-audit.json',
    'experiments/qlib/low-market-residual-vol1m-budgeted-development-independent-audit.json')
METHOD_FILES=('scripts/run_ivol_raw_pre2026.py','scripts/prepare_ivol_account_sources_pre2026.py',
    'scripts/replay_ordinary_budgeted_stock_distribution_targets.py','scripts/run_low_risk_raw_share_validation.py',
    'scripts/run_low_risk_feedback_cost_stress.py','scripts/fundamental_query_journal.py',
    'scripts/capture_low_risk_raw_account_data.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
    'scripts/prepare_qlib_master_market_pre2026.py','src/stock_rsi/primary_event_components.py',
    'src/stock_rsi/distribution_event_compiler_v2.py','src/stock_rsi/distribution_event_compiler.py',
    'src/stock_rsi/budgeted_raw_orders.py','src/stock_rsi/ordinary_source_scope.py','src/stock_rsi/lifecycle_source_rows.py',
    'src/stock_rsi/stock_distribution_account.py','src/stock_rsi/raw_share_account.py',
    'src/stock_rsi/execution_cost.py','src/stock_rsi/broker.py','src/stock_rsi/calendar.py',
    'src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py')


def read(path):return json.loads(Path(path).read_bytes())


def write(path,value):
    Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def safe(root,name):
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('input path escaped bound root')
    path=(Path(root)/relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):raise ValueError('input symlink escaped bound root')
    return path


def verify_inputs(mapping):
    for name,h in mapping.items():
        if not Path(name).is_file() or file_sha(name)!=h:raise ValueError('immutable input changed: '+name)


def valid_negative_controls(controls):
    return isinstance(controls,dict) and len(controls)>=4 and all(v is True for v in controls.values())


def validate_plan(plan):
    fixed={'status':'FROZEN_IVOL_RAW_PRE2026_DAILY_ENGINEERING_PLAN','initial_CNY':'1000000',
        'extra_cost_bps':[20,40],'reference_extra_bps':40,'window':['2023-12-29','2025-12-31'],
        'policy_id':POLICY,'allocator':'plan_budgeted_raw_targets','source_guard':'ordinary_source_rows_on',
        'tax_reserve_rate':'0.2','minimum_average_exposure_pct':90,'candidate_budget':1,'profile_budget':2,
        'output_relative':OUTPUT,'protocol_file':PROTOCOL,'source_request_file':SOURCE_REQUEST,
        'new_2026_queries_allowed':False,'investment_rule_changed':False}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in fixed.items()):
        raise ValueError('fixed raw account protocol/profiles changed')
    if any(type(v) is not int for v in plan['extra_cost_bps']):raise ValueError('integer cost profiles required')
    for field,names in (('method_code_sha256',METHOD_FILES),('public_evidence_sha256',PUBLIC_FILES),('local_source_sha256',LOCAL_FILES)):
        if set(plan[field])!=set(names):raise ValueError('exact frozen method/public/local source maps required')


def load_inputs(base,repo,plan_path,expected_sha):
    from scripts import prepare_ivol_account_sources_pre2026 as source_api
    base,repo,plan_path=Path(base).resolve(),Path(repo).resolve(),Path(plan_path).resolve()
    if file_sha(plan_path)!=expected_sha:raise ValueError('external raw plan checksum changed')
    plan=read(plan_path);validate_plan(plan);known={str(plan_path):expected_sha}
    def bind(path,h):
        if file_sha(path)!=h:raise ValueError('frozen raw input changed: '+str(path))
        known[str(path)]=h
    for field,root in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for n,h in plan[field].items():bind(safe(root,n),h)
    bind(repo/PROTOCOL,plan['protocol_sha256'])
    source_sha=plan['public_evidence_sha256'][SOURCE_REQUEST]
    ctx=source_api.load_inputs(base,repo,repo/SOURCE_REQUEST,source_sha)
    for n,h in ctx['input_sha256'].items():bind(Path(n).resolve(),h)
    directory=base/SOURCE;summary=read(directory/'summary.json');audit=read(repo/SOURCE_AUDIT)
    if (summary['projection_complete'] is not True or summary['error'] is not None
            or summary['request_sha256']!=source_sha or summary['raw_manifest_sha256']!=ctx['raw_manifest_sha256']
            or summary['target_sha256']!=ctx['target_sha256'] or summary['old42_financial_sha256']!=ctx['old42_financial_sha256']
            or set(summary['artifact_sha256'])!=set(SOURCE_ARTIFACTS)):
        raise ValueError('complete frozen source projection not linked to actual inputs')
    source_hashes={'summary.json':file_sha(directory/'summary.json'),**summary['artifact_sha256']}
    if (audit['status']!='PASS_INDEPENDENT_PRE2026_EVENT_SOURCE_AUDIT'
            or audit['source_summary_sha256']!=source_hashes['summary.json']
            or audit['source_plan_sha256']!=source_sha or audit['source_artifact_sha256']!=source_hashes
            or audit['old42_financial_sha256']!=ctx['old42_financial_sha256']
            or audit['critical_or_important_findings']
            or not valid_negative_controls(audit['semantic_negative_controls_rejected'])):
        raise ValueError('independent source audit identity/math/negative evidence incomplete')
    for field in ('all862_events_independently_reconstructed','all_source_receipts_independently_reconstructed',
                  'coverage_independently_reconstructed','six_unknown_tax_states_preserved'):
        if audit[field] is not True:raise ValueError('required independent source evidence missing')
    for field in ('imports_project_code','production_compiler_called','account_replay_admitted','portfolio_returns_computed','2026_values_read'):
        if audit[field] is not False:raise ValueError('independent source boundary changed')
    for n,h in source_hashes.items():bind(directory/n,h)
    bind(directory/'source-postcheck.json',summary['postcheck_sha256'])
    if read(directory/'source-postcheck.json')['all_bound_inputs_unchanged'] is not True:
        raise ValueError('source projection postcheck failed')
    for n,h in summary['input_sha256'].items():bind(Path(n).resolve(),h)
    effective=read(directory/'effective_proofs.json');initial=read(directory/'initial_listing_classification.json')
    lifecycle=read(directory/'lifecycles.json');coverage=read(directory/'coverage_validation.json')
    if (effective!=ctx['effective_proofs'] or initial!=ctx['initial_listing_classification']
            or lifecycle['boundaries']!=ctx['lifecycles'] or lifecycle['actual_flat_inventory_verified'] is not False
            or lifecycle['missing_rows_filled'] is not False):raise ValueError('source proof/lifecycle projection changed')
    before=deepcopy(ctx['packets'])
    events,receipts=compile_primary_event_components(ctx['packets'],effective,ctx['calendar'])
    source_api.validate_compiled(events,receipts,ctx['packets'])
    if (clean([asdict(e) for e in events])!=read(directory/'derived_events.json')
            or list(receipts)!=read(directory/'event_source_receipts.json') or ctx['packets']!=before):
        raise ValueError('canonical events/receipts not exactly reproduced or original source mutated')
    validate_source_coverage(source_api.coverage_view(ctx['packets'],events,initial,ctx['lifecycles']))
    if (coverage['compiled_event_count']!=862 or set(coverage['known_tax_unknown_event_keys'])!=source_api.UNKNOWN
            or coverage['coverage_validated_on_copy'] is not True or coverage['original_source_packets_modified'] is not False
            or coverage['source_admitted_for_account_replay'] is not False):raise ValueError('compiled source coverage/unknown guards changed')
    if (len(ctx['calendar'].days)!=486 or len(ctx['targets'])!=24 or len(ctx['packets'])!=361
            or [ctx['calendar'].days[0].isoformat(),ctx['calendar'].days[-1].isoformat()]!=plan['window']):
        raise ValueError('complete continuous pre2026 account source required')
    verify_inputs(known)
    return {'plan':plan,'calendar':ctx['calendar'],'packets':ctx['packets'],
        'bars':{c:{r['date']:r for r in p['bars']} for c,p in ctx['packets'].items()},
        'targets':ctx['targets'],'proofs':effective,'events':events,'receipts':receipts,
        'lifecycles':ctx['lifecycles'],'known_hashes':known,'source_summary_sha256':source_hashes['summary.json']}


def verify_unknown_zero(events,ledger):
    unknown=[e for e in events if e.stock_per_share>0 and not e.stock_tax_basis_verified
             or e.capital_per_share>0 and not e.capital_tax_exempt_verified]
    if len(unknown)!=6 or len({e.event_id for e in unknown})!=6:raise ValueError('exact six original unknown tax events required')
    checks=[]
    for e in unknown:
        records=[r for r in ledger if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id']==e.event_id]
        ex=[r for r in ledger if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id']==e.event_id]
        if (len(records)!=1 or len(ex)!=1 or records[0]['day']!=e.recorded or ex[0]['day']!=e.ex_date
                or records[0]['instrument']!=e.instrument or ex[0]['instrument']!=e.instrument
                or type(records[0]['quantity']) is not int or records[0]['quantity']!=0
                or type(ex[0]['registered_quantity']) is not int or ex[0]['registered_quantity']!=0):
            raise ValueError('unknown tax event needs actual exact zero record and ex ownership')
        checks.append({'event_id':e.event_id,'instrument':e.instrument,'record':deepcopy(records[0]),'ex':deepcopy(ex[0]),'tax_verification_granted':False})
    return checks


def validate_completed_case(case,ctx):
    days=[d.isoformat() for d in ctx['calendar'].days]
    if ([r['day'] for r in case['days']]!=days or len(days)!=486
            or len(case['intents'])!=24 or [r['execution_session'] for r in case['intents']]!=list(ctx['targets'])
            or case['whole_day_volume_violations']!=0 or case['execution_status']!='DAILY_PROXY_NECESSARY_CHECKS_PASSED'):
        raise ValueError('complete24 decisions/486day account with capacity checks required')
    for row in case['days']:
        if row['equity']<=0 or row['cash']+row['market_value']+row['pending_stock_value']+row['cash_receivable']!=row['equity']:
            raise ValueError('positive continuous equity/asset conservation required')
    checks=verify_unknown_zero(ctx['events'],case['corporate_ledger'])
    if any(r.get('synthetic_price_created') is not False for r in case['lifecycle_source_audit']):
        raise ValueError('lifecycle/source evidence cannot synthesize price')
    return checks


def persist_case(folder,case,unknown):
    write(folder/'source_scope_audit.json',case['lifecycle_source_audit'])
    write(folder/'unknown_tax_zero_ownership.json',unknown)
    return write_case(folder,case)


def score_case(case,initial):
    initial=Decimal(initial);all_days=case['days'];days=[r for r in all_days if r['day']>='2024-01-02']
    if len(days)!=485 or any(r['day']>'2025-12-31' for r in all_days):raise ValueError('pre2026 scoring window required')
    nav={r['day']:r['equity'] for r in all_days};peak=initial;dd=Decimal(0)
    for r in all_days:peak=max(peak,r['equity']);dd=min(dd,r['equity']/peak-1)
    return {'2024_return_pct':float((nav['2024-12-31']/initial-1)*100),
        '2025_return_pct':float((nav['2025-12-31']/nav['2024-12-31']-1)*100),
        'net_compound_return_pct':float((nav['2025-12-31']/initial-1)*100),
        'average_exposure_pct':float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100),
        'max_drawdown_pct':float(dd*100),'cost_pct_initial':float(sum((r['fees'] for r in all_days),Decimal(0))/initial*100),
        'orders':len(case['orders']),'fills':len(case['fills']),'monthly_decisions':len(case['intents']),
        'account_sessions':486,'outcome_sessions':485}


def failure_trace(exc):
    """Read-only exception locals; no tracing hooks or engine/global mutation."""
    tb=exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code is simulate_ordinary_budgeted_fixed_targets.__code__:
            values=tb.tb_frame.f_locals
            return deepcopy({'failed_session':values.get('day'),'required_codes':sorted(values.get('required',())),
                'days':values.get('rows',[]),'intents':values.get('intents',[]),'ownership':values.get('ownership',{}),
                'source_scope_audit':values.get('lifecycle_audit',[]),'last_marks':values.get('marks',{}),
                'following_session':values.get('following'),'following_target':values.get('target')})
        tb=tb.tb_next
    return {'failed_session':None,'required_codes':[],'days':[],'intents':[],'ownership':{},'source_scope_audit':[]}


def account_state(account):
    if account is None:return {'account_created':False}
    return deepcopy({'account_created':True,'last_account_clock':account._last_clock,'cash':account.broker.cash,
        'positions':account.broker.positions,'orders':account.broker.orders,'fills':account.broker.fills,
        'owned_shares':account.owned_quantities(),'entitlements':account.entitlements,
        'corporate_ledger':account.corporate_ledger,'cash_claims':account.cash_claims,'stock_claims':account.stock_claims})


def dependencies(ctx,trace,state):
    day=trace['failed_session'];label=day.isoformat() if isinstance(day,date) else day
    reasons={c:[] for c in trace['required_codes']}
    for c,q in state.get('owned_shares',{}).items():
        if q:reasons.setdefault(c,[]).append('OWNED_PHYSICAL_OR_PENDING_STOCK')
    for order in state.get('orders',[]):
        if order['status']=='PENDING':reasons.setdefault(order['security_id'],[]).append('PENDING_ORDER')
    for event in ctx['events']:
        if event.ex_date==day and state.get('entitlements',{}).get(event.event_id,0):
            reasons.setdefault(event.instrument,[]).append('POSITIVE_EX_ENTITLEMENT')
    for c in (trace.get('following_target') or {}).get('weights',{}):reasons.setdefault(c,[]).append('NEXT_TARGET_PRIOR_CLOSE')
    return {'failed_session':label,'required_codes':trace['required_codes'],'dependency_reasons':reasons,
        'source_rows':{c:deepcopy(ctx['bars'].get(c,{}).get(label)) for c in reasons},
        'source_rows_synthesized':False,'failed_guard_bypassed':False}


def run_profiles(ctx,out,*,plan_sha,simulator=None):
    out=Path(out)
    if out.exists() or out.is_symlink():raise ValueError('preserve previous raw diagnostic; no resume')
    if out.name!=OUTPUT:raise ValueError('fixed new raw diagnostic directory required')
    verify_inputs(ctx['known_hashes']);plan=ctx['plan'];simulator=simulator or simulate_ordinary_budgeted_fixed_targets
    out.mkdir(parents=True);results={};completed={};abnormal=None;post={};annual=False
    try:
        write(out/'input-before.json',ctx['known_hashes'])
        for bps in (20,40):
            folder=out/str(bps);folder.mkdir();holders=[];case=None
            def factory(cal,cash,distributions,**kw):
                account=StockDistributionAccount(cal,cash,distributions,
                    broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
                holders.append(account);return account
            try:
                case=simulator(ctx['calendar'],ctx['bars'],ctx['events'],ctx['targets'],plan['initial_CNY'],
                    lifecycles=ctx['lifecycles'],account_factory=factory,policy_id=POLICY)
                unknown=validate_completed_case(case,ctx)
                artifacts=persist_case(folder,case,unknown)
                results[str(bps)]={'status':'RAW_DAILY_PROXY_RECONCILED','artifact_sha256':artifacts,
                    'unknown_tax_zero_ownership':clean(unknown),'annual_returns_computed':False}
                completed[str(bps)]=case
            except BaseException as exc:
                error={'status':'INVALID_ACCOUNT_OR_SOURCE','error_type':type(exc).__name__,'error':str(exc),
                    'original_traceback':''.join(traceback.format_exception(exc)),'annual_returns_computed':False}
                trace=failure_trace(exc);state=account_state(holders[0] if holders else None)
                if case is not None:
                    # The engine returned before this validation/persistence error;
                    # its traceback frame no longer exists. Retain the full result.
                    write(folder/'returned_case_before_validation.json',case)
                    trace.update(failure_stage='POST_SIMULATION_VALIDATION_OR_PERSISTENCE',
                        failed_session=None,last_completed_session=case['days'][-1]['day'] if case.get('days') else None,
                        days=deepcopy(case.get('days',[])),intents=deepcopy(case.get('intents',[])),
                        ownership=deepcopy(case.get('ownership',{})),
                        source_scope_audit=deepcopy(case.get('lifecycle_source_audit',[])))
                write(folder/'failed_account_state.json',state);write(folder/'partial_engine_trace.json',trace)
                write(folder/'required_source_dependencies.json',dependencies(ctx,trace,state));write(folder/'error.json',error)
                if not (out/'first-error.json').exists():write(out/'first-error.json',error)
                error['failure_artifact_sha256']={p.name:file_sha(p) for p in sorted(folder.iterdir()) if p.is_file()}
                results[str(bps)]=error
                if not isinstance(exc,Exception):abnormal={'error_type':type(exc).__name__,'error':str(exc)};break
            finally:write(out/'case_results.json',results)
    except BaseException as exc:
        abnormal={'error_type':type(exc).__name__,'error':str(exc)}
        write(out/'terminal-error.json',abnormal)
        if not (out/'first-error.json').exists():write(out/'first-error.json',abnormal)
    finally:
        for bps in (20,40):
            if str(bps) not in results:results[str(bps)]={'status':'NOT_RUN_AFTER_INTERRUPTION','annual_returns_computed':False}
        try:verify_inputs(ctx['known_hashes']);post={'source_inputs_unchanged_after_replay':True}
        except BaseException as exc:
            post={'source_inputs_unchanged_after_replay':False,'error_type':type(exc).__name__,'error':str(exc)}
            if not (out/'first-error.json').exists():write(out/'first-error.json',post)
        write(out/'input-postcheck.json',post)
        if len(completed)==2 and abnormal is None and post['source_inputs_unchanged_after_replay']:
            try:
                metrics={bps:score_case(case,plan['initial_CNY']) for bps,case in completed.items()}
                for bps,values in metrics.items():results[bps].update(values,annual_returns_computed=True)
                annual=True
            except BaseException as exc:
                abnormal={'error_type':type(exc).__name__,'error':str(exc)};write(out/'scoring-error.json',abnormal)
        reference=results['40'];values=[reference.get(k,float('nan')) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
        passes=annual and all(math.isfinite(v) for v in values) and min(values[:2])>0 and values[2]>=90
        summary={'status':'IVOL_RAW_PRE2026_DAILY_ENGINEERING_COMPLETE' if annual else 'IVOL_RAW_PRE2026_FAILED_OR_INCOMPLETE_PRESERVED',
            'plan_sha256':plan_sha,'method_code_sha256':plan.get('method_code_sha256',{}),
            'source_projection_summary_sha256':ctx.get('source_summary_sha256'),
            'results_by_extra_bps':results,'reference_extra_bps':40,'reference_CNY':'1000000',
            'annual_returns_computed':annual,'both_profiles_complete_before_annual_scoring':annual,
            'raw_daily_proxy_development_gate_passes':passes,'abnormal_exit':abnormal,**post,
            'postcheck_sha256':file_sha(out/'input-postcheck.json'),
            'annual_return_denominators':'2024 initial1m;2025 preceding2024year-endcontinuous equity;no reset',
            'tax_model':'20percent cash+taxablebonus stress reserve, not actualFIFO liability settlement',
            'execution_model':'unchanged ordinary-source budgeted integer allocation,next explicit daily open,9.5percent reference proxy',
            'raw_account_independently_audited':False,'minute_execution_admitted':False,
            'historical_arrival_certified':False,'full_corporate_actions_certified':False,
            'actual_FIFO_tax_liability_verified':False,'queue_and_impact_calibrated':False,
            '2026_return_computed':False,'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
        write(out/'case_results.json',results);write(out/'summary.json',summary)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('source-root','plan','expected-plan-sha256','output-dir'):parser.add_argument('--'+n,required=True)
    parser.add_argument('--source-preflight-only',action='store_true');a=parser.parse_args(argv)
    base=Path(a.source_root).resolve();out=Path(a.output_dir)
    if out.exists() or out.is_symlink():raise ValueError('preserve existing raw account output')
    if out.resolve()!=base/OUTPUT:raise ValueError('fixed raw output path required')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('external raw account plan checksum changed')
    ctx=load_inputs(base,Path(__file__).resolve().parents[1],a.plan,a.expected_plan_sha256)
    if a.source_preflight_only:
        verify_inputs(ctx['known_hashes']);print('source preflight only; no account or output',flush=True);return 0
    result=run_profiles(ctx,out,plan_sha=a.expected_plan_sha256)
    return 0 if result['annual_returns_computed'] else 2

if __name__=='__main__':raise SystemExit(main())
