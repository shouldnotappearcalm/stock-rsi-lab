"""One bounded source-only balance extraction; old GP asset cells stay verbatim."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
from pathlib import Path
import sys

from scripts.build_profitability_availability import resolve
from scripts.immutable_http_capture import file_sha as sha,need,write_once
from stock_rsi import annual_assets as assets
from stock_rsi.data import digest

OUTPUT='annual-total-assets-all1236-v1-20261022'
PARENT_OUTPUT='gross-profitability-all1236-header-v7-20261022'
INITIAL_CACHE='gross-profitability-historical394-initial2022-schema-20261022'
LATER_CACHE='gross-profitability-all1236-source-v6-20261022'
PARENT_REQUEST='experiments/qlib/profitability-all1236-v7-request.json'
PARENT_SHA='51d047df56f4150906172d3ac27972ee3167e9b98cb4b1b32e800d066099eb55'
PARENT_AUDIT='experiments/qlib/profitability-all1236-v7-source-audit.json'
STATUS='FROZEN_BEFORE_BALANCE_ONLY_ALL1236_SOURCE_EXTRACTION'
SUPPORTED='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA'
WORKERS=4
METHODS=('src/stock_rsi/annual_assets.py','scripts/inspect_annual_assets_source.py',
         'scripts/build_profitability_availability.py','scripts/immutable_http_capture.py')


def read(path):return __import__('json').loads(Path(path).read_text())
def inventory(folder):return {str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def verify(base,root,membership,request_file,expected_sha):
    need(sha(request_file)==expected_sha,'frozen standalone-assets request')
    req=read(request_file)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['document_count']==1236
         and req['cohort_count']==394 and req['old_GP_supported_reports']==791 and req['old_GP_asset_cell_count']==1243
         and req['workers']==req['maximum_outstanding_documents']==WORKERS
         and req['parser_contract']==assets.CONTRACT and req['normative_basis']==assets.CAS19_REFERENCE
         and req['runtime_python']==sys.version.split()[0] and req['new_PDF_text_decodings_permitted'] is False
         and req['network_permitted'] is False and req['ranking_or_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False
         and req['old_assets_reused_without_rewriting_cells'] is True
         and set(req['method_sha256'])==set(METHODS),'complete source-only asset protocol')
    paths={k:resolve(k,root,base,membership) for k in req['input_sha256']}
    for key,path in paths.items():need(sha(path)==req['input_sha256'][key],'bound assets input '+key)
    for name,value in req['method_sha256'].items():need(value==req['input_sha256']['repo/'+name],'asset method binding')
    need(sha(root/PARENT_REQUEST)==PARENT_SHA,'unchanged original V7 source request')
    parent,audit=read(root/PARENT_REQUEST),read(root/PARENT_AUDIT)
    need(audit['request_sha256']==PARENT_SHA and audit['all_input_sha256']=={**parent['input_sha256'],'frozen_source_request':PARENT_SHA}
         and req['documents']==parent['documents'] and len({d['announcement_id'] for d in req['documents']})==1236,
         'complete same audited original annual editions')
    for key,value in parent['input_sha256'].items():need(req['input_sha256'][key]==value,'parent original-input closure')
    need(inventory(base/PARENT_OUTPUT)==audit['all_output_sha256'],'complete unchanged V7 outputs')
    for name,value in audit['all_output_sha256'].items():
        need(req['input_sha256']['source/'+PARENT_OUTPUT+'/'+name]==value,'complete V7 output bindings')
    names=sorted({c for c,a,b in (s.split() for s in membership.read_text().splitlines()) if a<='2024-01-02'<=b and c.startswith(('SH60','SZ00'))})
    need(names==req['cohort'] and len(names)==394,'full dated394 source cohort,not a parsing-success subset')
    old=read(base/PARENT_OUTPUT/'case_results.json')
    need(sum(bool(c['source_observations']) for c in old.values())==791
         and sum(len(c['source_observations']) for c in old.values())==1243,'protected full old-asset controls')
    return req,paths


def inspect_one(base,document,normative_basis):
    base=Path(base);key=document['capture_key'];old_file=base/PARENT_OUTPUT/(key+'.json');old=read(old_file)
    need(sha(base/document['source_path'])==document['source_sha256']==old['source_sha256'],'original asset-source PDF unchanged')
    need(old['capture_key']==key and old['instrument']==document['instrument']
         and old['fiscal_year']==document['effective_fiscal_year'],'source/case identity')
    result={'capture_key':key,'instrument':document['instrument'],'fiscal_year':document['effective_fiscal_year'],
        'source_sha256':document['source_sha256'],'parent_case_sha256':sha(old_file),'GP_source_status':old['status'],
        'page_count':old['page_count'],'asset_report':None,'historical_arrival_verified':False,
        'financial_version_history_complete':False,'investment_factor_admitted':False}
    if not(old['cover_code_consistent'] and old['cover_annual_year_consistent']):
        return {**result,'status':'COVER_IDENTITY_UNVERIFIED','source_strategy':'IDENTITY_FAILURE_RETAINED'}
    if old['source_observations']:
        observations=old['source_observations'];balances={}
        for o in observations:
            need(o['record_id']==digest({k:v for k,v in o.items() if k!='record_id'})
                 and o['instrument']==document['instrument'] and o['payload']['document_sha256']==document['source_sha256']
                 and o['payload']['announcement_id']==document['announcement_id'],'audited original GP observation identity')
            balances[o['fiscal_end']]=copy.deepcopy(o['payload']['cells']['total_assets'])
        report=assets.make_report(document['instrument'],document['effective_fiscal_year'],document['day'],
            document['captured_at_utc'],document['source_sha256'],document['announcement_id'],balances)
        return {**result,'status':SUPPORTED,'source_strategy':'REUSE_AUDITED_GP_ASSET_CELLS',
                'source_GP_record_ids':[o['record_id'] for o in observations],'asset_report':report}
    folder=INITIAL_CACHE if document['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER_CACHE
    need(document['source_phase'] in ('INITIAL_AUTHENTICATED_PAGE_CACHE','LATER_ORIGINAL_PDF'),'known cached source phase')
    cache_file=base/folder/(key+'.pages.json');cache=read(cache_file);pages=cache['pages']
    need(cache['source_sha256']==document['source_sha256'] and cache['extractor']=='pypdf6.10.0'
         and len(pages)==old['page_count'] and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}==old['all_extracted_page_text_sha256'],
         'authenticated cached pages required for standalone balance extraction')
    result.update(source_strategy='BALANCE_ONLY_FROM_AUTHENTICATED_CACHE',source_page_cache_sha256=sha(cache_file))
    try:
        balances=assets.parse_balance_only(pages,document['effective_fiscal_year'],normative_basis=normative_basis)
        report=assets.make_report(document['instrument'],document['effective_fiscal_year'],document['day'],
            document['captured_at_utc'],document['source_sha256'],document['announcement_id'],balances)
        return {**result,'status':SUPPORTED,'asset_report':report}
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':'ASSET_SOURCE_SCHEMA_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc)}


def run(base,root,membership,request_file,expected_sha,*,executor_factory=ProcessPoolExecutor,worker=inspect_one):
    out=base/OUTPUT;need(not out.exists(),'fresh standalone assets output; no retry/resume')
    req,paths=verify(base,root,membership,request_file,expected_sha)
    paths={**paths,'frozen_request':request_file};expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,path in paths.items():need(sha(path)==expected[key],'asset input before '+key)
    out.mkdir(parents=True);results,submitted,primary,mismatches,persistence={ },[],None,[],[]
    try:
        write_once(out/'input-before.json',expected)
        with executor_factory(max_workers=WORKERS) as pool:
            for start in range(0,len(req['documents']),WORKERS):
                batch=req['documents'][start:start+WORKERS];futures=[]
                for doc in batch:
                    submitted.append(doc['capture_key']);futures.append(pool.submit(worker,str(base),doc,req['normative_basis']))
                for doc,future in zip(batch,futures):
                    case=future.result();key=doc['capture_key']
                    need(case['capture_key']==key and case['source_sha256']==doc['source_sha256'],'asset worker source identity')
                    write_once(out/(key+'.json'),case);results[key]=case
                    print('standalone assets',len(results),'/',len(req['documents']),key,case['status'],flush=True)
        old=read(base/PARENT_OUTPUT/'case_results.json');preserved=0;preserved_cells=0
        for key,case in old.items():
            if not case['source_observations']:continue
            original={o['fiscal_end']:o['payload']['cells']['total_assets'] for o in case['source_observations']}
            need(results[key]['asset_report'] is not None and results[key]['asset_report']['payload']['balances']==original,
                 'old audited asset cells changed or lost')
            preserved+=1;preserved_cells+=len(original)
        need(preserved==req['old_GP_supported_reports'] and preserved_cells==req['old_GP_asset_cell_count'],'complete old-asset control counts')
        reports=[c['asset_report'] for c in results.values() if c['asset_report'] is not None]
        visibility={}
        for year in (2024,2025):
            for mode in (assets.OBSERVED,assets.RECONSTRUCTED):
                source=assets.visible_reports(reports,f'{year}-12-31T15:05:00+08:00',mode=mode)
                visibility[str(year)+'/'+mode]={'count':len(source['reports']),'record_ids':[r['record_id'] for r in source['reports']],
                    'all_visible_supported_editions_not_latest_eligibility':True}
        write_once(out/'visibility-checks.json',visibility)
    except BaseException as exc:primary=exc
    finally:
        for key,path in paths.items():
            try:
                if sha(path)!=expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches}
        terminal={'completed_documents':len(results),'submitted_keys':submitted,
            'pending':[d['capture_key'] for d in req['documents'] if d['capture_key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence:primary.add_note('asset-source persistence: '+str(persistence))
        raise primary
    need(not mismatches and not persistence and len(results)==len(req['documents']),'complete unchanged source and terminal required')
    summary={'status':'ALL1236_STANDALONE_TOTAL_ASSET_SOURCE_COMPLETE_NOT_FACTOR_ADMITTED',
        'request_sha256':expected_sha,'document_count':len(results),'cohort_count':req['cohort_count'],
        'status_counts':dict(Counter(c['status'] for c in results.values())),
        'source_strategy_counts':dict(Counter(c['source_strategy'] for c in results.values())),
        'asset_report_count':len(reports),'asset_cell_count':sum(len(r['payload']['balances']) for r in reports),
        'paired_explicit_annual_report_count':sum(len(r['payload']['balances'])==2 for r in reports),
        'old_GP_supported_reports_preserved':preserved,'old_GP_asset_cells_preserved':preserved_cells,
        'newly_supported_documents':[k for k,c in results.items() if c['asset_report'] is not None and not old[k]['source_observations']],
        'observed_pre2026_reports_visible':sum(v['count'] for k,v in visibility.items() if k.endswith('/OBSERVED')),
        'input_count':len(paths),'all_inputs_unchanged':True,'original_PDF_text_decodings_performed':0,
        'historical_arrival_verified':False,'financial_version_history_complete':False,'investment_factor_admitted':False,
        'asset_growth_values_or_stock_ranks_computed':False,'portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();summary=run(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],
        Path(a.membership_file).resolve(),Path(a.request).resolve(),a.expected_request_sha256)
    print(summary['status'],summary['status_counts'],flush=True)


if __name__=='__main__':main()
