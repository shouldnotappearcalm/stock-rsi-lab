"""Replay all1236 authenticated source caches through bounded V7 headers.
No new network/PDF text extraction, strategy, rankings or returns.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import hashlib
import sys
from scripts import inspect_profitability_all_v6 as prior
from stock_rsi import annual_profitability_v7 as grammar

read,need,file_sha,write_once=prior.read,prior.need,prior.file_sha,prior.write_once
PREVIOUS_OUTPUT=prior.OUTPUT
INITIAL_CACHE_OUTPUT=prior.initial.predecessor.OUTPUT
REQUEST='experiments/qlib/profitability-all1236-v6-request.json'
REQUEST_SHA='fc7ddecfac53f0d478180ecac7013f1dc6fe8460cc2be41fed7571d0418870f9'
AUDIT='experiments/qlib/profitability-all1236-v6-source-audit.json'
AUDIT_CODE='experiments/qlib/audit_sources/2026-10-22-profitability-all1236-v6-source-cells.py'
FIXTURE='tests/fixtures/annual-profitability-v7-header-format-excerpts.json'
EVIDENCE='gross-profitability-v7-header-evidence-20261022'
OUTPUT='gross-profitability-all1236-header-v7-20261022'
STATUS='FROZEN_BEFORE_ALL1236_CURRENT_DATE_ANCHORED_HEADER_V7_SOURCE_INSPECTION'
METHODS=tuple(dict.fromkeys((*prior.METHODS,'src/stock_rsi/annual_profitability_v7.py','scripts/inspect_profitability_all_v7.py')))
PUBLIC=(REQUEST,AUDIT,AUDIT_CODE,FIXTURE,'experiments/qlib/profitability-all1236-v6-results.json',
        'experiments/qlib/profitability-all1236-v6-checker-validation-history.json',
        'docs/research/profitability-all1236-v7-plan-2026-10-22.md','tests/test_annual_profitability_v7.py','tests/test_profitability_all_v7.py')
WORKERS=4


def required_paths(base,root,membership):
    paths=prior.required_paths(base,root,membership)
    for name in (*METHODS,*PUBLIC):paths['repo/'+name]=root/name
    for name,value in read(root/AUDIT)['all_output_sha256'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe previous output')
        path=base/PREVIOUS_OUTPUT/name;need(file_sha(path)==value,'unchanged V6 output')
        paths['source/'+PREVIOUS_OUTPUT+'/'+name]=path
    for path in sorted((base/EVIDENCE).rglob('*')):
        if path.is_file():paths['source/'+str(path.relative_to(base))]=path
    return paths


def verify(base,root,membership,request_file,expected_sha):
    import pypdf
    need(sys.version.split()[0]=='3.12.14' and pypdf.__version__=='6.10.0','registered runtime and original-cache extractor')
    need(file_sha(request_file)==expected_sha,'frozen V7 source request changed')
    req=read(request_file)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['document_count']==1236
         and req['source_range_issuer_count']==394 and req['old_supported_report_count']==665
         and req['workers']==req['maximum_outstanding_documents']==4 and req['parser_contract']==grammar.CONTRACT
         and req['normative_basis']==grammar.CAS19_REFERENCE and req['new_PDF_text_decodings_permitted'] is False
         and req['generic_opening_balance_date_must_remain_unresolved'] is True
         and req['ranking_or_portfolio_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'complete V7 source-only contract')
    paths=required_paths(base,root,membership);prior.later.metadata.initial.check(paths,req['input_sha256'])
    need(set(req['method_sha256'])==set(METHODS),'complete V7 method closure')
    for name,value in req['method_sha256'].items():need(value==req['input_sha256']['repo/'+name],'method/input binding')
    old_req,_,docs=prior.verify(base,root,membership,root/REQUEST,REQUEST_SHA)
    audit=read(root/AUDIT)
    need(audit['status']=='PASS_SEPARATE_ALL1236_V6_CORPUS_AND_SOURCE_CELL_CHECK_NOT_FACTOR_ADMISSION'
         and audit['audit_code_sha256']==file_sha(root/AUDIT_CODE) and audit['request_sha256']==REQUEST_SHA
         and audit['all_input_sha256']=={**old_req['input_sha256'],'frozen_source_request':REQUEST_SHA}
         and len(audit['all_output_sha256'])==2378 and audit['old_supported_reports_preserved_identically']==182,'complete prior corpus QA')
    need(file_sha(root/'experiments/qlib/profitability-all1236-v6-results.json')==file_sha(base/PREVIOUS_OUTPUT/'summary.json')
         and req['documents']==docs and len({d['announcement_id'] for d in docs})==1236,'same complete original corpus')
    old=read(base/PREVIOUS_OUTPUT/'case_results.json')
    need(set(old)=={d['capture_key'] for d in docs} and sum(bool(c['source_observations']) for c in old.values())==665,'all665 old successes protected')
    indexed={d['capture_key']:d for d in docs}
    for r in read(root/FIXTURE)['records']:
        need(r['capture_key'] in indexed and indexed[r['capture_key']]['source_sha256']==r['source_sha256']
             and old[r['capture_key']]['all_extracted_page_text_sha256'][str(r['physical_page'])]==r['page_text_sha256']
             and r['header_layout_manually_viewed'] is True and file_sha(base/r['png_path'])==r['render_png_sha256'],'reviewed original header page identity')
    return req,paths,docs


def inspect_one(base,document,normative_basis):
    base=Path(base);key=document['capture_key'];old=read(base/PREVIOUS_OUTPUT/(key+'.json'))
    need(file_sha(base/document['source_path'])==document['source_sha256']==old['source_sha256'],'original PDF bytes unchanged')
    folder=base/INITIAL_CACHE_OUTPUT if document['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else base/PREVIOUS_OUTPUT
    cache=read(folder/(key+'.pages.json'));pages=cache['pages']
    hashes={str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}
    need(cache['source_sha256']==document['source_sha256'] and cache['extractor']=='pypdf6.10.0'
         and hashes==old['all_extracted_page_text_sha256'] and len(pages)==old['page_count'],'authenticated cached page text required')
    result={k:v for k,v in old.items() if k not in ('error','error_type','source_observations')}
    result.update(parser_contract=grammar.CONTRACT,V6_source_status=old['status'],V6_source_error=old.get('error'),
                  source_page_cache_reused=True,investment_factor_admitted=False)
    if not(old['cover_code_consistent'] and old['cover_annual_year_consistent']):
        return {**result,'status':'COVER_IDENTITY_UNVERIFIED','source_observations':[]}
    try:
        cells=grammar.parse_consolidated_tables(pages,document['effective_fiscal_year'],normative_basis=normative_basis)
        observations=[grammar.original.make_observation(document['instrument'],document['effective_fiscal_year'],period,
            document['day'],document['captured_at_utc'],document['source_sha256'],document['announcement_id'],fields)
            for period,fields in cells.items()]
        return {**result,'status':'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW','source_observations':observations}
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':'SOURCE_SCHEMA_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc),'source_observations':[]}


def run(base,root,membership,request_file,expected_sha,out,*,executor_factory=ProcessPoolExecutor,worker=inspect_one):
    need(out.resolve()==(base/OUTPUT).resolve() and not out.exists(),'fresh V7 source output only; no retry/resume')
    req,paths,docs=verify(base,root,membership,request_file,expected_sha)
    paths={**paths,'frozen_source_request':Path(request_file)};expected={**req['input_sha256'],'frozen_source_request':expected_sha}
    prior.later.metadata.initial.check(paths,expected);out.mkdir(parents=True)
    results,submitted,primary,mismatches,persistence_errors,preserved={},[],None,[],[],0
    try:
        write_once(out/'input-before.json',expected)
        with executor_factory(max_workers=WORKERS) as pool:
            for start in range(0,len(docs),WORKERS):
                batch=docs[start:start+WORKERS]
                write_once(out/('batch-'+str(start//WORKERS).zfill(3)+'.json'),{'capture_keys':[d['capture_key'] for d in batch]})
                futures=[]
                for d in batch:submitted.append(d['capture_key']);futures.append(pool.submit(worker,str(base),d,req['normative_basis']))
                for d,future in zip(batch,futures):
                    c=future.result();key=d['capture_key']
                    need(c['capture_key']==key and c['source_sha256']==d['source_sha256'],'worker source identity')
                    results[key]=c;write_once(out/(key+'.json'),c)
                    print('V7 whole cached source',len(results),'/',len(docs),key,c['status'],flush=True)
        old=read(base/PREVIOUS_OUTPUT/'case_results.json')
        need(set(results)==set(old),'all source keys retained')
        for key,c in old.items():
            if c['source_observations']:
                need(results[key]['source_observations']==c['source_observations'] and results[key]['source_sha256']==c['source_sha256']
                     and results[key]['all_extracted_page_text_sha256']==c['all_extracted_page_text_sha256'],'old supported report altered or lost')
                preserved+=1
        need(preserved==req['old_supported_report_count'],'complete old success control count')
    except BaseException as exc:primary=exc
    finally:
        for key,path in paths.items():
            try:
                if file_sha(path)!=expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        terminal={'status':'WHOLE1236_V7_SOURCE_INSPECTION_TERMINAL','completed_documents':len(results),'submitted_keys':submitted,
            'pending':[d['capture_key'] for d in docs if d['capture_key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence_errors,'portfolio_returns_computed':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence_errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence_errors:primary.add_note('V7 terminal persistence errors: '+str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors and len(results)==len(docs),'complete unchanged cached source inspection')
    old=read(base/PREVIOUS_OUTPUT/'case_results.json')
    generic=[k for k,c in results.items() if any(o['payload']['cells']['total_assets'].get('comparative_date_is_unresolved') is True for o in c['source_observations'])]
    summary={'status':'WHOLE1236_V7_SOURCE_INSPECTED_NOT_FACTOR_ADMITTED','request_sha256':expected_sha,'parser_contract':grammar.CONTRACT,
        'document_count':len(results),'source_range_issuer_count':req['source_range_issuer_count'],'status_counts':dict(Counter(c['status'] for c in results.values())),
        'status_counts_by_fiscal_year':{str(y):dict(Counter(c['status'] for c in results.values() if c['fiscal_year']==y)) for y in sorted({c['fiscal_year'] for c in results.values()})},
        'status_counts_by_exchange':{e:dict(Counter(c['status'] for c in results.values() if c['instrument'].startswith(e))) for e in ('SH','SZ')},
        'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if 'error' in c)),
        'source_observation_count':sum(len(c['source_observations']) for c in results.values()),
        'supported_source_issuer_count':len({c['instrument'] for c in results.values() if c['source_observations']}),
        'issuers_with_supported_current_reports_2022_2023_2024':sorted({c['instrument'] for c in results.values() if all(any(x['instrument']==c['instrument'] and x['fiscal_year']==y and x['source_observations'] for x in results.values()) for y in (2022,2023,2024))}),
        'newly_supported_documents':[k for k,c in results.items() if c['source_observations'] and not old[k]['source_observations']],
        'generic_balance_current_only_documents':generic,'old_supported_reports_preserved_identically':preserved,
        'input_count':len(paths),'all_inputs_unchanged':True,'all_cached_text_reused':True,'original_PDF_text_decodings_performed':0,
        'source_gaps_remain_in_full_dated_range':True,'financial_version_history_complete':False,'historical_arrival_verified':False,
        'manual_numeric_visual_review_complete':False,'economic_sector_compatibility_verified':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();base,root=Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result=run(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['status_counts'],flush=True)


if __name__=='__main__':main()
