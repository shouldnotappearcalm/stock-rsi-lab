"""Frozen evidence-bound regime replay; old ordinary failure is immutable.

Adds general holding-state and explicit ST limit-order capabilities while the
strategy, account, allocator, cost profiles and original source stay fixed.
No 2026 data or account outcomes are read by this entry point.
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
from scripts import run_ivol_raw_pre2026 as ordinary
from scripts.replay_regime_budgeted_stock_distribution_targets import simulate_regime_budgeted_fixed_targets
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

read,write,safe=ordinary.read,ordinary.write,ordinary.safe
file_sha,verify_inputs=ordinary.file_sha,ordinary.verify_inputs
clean=ordinary.clean
account_state,dependencies=ordinary.account_state,ordinary.dependencies
score_case=ordinary.score_case
POLICY=ordinary.POLICY
OUTPUT='low-market-residual-vol1m-regime-raw-development-pre2026-20261021'
PRIMARY='low-market-residual-vol1m-regime-primary-pre2026-20261021'
OLD_OUTPUT=ordinary.OUTPUT
OLD_PLAN='experiments/qlib/low-market-residual-vol1m-raw-development-request.json'
OLD_AUDIT='experiments/qlib/low-market-residual-vol1m-raw-development-independent-failure-audit.json'
EVIDENCE='experiments/qlib/low-market-residual-vol1m-regime-evidence.json'
PRIMARY_PUBLIC='experiments/qlib/low-market-residual-vol1m-regime-primary-source-manifest.json'
RESEARCH='experiments/qlib/low-market-residual-vol1m-regime-primary-source-research.json'
PROTOCOL='docs/research/low-market-residual-vol1m-regime-development-protocol-2026-10-21.md'
METHOD_FILES=ordinary.METHOD_FILES+('src/stock_rsi/trading_regime_source.py',
 'scripts/replay_regime_budgeted_stock_distribution_targets.py','scripts/run_ivol_regime_raw_pre2026.py')
PUBLIC_FILES=(OLD_PLAN,OLD_AUDIT,EVIDENCE,PRIMARY_PUBLIC,RESEARCH)
LOCAL_FILES=(PRIMARY+'/manifest.json',OLD_OUTPUT+'/summary.json')


def validate_plan(plan):
    fixed={'status':'FROZEN_IVOL_REGIME_RAW_PRE2026_DAILY_ENGINEERING_PLAN',
      'initial_CNY':'1000000','extra_cost_bps':[20,40],'reference_extra_bps':40,
      'window':['2023-12-29','2025-12-31'],'policy_id':POLICY,
      'allocator':'plan_budgeted_raw_targets','source_guard':'regime_source_rows_on',
      'tax_reserve_rate':'0.2','minimum_average_exposure_pct':90,'candidate_budget':1,
      'profile_budget':2,'output_relative':OUTPUT,'protocol_file':PROTOCOL,
      'risk_warning_buy_permission':False,'investment_rule_changed':False,
      'new_2026_queries_allowed':False,'old_failure_must_remain_unchanged':True}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in fixed.items()):
        raise ValueError('fixed regime account scope/capabilities changed')
    if any(type(n) is not int for n in plan['extra_cost_bps']):raise ValueError('integer fixed cost profiles required')
    for key,names in (('method_code_sha256',METHOD_FILES),('public_evidence_sha256',PUBLIC_FILES),('local_source_sha256',LOCAL_FILES)):
        if set(plan[key])!=set(names):raise ValueError('exact regime method/public/local maps required')


def validate_primary_evidence(evidence,manifest,research,root,bind):
    # Literal metadata is independently reviewed; actual bytes remain mandatory.
    if (manifest['status']!='HASH_VERIFIED_EXISTING_PRIMARY_READING_BYTES_IMPORTED_NO_NEW_NETWORK'
        or manifest['all_existing_inputs_unchanged'] is not True
        or manifest['SDK_queries']!=0 or manifest['HTTP_queries_in_this_import']!=0):
        raise ValueError('verified immutable historical reading cache required')
    expected_artifacts={'issuer-www-st-notice.pdf','sse-trading-rules-2023.docx',
      'reading-download-receipts-additional.json','issuer-st-notice-text.txt',
      'sse-trading-rules-2023-text.txt'}
    if (set(manifest['artifact_sha256'])!=expected_artifacts
        or len(manifest['documents'])!=2
        or {d['file'] for d in manifest['documents']}!=
           {'issuer-www-st-notice.pdf','sse-trading-rules-2023.docx'}):
        raise ValueError('exact complete primary documents and reading artifacts required')
    for document in manifest['documents']:
        if document['sha256']!=manifest['artifact_sha256'][document['file']]:
            raise ValueError('primary document omitted from authenticated artifact map')
    for name,h in manifest['artifact_sha256'].items():bind(safe(root,name),h)
    docs={d['file']:d for d in manifest['documents']}
    rule=evidence['rule_document'];states=evidence['state_intervals']
    if (evidence['contract']!='SSE_MAINBOARD_RISK_WARNING_PRE2026_V1'
        or evidence['account_capabilities']!={'risk_warning_buy_permission':False}
        or rule['source_file']!='sse-trading-rules-2023.docx'
        or rule['sha256']!=docs[rule['source_file']]['sha256']
        or rule['published_on']!='2023-02-17'
        or rule['valid_from']!='2023-12-29' or rule['valid_through']!='2025-12-31'
        or len(states)!=1):raise ValueError('fixed reviewed pre2026 exchange rule required')
    state=states[0];notice=research['primary_notice'];facts=notice['facts']
    expected={'instrument':'SH600079','exchange':'SSE','board':'MAINBOARD','risk_status':'OTHER_RISK_WARNING',
      'effective_from':'2025-12-16','effective_through':'2025-12-31','published_on':'2025-12-13',
      'engineering_available_at':'2025-12-14T00:00:00+08:00','actual_arrival_verified':False,
      'source_file':'issuer-www-st-notice.pdf','source_sha256':docs['issuer-www-st-notice.pdf']['sha256']}
    if (state!=expected or notice['pdf_sha256']!=state['source_sha256']
        or facts['ST_effective_date']!=state['effective_from'] or facts['daily_price_limit_pct']!=5
        or facts['halt_date']!='2025-12-15' or facts['resumption_date']!='2025-12-16'
        or notice['physical_pages_complete_text_read_rendered_and_visually_inspected']!=[1,2,3]
        or research['existing_cash_share_trading']['attachment_sha256']!=rule['sha256']
        or research['public_time_boundaries']['earliest_primary_public_timestamp_authenticated'] is not False):
        raise ValueError('reviewed primary state/limits and arrival uncertainty changed')
    receipts=read(root/'reading-download-receipts-additional.json')
    for name in (rule['source_file'],state['source_file']):
        matches=[r for r in receipts if Path(r['local_file']).name==name]
        if len(matches)!=1 or matches[0]['status']!=200 or matches[0]['body_sha256']!=docs[name]['sha256']:
            raise ValueError('original successful source reading receipt required')


def load_inputs(base,repo,plan_path,expected_sha):
    base,repo=Path(base).resolve(),Path(repo).resolve();path=Path(plan_path).resolve()
    if file_sha(path)!=expected_sha:raise ValueError('external regime plan checksum changed')
    plan=read(path);validate_plan(plan);known={str(path):expected_sha}
    def bind(p,h):
        p=Path(p).resolve()
        if not(p.is_relative_to(base) or p.is_relative_to(repo)):raise ValueError('regime evidence outside registered roots')
        if str(p) in known and known[str(p)]!=h:raise ValueError('conflicting regime input hash')
        if file_sha(p)!=h:raise ValueError('frozen regime input changed: '+str(p))
        known[str(p)]=h
    for key,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for name,h in plan[key].items():bind(safe(parent,name),h)
    bind(repo/PROTOCOL,plan['protocol_sha256'])
    ctx=ordinary.load_inputs(base,repo,repo/OLD_PLAN,plan['public_evidence_sha256'][OLD_PLAN])
    for name,h in ctx['known_hashes'].items():bind(name,h)
    audit=read(repo/OLD_AUDIT);oldroot=base/OLD_OUTPUT
    if (audit['status']!='PASS_INDEPENDENT_FAILED_RAW_ACCOUNT_PRESERVATION_AUDIT'
        or audit['summary_sha256']!=file_sha(oldroot/'summary.json')
        or audit['plan_sha256']!=plan['public_evidence_sha256'][OLD_PLAN]
        or audit['critical_or_important_findings'] or audit['account_replay_rerun'] is not False
        or audit['annual_scorer_called'] is not False or audit['guard_bypassed'] is not False
        or audit['objective_achieved'] is not False):raise ValueError('authentic preserved ordinary failure required')
    for name,h in audit['all_output_file_sha256'].items():bind(safe(oldroot,name),h)
    for name,h in audit['all_bound_inputs_actual_sha256'].items():bind(name,h)
    primary=base/PRIMARY;manifest=read(primary/'manifest.json');research=read(repo/RESEARCH)
    if (manifest!=read(repo/PRIMARY_PUBLIC) or manifest['source_research_sha256']!=file_sha(repo/RESEARCH)
        or manifest['independent_failed_account_audit_sha256']!=file_sha(repo/OLD_AUDIT)):
        raise ValueError('primary cache exact source/audit identity required')
    evidence=read(repo/EVIDENCE);validate_primary_evidence(evidence,manifest,research,primary,bind)
    ctx.update(plan=plan,regime_evidence=evidence,known_hashes=known,
      old_prefix={str(b):{'trace':read(oldroot/str(b)/'partial_engine_trace.json'),
        'state':read(oldroot/str(b)/'failed_account_state.json')} for b in (20,40)})
    verify_inputs(known);return ctx


def compare_preserved_prefix(case,prefix):
    trace,state=prefix['trace'],prefix['state'];cut=trace['failed_session'];n=len(trace['days'])
    if (n!=474 or cut!='2025-12-16' or clean(case['days'][:n])!=trace['days']
        or clean(case['intents'])!=trace['intents']
        or clean([f for f in case['fills'] if f['execution_at'][:10]<cut])!=state['fills']
        or clean([r for r in case['corporate_ledger'] if str(r['day'])<cut])!=state['corporate_ledger']
        or clean({d:v for d,v in case['ownership'].items() if d<cut})!=trace['ownership']):
        raise ValueError('new regime version changed preserved ordinary financial/intent prefix')
    return {'old_partial_days':n,'old_failed_session':cut,'financial_prefix_byte_semantics_identical':True,
      'all24_monthly_intents_identical':True,'old_source_guard_failure_relabelled_success':False}


def validate_completed_case(case,ctx,bps):
    unknown=ordinary.validate_completed_case(case,ctx)
    prefix=compare_preserved_prefix(case,ctx['old_prefix'][str(bps)])
    if not isinstance(case.get('regime_audit'),list) or not isinstance(case.get('phase_audit'),list):
        raise ValueError('explicit regime and phase audits required')
    return unknown,prefix


def persist_case(folder,case,unknown,prefix):
    write(folder/'regime_audit.json',case['regime_audit']);write(folder/'phase_audit.json',case['phase_audit'])
    write(folder/'ordinary_prefix_regression.json',prefix)
    return ordinary.persist_case(folder,case,unknown)


def failure_trace(exc):
    """Read-only exception locals; no tracing hooks or engine/global mutation."""
    tb=exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code is simulate_regime_budgeted_fixed_targets.__code__:
            values=tb.tb_frame.f_locals
            return deepcopy({'failed_session':values.get('day'),'required_codes':sorted(values.get('required',())),
                'days':values.get('rows',[]),'intents':values.get('intents',[]),'ownership':values.get('ownership',{}),
                'source_scope_audit':values.get('lifecycle_audit',[]),'last_marks':values.get('marks',{}),
                'regime_audit':values.get('regime_audit',[]),'phase_audit':values.get('phase_audit',[]),
                'failed_phase':values.get('current_phase'),
                'following_session':values.get('following'),'following_target':values.get('target')})
        tb=tb.tb_next
    return {'failed_session':None,'required_codes':[],'days':[],'intents':[],'ownership':{},'source_scope_audit':[],'regime_audit':[],'phase_audit':[],'failed_phase':None}


def run_profiles(ctx,out,*,plan_sha,simulator=None):
    out=Path(out)
    if out.exists() or out.is_symlink():raise ValueError('preserve previous raw diagnostic; no resume')
    if out.name!=OUTPUT:raise ValueError('fixed new raw diagnostic directory required')
    verify_inputs(ctx['known_hashes']);plan=ctx['plan'];simulator=simulator or simulate_regime_budgeted_fixed_targets
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
                    lifecycles=ctx['lifecycles'],regime_evidence=ctx['regime_evidence'],account_factory=factory,policy_id=POLICY)
                unknown,prefix=validate_completed_case(case,ctx,bps)
                artifacts=persist_case(folder,case,unknown,prefix)
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
        summary={'status':'IVOL_REGIME_RAW_PRE2026_DAILY_ENGINEERING_COMPLETE' if annual else 'IVOL_REGIME_RAW_PRE2026_FAILED_OR_INCOMPLETE_PRESERVED',
            'plan_sha256':plan_sha,'method_code_sha256':plan.get('method_code_sha256',{}),
            'source_projection_summary_sha256':ctx.get('source_summary_sha256'),
            'results_by_extra_bps':results,'reference_extra_bps':40,'reference_CNY':'1000000',
            'annual_returns_computed':annual,'both_profiles_complete_before_annual_scoring':annual,
            'raw_daily_proxy_development_gate_passes':passes,'abnormal_exit':abnormal,**post,
            'postcheck_sha256':file_sha(out/'input-postcheck.json'),
            'annual_return_denominators':'2024 initial1m;2025 preceding2024year-endcontinuous equity;no reset',
            'tax_model':'20percent cash+taxablebonus stress reserve, not actualFIFO liability settlement',
            'execution_model':'same budgeted integer allocation;ordinary9.5guard;authenticated ST5percent LIMIT daily-open proxy',
            'raw_account_independently_audited':False,'historical_arrival_verified':False,'risk_warning_buy_permission':False,'minute_execution_admitted':False,
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
