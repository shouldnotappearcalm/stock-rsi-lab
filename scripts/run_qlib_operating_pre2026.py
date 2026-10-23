"""One prospectively frozen operating hypothesis; pre2026 daily proxy only."""
import argparse
import math
import os
from pathlib import Path

from scripts import run_qlib_profitability_pre2026 as engine
from stock_rsi.operating_monthly import PRIMARY,LOW_CONTROL,NAMES,START,END,build_targets
from stock_rsi.qlib_snapshot import QlibSnapshot

read,sha,need,write_once,inventory=engine.read,engine.sha,engine.need,engine.write_once,engine.inventory
OUTPUT='operating-profitability-conditional-development-v1-20261023'
PROVIDER=engine.PROVIDER
SOURCE='operating-asset-recovery-source-v1-20261023'
LEGACY='operating-corpus-source-v1-20261023'
SOURCE_REQUEST='experiments/qlib/operating-asset-recovery-source-request.json'
SOURCE_SHA='d7faf59fab2f90d6dc477f54b3b3ecb7a5c8487dcd0328378e3ed823efa024b2'
SOURCE_PROOF='experiments/qlib/operating-asset-recovery-independent-check.json'
PROOF_SHA='7551c4d43dece6b1eb983e107a27c52658f9443350cbd65a2bfbb7c944e589fa'
COVERAGE='experiments/qlib/operating-asset-recovery-source-coverage.json'
COVERAGE_SHA='b8931b04b8d6d84897f51e8cd31d01c5bcb353390032f96dd438e3432c1c4bff'
ENGINE_REQUEST='experiments/qlib/gross-profitability-pre2026-request.json'
ENGINE_SHA='b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5'
NATIVE_AUDIT='experiments/qlib/audit_sources/2026-10-22-gross-profitability-development-audit.py'
NATIVE_SHA='cfa7f994915eb5c1b8ab51e43ab1ede92aab1d99c615ac962938adc609d5b33f'
STATUS='FROZEN_BEFORE_ONE_OPERATING_PROFITABILITY_DEVELOPMENT_SCREEN'
CAPITAL,EXTRA_BPS=engine.CAPITAL,engine.EXTRA_BPS
METHODS=tuple(dict.fromkeys((*engine.METHODS,'src/stock_rsi/annual_operating.py','src/stock_rsi/operating_source_bridge.py',
    'src/stock_rsi/asset_geometry.py','src/stock_rsi/operating_factor.py','src/stock_rsi/operating_monthly.py',
    'scripts/run_qlib_operating_pre2026.py','scripts/audit_operating_pre2026.py',NATIVE_AUDIT)))
PUBLIC=(SOURCE_REQUEST,SOURCE_PROOF,COVERAGE,ENGINE_REQUEST,'experiments/qlib/operating-profitability-development-review.json',
    'docs/research/operating-profitability-development-design-2026-10-23.md','docs/superpowers/plans/2026-10-23-operating-profitability-development.md',
    'tests/test_operating_factor.py','tests/test_operating_monthly.py','tests/test_operating_development.py','tests/test_operating_development_audit.py')


def validate_request(req):
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['provider_relative']==PROVIDER
        and req['candidate']==PRIMARY and req['controls']==['eligible_equal_weight',LOW_CONTROL]
        and req['candidate_budget']==req['operating_family_trial']==1 and req['account_window']==[START,END]
        and req['capital_CNY']==CAPITAL and req['extra_bps']==list(EXTRA_BPS) and req['target_exposure']==.95
        and req['ranking_fraction']=='1/10' and req['minimum_eligible']==100 and req['minimum_active_cohort_fraction'] is None
        and req['freshness_rule']=='YEAR_MINUS2_THROUGH_JUNE_YEAR_MINUS1_FROM_JULY'
        and req['conditional_engineering_assumptions_explicit'] is True and req['network_permitted'] is False
        and req['2026_financial_or_market_values_permitted'] is False
        and req['execution_adapter']=='scripts.run_qlib_profitability_pre2026.simulate','complete one-candidate operating protocol')


def required_paths(base,root,membership):
    old=read(root/ENGINE_REQUEST);source=read(root/SOURCE_REQUEST);proof=read(root/SOURCE_PROOF)
    paths={k:engine.resolve(k,root,base,membership) for k in {*old['input_sha256'],*source['input_sha256']}}
    for name in proof['all_output_sha256']:paths['source/'+SOURCE+'/'+name]=base/SOURCE/name
    for name in (*METHODS,*PUBLIC):paths['repo/'+name]=root/name
    return paths


