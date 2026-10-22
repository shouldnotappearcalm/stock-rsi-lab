"""Frozen asset-expansion signal; reuse the immutable prior daily account engine."""
import argparse
import math
from pathlib import Path

from scripts import run_qlib_profitability_pre2026 as engine
from stock_rsi.asset_expansion_monthly import PRIMARY,HIGH_CONTROL,NAMES,START,END,build_targets
from stock_rsi.qlib_snapshot import QlibSnapshot

read,sha,need,write_once,inventory=engine.read,engine.sha,engine.need,engine.write_once,engine.inventory
OUTPUT='asset-expansion-conditional-development-v1-20261022'
PROVIDER=engine.PROVIDER
METADATA_SOURCE=engine.SOURCE
ASSET_SOURCE='annual-total-assets-all1236-v1-20261022'
ASSET_REQUEST='experiments/qlib/annual-assets-all1236-request.json'
ASSET_SHA='ff3634bc7fc215d621d4d6ed87f02cbecc9016045ee2364f32b92ec3f7d7b4b6'
ASSET_AUDIT='experiments/qlib/annual-assets-all1236-source-audit.json'
ENGINE_REQUEST='experiments/qlib/gross-profitability-pre2026-request.json'
ENGINE_SHA='b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5'
STATUS='FROZEN_BEFORE_ONE_LOW_ASSET_EXPANSION_DEVELOPMENT_SCREEN'
CAPITAL,EXTRA_BPS=engine.CAPITAL,engine.EXTRA_BPS
METHODS=tuple(dict.fromkeys((*engine.METHODS,'src/stock_rsi/annual_assets.py',
    'src/stock_rsi/asset_expansion_monthly.py','scripts/run_qlib_asset_expansion_pre2026.py')))


def verify(base,root,membership,request_file,expected_sha):
    need(sha(request_file)==expected_sha,'frozen asset-expansion request changed')
    req=read(request_file)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['provider_relative']==PROVIDER
         and req['candidate']==PRIMARY and req['controls']==['eligible_equal_weight',HIGH_CONTROL]
         and req['candidate_budget']==1 and req['asset_expansion_family_trial']==1
         and req['account_window']==[START,END] and req['capital_CNY']==CAPITAL and req['extra_bps']==list(EXTRA_BPS)
         and req['target_exposure']==.95 and req['ranking_fraction']=='1/10'
         and req['minimum_eligible']==100 and req['minimum_active_cohort_fraction'] is None
         and req['freshness_rule']=='YEAR_MINUS2_THROUGH_JUNE_YEAR_MINUS1_FROM_JULY'
         and req['execution_adapter']=='scripts.run_qlib_profitability_pre2026.simulate'
         and req['conditional_engineering_assumptions_explicit'] is True
         and req['network_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False
         and set(req['method_sha256'])==set(METHODS),'complete one-candidate asset-expansion protocol')
    paths={key:engine.resolve(key,root,base,membership) for key in req['input_sha256']}
    for key,path in paths.items():need(sha(path)==req['input_sha256'][key],'bound expansion input '+key)
    for name,value in req['method_sha256'].items():need(value==req['input_sha256']['repo/'+name],'complete expansion method binding')
    old,_=engine.verify(base,root,membership,root/ENGINE_REQUEST,ENGINE_SHA)
    need(req['runtime']==old['runtime'] and req['cohort']==old['cohort'] and req['formations']==old['formations']
         and req['gap_state_manifest_sha256']==old['gap_state_manifest_sha256'],'same runtime/metadata clocks/cohort/quote/gap engine')
    for key,value in old['input_sha256'].items():need(req['input_sha256'][key]==value,'old account/provider source closure')
    need(sha(root/ASSET_REQUEST)==ASSET_SHA,'unchanged standalone asset source request')
    source,audit=read(root/ASSET_REQUEST),read(root/ASSET_AUDIT)
    need(audit['request_sha256']==ASSET_SHA and audit['all_input_sha256']=={**source['input_sha256'],'frozen_request':ASSET_SHA}
         and audit['document_count']==1236 and audit['asset_report_count']==907 and audit['newly_supported_report_count']==116
         and audit['old_supported_reports_preserved']==791 and audit['old_asset_cells_preserved']==1243
         and audit['all_inputs_and_outputs_unchanged'] is True and audit['no_production_imports'] is True,
         'complete independently audited asset source')
    for key,value in source['input_sha256'].items():need(req['input_sha256'][key]==value,'asset original-source input closure')
    need(inventory(base/ASSET_SOURCE)==audit['all_output_sha256'],'all1242 immutable asset outputs')
    for name,value in audit['all_output_sha256'].items():need(req['input_sha256']['source/'+ASSET_SOURCE+'/'+name]==value,'asset output closure')
    return req,paths


