"""Whole1236 source inspection:408 old text caches,828 original PDFs, no ROI.
Four foreground workers, bounded batches, immutable outputs and old-cell guards.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
from pathlib import Path
import sys
from scripts import inspect_profitability_historical_v5 as initial
from scripts import capture_profitability_later_annual_pdfs as later
from stock_rsi import annual_profitability_v6 as grammar
from stock_rsi.annual_profitability import make_observation

read,need,file_sha,write_once = initial.read,initial.need,initial.file_sha,initial.write_once
INITIAL_REQUEST = 'experiments/qlib/profitability-historical394-v5-request.json'
INITIAL_SHA = 'd0b8aacab7d881d8a0e5aebb515a8f0652180c3afee9251299e703dc52c4493a'
INITIAL_AUDIT = 'experiments/qlib/profitability-historical394-v5-source-audit.json'
INITIAL_CODE = 'experiments/qlib/audit_sources/2026-10-22-profitability-v5-source-cells.py'
LATER_REQUEST = 'experiments/qlib/profitability-historical394-later-pdf-request.json'
LATER_SHA = 'a4771483875d5b322ebdc3db17cb7bdeec2b52328e95e38e23d387db77992f52'
LATER_AUDIT = 'experiments/qlib/profitability-historical394-later-pdf-byte-audit.json'
LATER_CODE = 'experiments/qlib/audit_sources/2026-10-22-later-annual-pdf-byte-audit.py'
LEGAL = 'experiments/qlib/profitability-cas19-currency-evidence-research.json'
COVER = 'experiments/qlib/profitability-later-yearless-cover-review.json'
FIXTURE = 'tests/fixtures/annual-profitability-v6-CAS-compliance-excerpts.json'
OUTPUT = 'gross-profitability-all1236-source-v6-20261022'
STATUS = 'FROZEN_BEFORE_ALL1236_CAS19_V6_FINANCIAL_SOURCE_INSPECTION'
METHODS = tuple(dict.fromkeys((*initial.METHODS,*later.METHODS,
    'src/stock_rsi/annual_profitability_v6.py','scripts/inspect_profitability_all_v6.py')))
PUBLIC = (INITIAL_REQUEST,INITIAL_AUDIT,INITIAL_CODE,LATER_REQUEST,LATER_AUDIT,LATER_CODE,LEGAL,COVER,FIXTURE,
    'docs/research/profitability-all1236-v6-plan-2026-10-22.md','tests/test_annual_profitability_v6.py','tests/test_profitability_all_v6.py')
WORKERS = 4


def required_paths(base, root, membership):
    paths = {**initial.required_paths(base,root,membership),**later.required_paths(base,root,membership)}
    for name in (*METHODS,*PUBLIC):paths['repo/'+name] = root/name
    for audit_name,folder in ((INITIAL_AUDIT,initial.OUTPUT),(LATER_AUDIT,later.OUTPUT)):
        for name,digest in read(root/audit_name)['all_output_sha256'].items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe old corpus output')
            path = base/folder/name;need(file_sha(path) == digest,'old original/result bytes changed')
            paths['source/'+folder+'/'+name] = path
    legal_dir = base/read(root/LEGAL)['local_archive_relative_source_root']
    for path in sorted(legal_dir.rglob('*')):
        if path.is_file():paths['source/'+str(path.relative_to(base))] = path
    for path in sorted((base/'gross-profitability-later-yearless-cover-review-20261022').rglob('*')):
        if path.is_file():paths['source/'+str(path.relative_to(base))] = path
    for record in read(root/FIXTURE)['records']:
        name = record['render_path_relative_source_root'];need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe reviewed CAS image')
        need(file_sha(base/name) == record['render_png_sha256'],'reviewed CAS source page')
        paths['source/'+name] = base/name
    return paths


def documents(base, root):
    first = read(base/initial.predecessor.capture.OUTPUT/'documents.json')
    second = read(base/later.OUTPUT/'documents.json');cover = read(root/COVER)
    result = []
    for phase,items in (('INITIAL_AUTHENTICATED_PAGE_CACHE',first),('LATER_ORIGINAL_PDF',second)):
        for d in items:
            year = d['fiscal_year']
            if year is None:
                need(d['capture_key'] == cover['capture_key'] and d['source_sha256'] == cover['source_sha256']
                     and cover['identity_evidence']['code_consistent'] and cover['identity_evidence']['annual_year_consistent']
                     and cover['manually_viewed_original_cover_render'] is True,'yearless source needs exact original-cover evidence')
                year = cover['fiscal_year_from_original_cover']
            need(type(year) is int and 1900 <= year <= 2024 and d['day'] <= '2025-12-31','pre2026 fiscal/publication source scope')
            result.append({**d,'source_phase':phase,'effective_fiscal_year':year,
                           'year_resolved_from_cover_sidecar':d['fiscal_year'] is None})
    need(len(result) == 1236 and len({d['announcement_id'] for d in result}) == 1236
         and len(first) == 408 and len(second) == 828,'complete initial+later source corpus')
    return result


def verify(base, root, membership, request_file, expected_sha):
    need(sys.version.split()[0] == '3.12.14','registered Python3.12.14 source runtime')
    need(file_sha(request_file) == expected_sha,'frozen whole-corpus V6 request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['document_count'] == 1236
         and req['initial_page_cache_count'] == 408 and req['later_PDF_extraction_count'] == 828
         and req['source_range_issuer_count'] == 394 and req['workers'] == req['maximum_outstanding_documents'] == 4
         and req['pypdf_version'] == '6.10.0' and req['max_pages_per_document'] == 1200
         and req['parser_contract'] == grammar.CONTRACT and req['normative_basis'] == grammar.CAS19_REFERENCE
         and req['regulatory_currency_inference_is_not_literal_CNY_evidence'] is True
         and req['financial_numeric_source_parsing_permitted'] is True and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'complete1236 V6 source-only contract')
    paths = required_paths(base,root,membership);later.metadata.initial.check(paths,req['input_sha256'])
    need(set(req['method_sha256']) == set(METHODS),'complete source method closure')
    for name,digest in req['method_sha256'].items():need(digest == req['input_sha256']['repo/'+name],'method/input identity')
    first_req,_,_ = initial.verify(base,root,membership,root/INITIAL_REQUEST,INITIAL_SHA)
    second_req,_ = later.verify(base,root,membership,root/LATER_REQUEST,LATER_SHA)
    for name,code,old_req,old_sha in ((INITIAL_AUDIT,INITIAL_CODE,first_req,INITIAL_SHA),(LATER_AUDIT,LATER_CODE,second_req,LATER_SHA)):
        audit = read(root/name)
        need(audit['audit_code_sha256'] == file_sha(root/code) and audit['request_sha256'] == old_sha
             and audit['all_input_sha256'] == {**old_req['input_sha256'],'frozen_source_request':old_sha},'original whole source audits required')
    legal = read(root/LEGAL);archive = base/legal['local_archive_relative_source_root']
    for source in legal['official_source_records']:
        folder = archive/source['source_id']
        for filename,key in (('body.bin','body_sha256'),('response.json','response_sha256'),('text.txt','text_sha256')):
            need(file_sha(folder/filename) == source[key],'archived official accounting text identity')
    norm = grammar.CAS19_REFERENCE
    need(file_sha(archive/'cas19/body.bin') == norm['archived_body_sha256'] and file_sha(archive/'cas19/text.txt') == norm['archived_text_sha256']
         and norm['normative_phrase'] in (archive/'cas19/text.txt').read_text()
         and '2006年03月09日' in (archive/'cas19/text.txt').read_text(),'historical official CAS19 statement and publisher date')
    docs = documents(base,root);need(req['documents'] == docs,'same complete source documents and cover-only year resolution')
    return req,paths,docs


def inspect_pages(document, pages, normative_basis):
    year = document['effective_fiscal_year'];identity = grammar.document_identity(pages,document['instrument'],year)
    result = {'capture_key':document['capture_key'],'instrument':document['instrument'],'fiscal_year':year,
        'raw_capture_fiscal_year':document['fiscal_year'],'year_resolved_from_cover_sidecar':document['year_resolved_from_cover_sidecar'],
        'source_phase':document['source_phase'],'source_sha256':document['source_sha256'],'page_count':len(pages),
        'parser_contract':grammar.CONTRACT,'identity_evidence':identity,'cover_code_consistent':identity['code_consistent'],
        'cover_annual_year_consistent':identity['annual_year_consistent'],
        'all_extracted_page_text_sha256':{str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)},
        'financial_version_history_complete':False,'historical_arrival_verified':False,'economic_sector_compatibility_verified':False,
        'manual_numeric_visual_review_complete':False,'investment_factor_admitted':False}
    if not (identity['code_consistent'] and identity['annual_year_consistent']):
        return {**result,'status':'COVER_IDENTITY_UNVERIFIED','source_observations':[]}
    try:
        cells = grammar.parse_consolidated_tables(pages,year,normative_basis=normative_basis)
        observations = [make_observation(document['instrument'],year,period,document['day'],document['captured_at_utc'],
            document['source_sha256'],document['announcement_id'],fields) for period,fields in cells.items()]
        return {**result,'status':'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW','source_observations':observations}
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':'SOURCE_SCHEMA_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc),'source_observations':[]}


def inspect_one(base, document, normative_basis):
    import pypdf
    need(pypdf.__version__ == '6.10.0','registered original-text extractor')
    base = Path(base);need(file_sha(base/document['source_path']) == document['source_sha256'],'original source body changed')
    if document['source_phase'] == 'INITIAL_AUTHENTICATED_PAGE_CACHE':
        folder = base/initial.predecessor.OUTPUT;key = document['capture_key']
        before,cache = read(folder/(key+'.json')),read(folder/(key+'.pages.json'));pages = cache['pages']
        need(cache['source_sha256'] == document['source_sha256'] and cache['extractor'] == 'pypdf6.10.0'
             and before['all_extracted_page_text_sha256'] == {str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)},'original cached pages unchanged')
        return inspect_pages(document,pages,normative_basis),None
    need(document['source_phase'] == 'LATER_ORIGINAL_PDF','known source phase')
    try:pages = initial.predecessor.fixed.pages_from_pdf(base/document['source_path'])
    except (ValueError,pypdf.errors.PdfReadError,pypdf.errors.DependencyError) as exc:
        return {'capture_key':document['capture_key'],'instrument':document['instrument'],'fiscal_year':document['effective_fiscal_year'],
            'raw_capture_fiscal_year':document['fiscal_year'],'year_resolved_from_cover_sidecar':document['year_resolved_from_cover_sidecar'],
            'source_phase':document['source_phase'],'source_sha256':document['source_sha256'],'page_count':None,
            'parser_contract':grammar.CONTRACT,'status':'SOURCE_PDF_EXTRACTION_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc),
            'source_observations':[],'all_extracted_page_text_sha256':{},'investment_factor_admitted':False,
            'financial_version_history_complete':False,'historical_arrival_verified':False,'economic_sector_compatibility_verified':False,
            'manual_numeric_visual_review_complete':False},None
    return inspect_pages(document,pages,normative_basis),pages


def baseline_cases(base):
    return [read(base/initial.OUTPUT/'case_results.json'),read(base/initial.predecessor.fixed.OUTPUT/'case_results.json')]


def run(base, root, membership, request_file, expected_sha, out, *, executor_factory=ProcessPoolExecutor, worker=inspect_one):
    need(out.resolve() == (base/OUTPUT).resolve() and not out.exists(),'fresh V6 source output only; no retry/resume')
    req,paths,docs = verify(base,root,membership,request_file,expected_sha)
    paths = {**paths,'frozen_source_request':Path(request_file)};expected = {**req['input_sha256'],'frozen_source_request':expected_sha}
    later.metadata.initial.check(paths,expected);out.mkdir(parents=True)
    results,submitted,primary,mismatches,persistence_errors,caches,preserved = {},[],None,[],[],0,set()
    try:
        write_once(out/'input-before.json',expected)
        with executor_factory(max_workers=WORKERS) as pool:
            for start in range(0,len(docs),WORKERS):
                batch = docs[start:start+WORKERS]
                write_once(out/('batch-'+str(start//WORKERS).zfill(3)+'.json'),{'capture_keys':[d['capture_key'] for d in batch]})
                futures = []
                for d in batch:submitted.append(d['capture_key']);futures.append(pool.submit(worker,str(base),d,req['normative_basis']))
                for d,future in zip(batch,futures):
                    result,pages = future.result();key = d['capture_key']
                    need(result['capture_key'] == key and result['source_sha256'] == d['source_sha256'],'worker source identity')
                    if pages is not None:
                        need(d['source_phase'] == 'LATER_ORIGINAL_PDF' and result['page_count'] == len(pages)
                             and result['all_extracted_page_text_sha256'] == {str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)},'new source page-text conservation')
                        write_once(out/(key+'.pages.json'),{'source_sha256':d['source_sha256'],'extractor':'pypdf6.10.0','pages':pages});caches += 1
                    results[key] = result;write_once(out/(key+'.json'),result)
                    print('V6 whole source',len(results),'/',len(docs),key,result['status'],flush=True)
        for old in baseline_cases(base):
            initial.predecessor.preserve_old_supported(results,old)
            preserved |= {key for key,c in old.items() if c['source_observations'] and key in results}
    except BaseException as exc:primary = exc
    finally:
        for key,path in paths.items():
            try:
                if file_sha(path) != expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post = {'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        terminal = {'status':'WHOLE1236_V6_SOURCE_INSPECTION_TERMINAL','completed_documents':len(results),'submitted_keys':submitted,
            'pending':[d['capture_key'] for d in docs if d['capture_key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence_errors,'portfolio_returns_computed':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence_errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence_errors:primary.add_note('V6 terminal persistence errors: '+str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors and len(results) == len(docs),'complete unchanged source classification')
    inferred = [key for key,c in results.items() if any(e['scope'] == 'INFERRED_FROM_EXPLICIT_CAS_COMPLIANCE_AND_CAS19_ART4'
        for o in c['source_observations'] for cell in o['payload']['cells'].values() for e in cell['currency_scope_evidence'])]
    summary = {'status':'WHOLE1236_V6_SOURCE_INSPECTED_NOT_FACTOR_ADMITTED','request_sha256':expected_sha,
        'parser_contract':grammar.CONTRACT,'document_count':len(results),'source_range_issuer_count':req['source_range_issuer_count'],
        'status_counts':dict(Counter(c['status'] for c in results.values())),
        'status_counts_by_fiscal_year':{str(y):dict(Counter(c['status'] for c in results.values() if c['fiscal_year'] == y)) for y in sorted({c['fiscal_year'] for c in results.values()})},
        'status_counts_by_exchange':{e:dict(Counter(c['status'] for c in results.values() if c['instrument'].startswith(e))) for e in ('SH','SZ')},
        'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if 'error' in c)),
        'source_observation_count':sum(len(c['source_observations']) for c in results.values()),
        'supported_source_issuer_count':len({c['instrument'] for c in results.values() if c['source_observations']}),
        'issuers_with_supported_current_reports_2022_2023_2024':sorted({d['instrument'] for d in docs if all(any(c['instrument'] == d['instrument'] and c['fiscal_year'] == y and c['source_observations'] for c in results.values()) for y in (2022,2023,2024))}),
        'regulatory_currency_inference_documents':inferred,'new_page_caches_written':caches,
        'old_supported_reports_preserved_identically':len(preserved),'input_count':len(paths),'all_inputs_unchanged':True,
        'source_gaps_remain_in_full_dated_range':True,'financial_version_history_complete':False,'historical_arrival_verified':False,
        'manual_numeric_visual_review_complete':False,'economic_sector_compatibility_verified':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'summary.json',summary)
    return summary


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    a = p.parse_args();base,root = Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result = run(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['status_counts'],flush=True)


if __name__=='__main__':main()