def verify(base,root,membership,request,expected_sha):
    need(sha(request)==expected_sha,'frozen operating request');req=read(request);validate_request(req)
    need(set(req['method_sha256'])==set(METHODS),'complete operating method set')
    paths=required_paths(base,root,membership);need(set(paths)==set(req['input_sha256']),'entire source/account input closure')
    for k,p in paths.items():need(sha(p)==req['input_sha256'][k],'bound operating input '+k)
    for p,h in req['method_sha256'].items():need(h==req['input_sha256']['repo/'+p],'explicit operating methods bound')
    need(sha(root/SOURCE_REQUEST)==SOURCE_SHA and sha(root/SOURCE_PROOF)==PROOF_SHA and sha(root/COVERAGE)==COVERAGE_SHA
         and sha(root/NATIVE_AUDIT)==NATIVE_SHA,'fixed independently checked source and account authorities')
    old,_=engine.verify(base,root,membership,root/ENGINE_REQUEST,ENGINE_SHA)
    src,proof,cov=read(root/SOURCE_REQUEST),read(root/SOURCE_PROOF),read(root/COVERAGE)
    need(proof['status']=='PASS_SEPARATE_OPERATING_RECOVERY_ORIGINAL_CELLS_AND_POSITIONS'
        and proof['all_inputs_outputs_unchanged'] is True and proof['document_count']==1236 and proof['target_count']==339
        and proof['all_input_sha256']=={**src['input_sha256'],'frozen_request':SOURCE_SHA}
        and inventory(base/SOURCE)==proof['all_output_sha256']==cov['all_new_output_sha256'],'entire immutable proved source corpus')
    need(req['cohort']==src['cohort']==old['cohort'] and req['formations']==src['formations']==old['formations']
        and req['documents']==src['documents'] and req['runtime']==old['runtime']
        and req['gap_state_manifest_sha256']==old['gap_state_manifest_sha256'],'same complete source universe/clocks/engine runtime')
    need(len(cov['case_rows'])==len({c['capture_key'] for c in cov['case_rows']})==1236
        and req['approved_record_ids']=={c['capture_key']:c['effective_record_id'] for c in cov['case_rows']},'complete approved immutable source ID registry')
    for parent in (old,src):
        for k,h in parent['input_sha256'].items():need(req['input_sha256'][k]==h,'original closure retained '+k)
    return req,paths