def form_targets(base,req,out):
    provider=base/PROVIDER;snapshot=QlibSnapshot(provider)
    need(snapshot.calendar[-1].isoformat()==END,'physically capped formation quote reader')
    memberships=engine.parse_memberships((provider/'instruments/csi500.txt').read_text())
    views={q['execution_session']:read(base/METADATA_SOURCE/(q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json')) for q in req['formations']}
    cases=read(base/ASSET_SOURCE/'case_results.json');folder=out/'formations';folder.mkdir()
    def save(day,targets,receipt):write_once(folder/(day+'.json'),{'targets':targets,'receipt':receipt})
    return build_targets(snapshot,memberships,req['cohort'],views,cases.__getitem__,on_formation=save)


def run(base,root,membership,request_file,expected_sha,*,form_targets=form_targets,simulation=engine.simulate):
    out=base/OUTPUT;need(not out.exists(),'fresh asset-expansion output; no resume or overwrite')
    req,paths=verify(base,root,membership,request_file,expected_sha)
    paths={**paths,'frozen_request':request_file};expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,path in paths.items():need(sha(path)==expected[key],'expansion input before '+key)
    out.mkdir(parents=True);results={};primary=None;mismatches=[];persistence=[]
    labels=[str(extra)+'/'+name for extra in EXTRA_BPS for name in NAMES]
    try:
        write_once(out/'input-before.json',expected)
        targets,receipts=form_targets(base,req,out)
        need(len(receipts)==len(req['formations']) and all(r['formation_asof']==r['latest_factor_price_read'] for r in receipts),
             'complete prior-close expansion formations')
        write_once(out/'targets.json',targets);write_once(out/'formation_receipts.json',receipts)
        for extra in EXTRA_BPS:
            for name in NAMES:
                label=str(extra)+'/'+name;folder=out/label;folder.mkdir(parents=True)
                print('low asset expansion development',label,flush=True)
                result=simulation(base/req['provider_relative'],targets[name],name=name,extra_bps=extra,out=folder,base=base,req=req)
                need(result['status']=='DAILY_PROXY_DEVELOPMENT_RECONCILED','same reconciled daily account engine')
                metrics=('2024_return_pct','2025_return_pct','average_exposure_pct','turnover_x_initial')
                need(all(k in result and type(result[k]) in (int,float) and math.isfinite(result[k]) for k in metrics)
                     and type(result.get('unverified_held_marks')) is int and result['unverified_held_marks']>=0,'complete finite development metrics')
                write_once(folder/'metrics.json',result);results[label]=result
    except BaseException as exc:primary=exc
    finally:
        for key,path in paths.items():
            try:
                if sha(path)!=expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches}
        terminal={'completed_profiles':list(results),'pending_profiles':[label for label in labels if label not in results],
            'completed_formation_artifacts':sorted(p.name for p in (out/'formations').glob('*.json')),
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence:primary.add_note('asset-expansion terminal persistence: '+str(persistence))
        raise primary
    need(not mismatches and not persistence,'complete unchanged asset-expansion inputs/terminal')
    row=results['40/'+PRIMARY]
    lead=PRIMARY if min(row['2024_return_pct'],row['2025_return_pct'])>0 and row['average_exposure_pct']>=90 and row['unverified_held_marks']==0 else None
    summary={'status':'ONE_LOW_ASSET_EXPANSION_PRE2026_DEVELOPMENT_COMPLETE','candidate_budget':1,'asset_expansion_family_trial':1,
        'request_sha256':expected_sha,'start':START,'end':END,'capital_CNY':CAPITAL,
        'results_by_extra_bps_and_family':results,'selected_development_lead':lead,
        'selection_rule':'Primary only,40bp: each2024/2025 net positive,exposure>=90%,zero unverified marks; controls cannot be promoted.',
        'execution_adapter':'scripts.run_qlib_profitability_pre2026.simulate','targets_sha256':sha(out/'targets.json'),
        'formation_receipts_sha256':sha(out/'formation_receipts.json'),'input_count':len(paths),'all_inputs_unchanged':True,
        'historical_arrival_verified':False,'current_business_identity_verified':False,'financial_reporting_compatibility_verified':False,
        'financial_version_history_complete':False,'raw_share_execution_verified':False,'investment_factor_admitted':False,
        '2026_financial_or_market_values_read':False,'sealed_evidence':False,'objective_achieved':False,
        'claim_status':'CONDITIONAL_SAME_EDITION_ASSET_SOURCE_NORMALIZED_DAILY_SCREEN_REQUIRES_SOURCE_AND_RAW_CONFIRMATION'}
    write_once(out/'summary.json',summary);print('low asset expansion complete; lead',lead,flush=True);return summary


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.membership_file).resolve(),Path(a.request).resolve(),a.expected_request_sha256)


if __name__=='__main__':main()
