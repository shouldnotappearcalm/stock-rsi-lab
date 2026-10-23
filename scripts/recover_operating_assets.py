"""Prospective complete-corpus source recovery; no factors, prices or returns."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import os
from pathlib import Path
import sys

from scripts import inspect_operating_corpus_source as legacy
from scripts.immutable_http_capture import file_sha as sha,need,write_once
from stock_rsi import asset_geometry as geometry
from stock_rsi import operating_source_bridge as bridge
from stock_rsi import annual_operating as op
from stock_rsi.data import digest

OUTPUT='operating-asset-recovery-source-v1-20261023'
LEGACY_OUTPUT=legacy.OUTPUT
GP_OUTPUT=legacy.PARENT_OUTPUT
INITIAL_CACHE=legacy.INITIAL_CACHE
LATER_CACHE=legacy.LATER_CACHE
DATE_ERROR='same-edition explicitly dated prior December31 assets required'
PARENT_REQUEST='experiments/qlib/operating-corpus-source-request.json'
PARENT_SHA='f0302c00af7e312055aaf5a41f74a547de2bf2aaf9465a65d38aa9bf92da3710'
PARENT_PROOF='experiments/qlib/operating-corpus-source-independent-check.json'
PARENT_PROOF_SHA='292aceb7322fe8dd6b15b67a3be4d45ea285ddbbe60876bdde1358d603893581'
INVENTORY='experiments/qlib/operating-lagged-asset-date-inventory.json'
REGULATORY='regulatory-csrc-annual-format-2021-20261023'
STATUS='FROZEN_BEFORE_COMPLETE_OPERATING_ASSET_SOURCE_RECOVERY'
WORKERS=4
METHODS=tuple(dict.fromkeys((*legacy.METHODS,'src/stock_rsi/asset_geometry.py','src/stock_rsi/operating_source_bridge.py',
    'scripts/recover_operating_assets.py','scripts/audit_operating_asset_recovery.py')))
PUBLIC=(PARENT_REQUEST,PARENT_PROOF,INVENTORY,'experiments/qlib/operating-asset-recovery-review.json',
    'experiments/qlib/operating-lagged-asset-bridge-regulatory-proof.json','experiments/qlib/operating-asset-table-geometry-source-request.json',
    'experiments/qlib/operating-asset-table-geometry-source-results.json','experiments/qlib/operating-asset-table-geometry-source-terminal.json',
    'tests/fixtures/operating-asset-summary-real-word-geometry.json','tests/test_asset_geometry.py','tests/test_operating_source_bridge.py',
    'tests/test_operating_asset_recovery.py','tests/test_operating_asset_recovery_audit.py',
    'docs/research/operating-asset-recovery-design-2026-10-23.md','docs/superpowers/plans/2026-10-23-operating-asset-recovery.md')


def read(path):return legacy.read(path)


def candidate_pages(texts,year,primary_page):
    need(type(primary_page) is int and 1<=primary_page<=len(texts),'protected primary page inside original cache')
    compact=[op.compact(t) for t in texts[:20]];selected=set();windows=0
    for i in range(len(compact)-1):
        plain=''.join(compact[i:i+2]);context=''.join(compact[max(0,i-1):i+2])
        if '总资产' in plain and (f'{year-1}年末' in plain or f'{year-1}年12月31日' in plain) and '主要会计数据' in context:
            pages={i+1,i+2}
            if pages&selected:continue
            selected|=pages;windows+=1
            if windows==2:break
    return sorted(selected|{primary_page}) if windows else []


def extract_geometry(pdf,pages,source_sha256,expected_page_count):
    import pdfplumber
    need(pdfplumber.__version__=='0.11.9','frozen original word reader version')
    with pdfplumber.open(pdf) as document:
        need(len(document.pages)==expected_page_count,'original PDF/cache physical page count')
        for number in pages:
            page=document.pages[number-1]
            yield {'physical_page':number,'width':page.width,'height':page.height,'source_sha256':source_sha256,
                'tables':[{'bbox':list(t.bbox)} for t in page.find_tables(table_settings={})],
                'words':page.extract_words(x_tolerance=3,y_tolerance=3,keep_blank_chars=False)}


def required_paths(base,root,membership):
    old=read(root/PARENT_REQUEST);proof=read(root/PARENT_PROOF)
    paths={k:legacy.parent.resolve(k,root,base,membership) for k in old['input_sha256']}
    for relative in proof['all_output_sha256']:paths['source/'+LEGACY_OUTPUT+'/'+relative]=base/LEGACY_OUTPUT/relative
    for name in (*METHODS,*PUBLIC):paths['repo/'+name]=root/name
    regulatory=read(root/'experiments/qlib/operating-lagged-asset-bridge-regulatory-proof.json')
    for name in regulatory['local_evidence_sha256']:paths['source/'+REGULATORY+'/'+name]=base/REGULATORY/name
    geometry_proof=read(root/'experiments/qlib/operating-asset-table-geometry-source-terminal.json')
    prefix='operating-asset-table-geometry-source-v1-20261023'
    for name in (*geometry_proof['output_sha256'],'terminal.json'):paths['source/'+prefix+'/'+name]=base/prefix/name
    return paths


def verify(base,root,membership,request,expected_sha):
    need(sha(request)==expected_sha,'frozen recovery request');req=read(request)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['document_count']==1236 and req['cohort_count']==394
        and req['target_count']==339 and req['workers']==req['maximum_outstanding_documents']==4
        and req['runtime_python']==sys.version.split()[0]=='3.12.14' and req['pdfplumber_version']=='0.11.9'
        and req['normative_basis']==geometry.basis() and req['geometry_pages_per_target']==5 and req['geometry_pages_per_pass']==1695
        and req['cached_search_first_pages']==20 and req['maximum_nonoverlapping_two_page_windows']==2
        and req['network_permitted'] is False and req['factor_ratio_rank_or_return_permitted'] is False
        and req['2026_financial_or_market_values_permitted'] is False and set(req['method_sha256'])==set(METHODS),
        'fixed complete source-only recovery scope')
    import pdfplumber
    need(pdfplumber.__version__==req['pdfplumber_version'],'bound actual geometry reader')
    paths=required_paths(base,root,membership);need(set(paths)==set(req['input_sha256']),'complete recovery input closure')
    for key,p in paths.items():need(sha(p)==req['input_sha256'][key],'bound recovery input '+key)
    for name,value in req['method_sha256'].items():need(value==req['input_sha256']['repo/'+name],'complete method binding')
    need(sha(root/PARENT_REQUEST)==PARENT_SHA and sha(root/PARENT_PROOF)==PARENT_PROOF_SHA,'original source request/proof unchanged')
    old=read(root/PARENT_REQUEST);proof=read(root/PARENT_PROOF);original=read(base/LEGACY_OUTPUT/'case_results.json')
    need(req['documents']==old['documents'] and req['cohort']==old['cohort'] and req['formations']==old['formations'] and req['modes']==old['modes'],
         'complete original source corpus/calendar/modes, no supported subset')
    keys={k for k,c in original.items() if c.get('error')==DATE_ERROR};inventory=read(root/INVENTORY)
    need(keys=={r['capture_key'] for r in inventory['rows']} and req['targets']==[d['capture_key'] for d in req['documents'] if d['capture_key'] in keys]
        and len(req['targets'])==339,'all original date-failure cases retained')
    for key,value in old['input_sha256'].items():need(req['input_sha256'][key]==value,'original source closure protected')
    actual={str(p.relative_to(base/LEGACY_OUTPUT)):sha(p) for p in sorted((base/LEGACY_OUTPUT).rglob('*')) if p.is_file()}
    need(actual==proof['all_output_sha256'],'entire original operating output inventory')
    need(sha(base/REGULATORY/'2021-standard/body.bin')==geometry.basis()['body_sha256'],'original regulatory body identity')
    return req,paths


def legacy_reference(base,document,targeted=False):
    key=document['capture_key'];path=base/LEGACY_OUTPUT/(key+'.json');old=read(path)
    need(old['capture_key']==key and old['instrument']==document['instrument'] and old['source_sha256']==document['source_sha256']
         and old['fiscal_year']==document['effective_fiscal_year'],'legacy source case identity')
    supported=old['status']==legacy.SUPPORTED
    return {'capture_key':key,'instrument':document['instrument'],'fiscal_year':document['effective_fiscal_year'],
        'source_sha256':document['source_sha256'],'original_case_sha256':sha(path),'original_status':old['status'],'original_error':old.get('error'),
        'recovery_state':'PENDING' if targeted else 'NOT_TARGETED','effective_source_status':bridge.LEGACY_SUPPORTED if supported else bridge.STILL_UNSUPPORTED,
        'effective_record_id':old['operating_report']['record_id'] if supported else None,'source_record':None,'asset_bridge':None,
        'historical_arrival_verified':False,'investment_factor_admitted':False}


def inspect_one(base,document,normative_basis):
    base=Path(base);key=document['capture_key'];result=legacy_reference(base,document,True)
    need(result['original_error']==DATE_ERROR,'only registered original date failures targeted')
    gp=read(base/GP_OUTPUT/(key+'.json'));cache_folder=INITIAL_CACHE if document['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER_CACHE
    need(document['source_phase'] in ('INITIAL_AUTHENTICATED_PAGE_CACHE','LATER_ORIGINAL_PDF'),'registered original cache phase')
    cache=read(base/cache_folder/(key+'.pages.json'));texts=cache['pages']
    need(sha(base/document['source_path'])==document['source_sha256']==gp['source_sha256']==cache['source_sha256']
        and cache['extractor']=='pypdf6.10.0' and len(texts)==gp['page_count']
        and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(texts)}==gp['all_extracted_page_text_sha256'],
        'authenticated original PDF and all cached physical pages')
    need(gp['capture_key']==key and gp['instrument']==document['instrument'] and gp['fiscal_year']==document['effective_fiscal_year']
         and gp['cover_code_consistent'] and gp['cover_annual_year_consistent'],'protected original cover/case identity')
    for observation in gp['source_observations']:need(observation['record_id']==digest({k:v for k,v in observation.items() if k!='record_id'}),'protected GP source record integrity')
    year=document['effective_fiscal_year'];current=[o for o in gp['source_observations'] if o['fiscal_end']==f'{year}-12-31']
    need(len(current)==1,'one protected current GP source observation');primary=current[0]['payload']['cells']['total_assets']
    result.update(recovery_state='ATTEMPT_COMPLETE',geometry_pages=[],selected_geometry_pages=[],GP_control_cells_compared=0)
    if not '2021-06-28'<=document['day']<'2025-07-01':return {**result,'failure_stage':'REGULATORY_VERSION','error':'original2021 regulatory version not applicable'}
    selected=candidate_pages(texts,year,primary['page']);result['selected_geometry_pages']=selected
    if not selected:return {**result,'failure_stage':'SUMMARY_WINDOW_ABSENT','error':'no main-accounting candidate within first20 cached pages'}
    try:
        for page in extract_geometry(base/document['source_path'],selected,document['source_sha256'],len(texts)):result['geometry_pages'].append(page)
        need([p['physical_page'] for p in result['geometry_pages']]==selected,'exact complete bounded geometry pages')
    except OSError as exc:
        exc.partial_geometry=result['geometry_pages'];raise
    except Exception as exc:return {**result,'failure_stage':'GEOMETRY_READ','error_type':type(exc).__name__,'error':str(exc)}
    except BaseException as exc:
        exc.partial_geometry=result['geometry_pages'];raise
    try:
        result['asset_bridge']=geometry.parse_summary_assets(result['geometry_pages'],year,document['day'],document['source_sha256'],
            {'source_sha256':document['source_sha256'],'report_year':year,'cell':primary},normative_basis=normative_basis)
    except (ValueError,KeyError,ArithmeticError) as exc:return {**result,'failure_stage':'ASSET_MAPPING','error_type':type(exc).__name__,'error':str(exc)}
    try:record=bridge.recover_source_record(document,texts,result['geometry_pages'],primary,normative_basis=normative_basis)
    except (ValueError,KeyError,ArithmeticError) as exc:return {**result,'failure_stage':'INCOME_SOURCE','error_type':type(exc).__name__,'error':str(exc)}
    controls=0
    for observation in gp['source_observations']:
        period=observation['fiscal_end'];old=observation['payload']['cells'];new=record['payload']['income'][period]
        for field in ('revenue','cost_of_sales'):
            need(all(new[field][k]==old[field][k] for k in ('value_CNY','literal','fiscal_end','column_index')),'protected GP income cell disagreement');controls+=1
        assets=record['payload']['asset_bridge']['current' if period==f'{year}-12-31' else 'prior']
        need(assets['value_CNY']==old['total_assets']['value_CNY'],'protected GP asset value disagreement');controls+=1
    result.update(effective_source_status=bridge.SUPPORTED,effective_record_id=record['record_id'],source_record=record,GP_control_cells_compared=controls)
    return result


def run(base,root,membership,request,expected_sha,*,executor_factory=ProcessPoolExecutor,worker=inspect_one):
    out=base/OUTPUT;need(not out.exists(),'fresh recovery output only; no overwrite/resume')
    req,paths=verify(base,root,membership,request,expected_sha);paths={**paths,'frozen_request':Path(request)}
    expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,p in paths.items():need(sha(p)==expected[key],'recovery input before '+key)
    out.mkdir();targets=set(req['targets']);cases={}
    completed=[];submitted=[];failed=[];queries=[];primary=None;summary=None;persistence=[];mismatches=[]
    try:
        write_once(out/'input-before.json',expected)
        for document in req['documents']:
            key=document['capture_key'];cases[key]=legacy_reference(base,document,key in targets)
        for key,case in cases.items():
            if key not in targets:write_once(out/(key+'.json'),case)
        documents=[d for d in req['documents'] if d['capture_key'] in targets]
        with executor_factory(max_workers=WORKERS) as pool:
            for offset in range(0,len(documents),WORKERS):
                futures=[];batch_error=None
                for doc in documents[offset:offset+WORKERS]:
                    try:future=pool.submit(worker,str(base),doc,req['normative_basis'])
                    except BaseException as exc:batch_error=exc;break
                    submitted.append(doc['capture_key']);futures.append((doc,future))
                for doc,future in futures:
                    key=doc['capture_key']
                    try:
                        case=future.result();need(case['capture_key']==key and case['instrument']==doc['instrument']
                            and case['source_sha256']==doc['source_sha256'] and case['recovery_state']=='ATTEMPT_COMPLETE','completed recovery worker identity')
                        raw=case.pop('geometry_pages');write_once(out/(key+'.geometry.json'),raw);write_once(out/(key+'.json'),case)
                        cases[key]=case;completed.append(key)
                    except BaseException as exc:
                        failed.append({'capture_key':key,'type':type(exc).__name__,'message':str(exc)})
                        if hasattr(exc,'partial_geometry'):
                            try:write_once(out/(key+'.partial-geometry.json'),{'uncommitted':True,'pages':exc.partial_geometry})
                            except BaseException as failure:persistence.append('partial-geometry:'+type(failure).__name__)
                        if batch_error is None:batch_error=exc
                if batch_error is not None:raise batch_error
                if len(completed)%40==0 or len(completed)==len(documents):print('asset source recovery',len(completed),'/',len(documents),flush=True)
        need(set(completed)==targets,'every registered recovery target must finish')
        write_once(out/'case_results.json',cases)
        for formation in req['formations']:
            for mode in req['modes']:
                name=formation['execution_session']+'-'+mode+'.json';view=bridge.augment_coverage(read(base/LEGACY_OUTPUT/name),cases.__getitem__)
                write_once(out/name,view);queries.append({**formation,'mode':mode,'artifact':name,
                    'effective_source_status_counts':dict(Counter(r['effective_source_status'] for r in view['classifications'])),
                    'industry_source_status_counts':dict(Counter(r['industry_status']+'/'+r['effective_source_status'] for r in view['classifications']))})
        observed=sum(sum(v for k,v in q['effective_source_status_counts'].items() if k!='NO_VISIBLE_ANNUAL_REPORT') for q in queries if q['mode']==op.OBSERVED)
        need(observed==0,'actual2026 captures cannot become observed historical sources')
        attempted=[cases[k] for k in req['targets']]
        summary={'status':'COMPLETE_OPERATING_ASSET_SOURCE_RECOVERY_NOT_INVESTMENT_ADMITTED','request_sha256':expected_sha,
            'document_count':len(cases),'cohort_count':len(req['cohort']),'target_documents_completed':len(completed),
            'effective_source_status_counts':dict(Counter(c['effective_source_status'] for c in cases.values())),
            'recovery_failure_stage_counts':dict(Counter(c.get('failure_stage','SOURCE_SUPPORTED') for c in attempted)),
            'recovery_error_counts':dict(Counter(c['error'] for c in attempted if 'error' in c)),
            'asset_bridge_supported_count':sum(c['asset_bridge'] is not None for c in attempted),
            'new_operating_source_records':sum(c['source_record'] is not None for c in attempted),
            'GP_control_cells_compared':sum(c.get('GP_control_cells_compared',0) for c in attempted),
            'queries':queries,'observed_visible_annual_rows':observed,'input_count':len(paths),'all_inputs_unchanged':True,
            'historical_arrival_verified':False,'manual_all_source_visual_QA_complete':False,'financial_cross_issuer_comparability_verified':False,
            'investment_factor_admitted':False,'ratios_rankings_or_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
        write_once(out/'.summary-pending.json',summary)
    except BaseException as exc:primary=exc
    finally:
        if not (out/'case_results.json').exists():
            try:write_once(out/'case_results.json',cases)
            except BaseException as exc:
                persistence.append('case_results:'+type(exc).__name__)
                if primary is None:primary=exc
        for key,p in paths.items():
            try:
                if sha(p)!=expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'mismatches':mismatches,'input_count':len(paths)}
        try:write_once(out/'input-postcheck.json',post)
        except BaseException as exc:
            persistence.append('input-postcheck:'+type(exc).__name__)
            if primary is None:primary=exc
        if summary is not None and primary is None and not mismatches and not persistence:
            try:os.replace(out/'.summary-pending.json',out/'summary.json')
            except BaseException as exc:primary=exc
        terminal={'completed':summary is not None and primary is None and not mismatches and not persistence,
            'completed_target_documents':len(completed),'completed_target_keys':completed,'submitted_target_keys':submitted,
            'unsubmitted_target_keys':[k for k in req['targets'] if k not in submitted],'failed_documents':failed,
            'pending_target_keys':[k for k in req['targets'] if k not in completed],
            'completed_queries':queries,'pending_query_count':len(req['formations'])*len(req['modes'])-len(queries),
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
    if primary is not None:
        if persistence:primary.add_note('recovery persistence errors: '+str(persistence))
        raise primary
    need(not mismatches and not persistence and terminal['completed'],'complete unchanged source recovery and persistence required')
    return summary


def main():
    parser=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();result=run(Path(args.source_root).resolve(),Path(__file__).resolve().parents[1],Path(args.membership_file).resolve(),Path(args.request).resolve(),args.expected_request_sha256)
    print(result['status'],result['effective_source_status_counts'],flush=True)


if __name__=='__main__':main()