def form_targets(base,req,out):
    snapshot=QlibSnapshot(base/PROVIDER);need(snapshot.calendar[-1].isoformat()==END,'physically capped pre2026 quote provider')
    members=engine.parse_memberships((base/PROVIDER/'instruments/csi500.txt').read_text());docs={d['capture_key']:d for d in req['documents']}
    def bound(relative):
        p=base/relative;need(sha(p)==req['input_sha256']['source/'+relative],'selected source bytes unchanged before reading');return read(p)
    # Metadata contains no amounts; monetary cases remain callback-only after visibility.
    views={q['execution_session']:bound(SOURCE+'/'+q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json') for q in req['formations']}
    folder=out/'formations';folder.mkdir()
    def save(day,targets,receipt):write_once(folder/(day+'.json'),{'targets':targets,'receipt':receipt})
    return build_targets(snapshot,members,req['cohort'],views,docs,lambda k:bound(SOURCE+'/'+k+'.json'),
        lambda k:bound(LEGACY+'/'+k+'.json'),req['approved_record_ids'],on_formation=save)


def run(base,root,membership,request,expected_sha,*,form_targets=form_targets,simulation=engine.simulate):
    out=base/OUTPUT;need(not out.exists(),'fresh operating output only; no overwrite/resume')
    req,paths=verify(base,root,membership,request,expected_sha);paths={**paths,'frozen_request':Path(request)}
    expected={**req['input_sha256'],'frozen_request':expected_sha}
    for k,p in paths.items():need(sha(p)==expected[k],'operating input before '+k)
    out.mkdir();results={};primary=None;summary=None;mismatches=[];persistence=[]
    labels=[str(extra)+'/'+name for extra in EXTRA_BPS for name in NAMES]
    try:
        write_once(out/'input-before.json',expected)
        targets,receipts=form_targets(base,req,out)
        need(len(receipts)==len(req['formations']) and all(r['formation_asof']==r['latest_factor_price_read'] for r in receipts),'complete prior-close formations')
        write_once(out/'targets.json',targets);write_once(out/'formation_receipts.json',receipts)
        for extra in EXTRA_BPS:
            for name in NAMES:
                label=str(extra)+'/'+name;folder=out/label;folder.mkdir(parents=True)
                print('operating conditional development',label,flush=True)
                result=simulation(base/PROVIDER,targets[name],name=name,extra_bps=extra,out=folder,base=base,req=req)
                need(result['status']=='DAILY_PROXY_DEVELOPMENT_RECONCILED','same reconciled daily account engine')
                for key in ('2024_return_pct','2025_return_pct','average_exposure_pct','turnover_x_initial'):
                    need(type(result.get(key)) in (int,float) and math.isfinite(result[key]),'complete finite development metrics')
                need(type(result.get('unverified_held_marks')) is int and result['unverified_held_marks']>=0,'explicit missing-mark evidence')
                write_once(folder/'metrics.json',result);results[label]=result
        p=results['40/'+PRIMARY];lead=PRIMARY if min(p['2024_return_pct'],p['2025_return_pct'])>0 and p['average_exposure_pct']>=90 and p['unverified_held_marks']==0 else None
        summary={'status':'ONE_OPERATING_PROFITABILITY_PRE2026_DEVELOPMENT_COMPLETE','candidate_budget':1,'operating_family_trial':1,
            'request_sha256':expected_sha,'start':START,'end':END,'capital_CNY':CAPITAL,'results_by_extra_bps_and_family':results,
            'selected_development_lead':lead,'selection_rule':'Primary only,40bp: each2024/2025 net positive,exposure>=90%,zero unverified marks; controls never promoted.',
            'targets_sha256':sha(out/'targets.json'),'formation_receipts_sha256':sha(out/'formation_receipts.json'),
            'input_count':len(paths),'all_inputs_unchanged':True,'historical_arrival_verified':False,'current_business_identity_verified':False,
            'financial_reporting_compatibility_verified':False,'financial_version_history_complete':False,'raw_share_execution_verified':False,
            'investment_factor_admitted':False,'2026_financial_or_market_values_read':False,'sealed_evidence':False,'objective_achieved':False,
            'claim_status':'CONDITIONAL_OPERATING_SOURCE_NORMALIZED_DAILY_SCREEN_REQUIRES_RAW_AND_2026_CONFIRMATION'}
        write_once(out/'.summary-pending.json',summary)
    except BaseException as exc:primary=exc
    finally:
        try:write_once(out/'case_results.json',results)
        except BaseException as exc:
            persistence.append('case_results.json:'+type(exc).__name__)
            if primary is None:primary=exc
        for k,p in paths.items():
            try:
                if sha(p)!=expected[k]:mismatches.append({'input':k,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':k,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches}
        for filename,value in (('input-postcheck.json',post),):
            try:write_once(out/filename,value)
            except BaseException as exc:
                persistence.append(filename+':'+type(exc).__name__)
                if primary is None:primary=exc
        if summary is not None and primary is None and not mismatches and not persistence:
            try:os.replace(out/'.summary-pending.json',out/'summary.json')
            except BaseException as exc:primary=exc
        terminal={'completed':summary is not None and primary is None and not mismatches and not persistence,'completed_profiles':list(results),
            'pending_profiles':[s for s in labels if s not in results], 'completed_formation_artifacts':sorted(p.name for p in (out/'formations').glob('*.json')),
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},'postcheck':post,'persistence_errors':persistence}
        try:write_once(out/'.terminal-pending.json',terminal);os.replace(out/'.terminal-pending.json',out/'terminal.json')
        except BaseException as exc:
            persistence.append('terminal:'+type(exc).__name__)
            if primary is None:primary=exc
            if (out/'summary.json').exists():
                try:os.replace(out/'summary.json',out/'uncommitted-summary.json')
                except BaseException as failure:persistence.append('summary-demotion:'+type(failure).__name__)
            terminal.update(completed=False,original_error={'type':type(primary).__name__,'message':str(primary)})
            try:write_once(out/'.terminal-failure.json',terminal);os.replace(out/'.terminal-failure.json',out/'terminal.json')
            except BaseException as failure:persistence.append('terminal-failure:'+type(failure).__name__)
        # Validate again after all output/terminal persistence, including its failures.
        final_mismatches=[]
        for k,p in paths.items():
            try:
                if sha(p)!=expected[k]:final_mismatches.append({'input':k,'reason':'SHA256_CHANGED'})
            except BaseException as exc:final_mismatches.append({'input':k,'reason':type(exc).__name__})
        final_post={'all_inputs_unchanged':not final_mismatches,'count':len(paths),'mismatches':final_mismatches}
        if final_post!=post:
            post=final_post;mismatches=final_mismatches
            if primary is None:primary=ValueError('operating inputs changed during final persistence')
            terminal.update(completed=False,postcheck=post,original_error={'type':type(primary).__name__,'message':str(primary)})
            if (out/'summary.json').exists():
                try:os.replace(out/'summary.json',out/'uncommitted-summary.json')
                except BaseException as failure:persistence.append('late-summary-demotion:'+type(failure).__name__)
            for filename,value in (('input-postcheck-after-persistence.json',post),('.terminal-input-failure.json',terminal)):
                try:write_once(out/filename,value)
                except BaseException as failure:persistence.append(filename+':'+type(failure).__name__)
            if (out/'.terminal-input-failure.json').exists():
                try:os.replace(out/'.terminal-input-failure.json',out/'terminal.json')
                except BaseException as failure:persistence.append('late-terminal:'+type(failure).__name__)
    if primary is not None:
        if persistence:primary.add_note('operating persistence failures: '+str(persistence))
        raise primary
    need(terminal['completed'],'complete unchanged operating run/persistence required');return summary


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();s=run(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.membership_file).resolve(),Path(a.request).resolve(),a.expected_request_sha256)
    print(s['status'],'lead',s['selected_development_lead'],flush=True)


if __name__=='__main__':main()
