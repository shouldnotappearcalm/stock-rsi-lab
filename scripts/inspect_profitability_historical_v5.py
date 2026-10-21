"""V5 source-format inspection over all408 authenticated original page caches."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
from scripts import inspect_profitability_historical_initial as predecessor
from stock_rsi import annual_profitability_v5 as grammar
from stock_rsi.annual_profitability import make_observation

read, need, file_sha, write_once = predecessor.read, predecessor.need, predecessor.file_sha, predecessor.write_once
PREVIOUS_REQUEST = 'experiments/qlib/profitability-historical394-initial-schema-request.json'
PREVIOUS_SHA = 'ce6f7699c24df53aa31c3519ffd474e6b4e705f718bcc4684549e1454bb81309'
AUDIT = 'experiments/qlib/profitability-historical394-initial-schema-audit.json'
AUDIT_CODE = 'experiments/qlib/audit_sources/2026-10-22-historical-initial-content-audit.py'
FIXTURE = 'tests/fixtures/annual-profitability-v5-source-format-excerpts.json'
OUTPUT = 'gross-profitability-historical394-initial2022-v5-20261022'
STATUS = 'FROZEN_BEFORE_ALL408_CURRENCY_AND_NOTE_V5_SOURCE_INSPECTION'
METHODS = (*predecessor.METHODS,'src/stock_rsi/annual_profitability_v5.py','scripts/inspect_profitability_historical_v5.py')
PUBLIC = (PREVIOUS_REQUEST,AUDIT,AUDIT_CODE,FIXTURE,
    'experiments/qlib/profitability-historical394-initial-schema-results.json',
    'experiments/qlib/profitability-historical394-initial-schema-coverage.json',
    'experiments/qlib/profitability-historical394-note-layout-review.json',
    'experiments/qlib/profitability-historical394-currency-context-followup.json',
    'docs/research/profitability-historical394-v5-plan-2026-10-22.md',
    'tests/test_annual_profitability_v5.py','tests/test_profitability_historical_v5.py')


def required_paths(base, root, membership):
    paths = predecessor.required_paths(base,root,membership)
    for name in (*METHODS,*PUBLIC): paths['repo/'+name] = root/name
    for name,expected in read(root/AUDIT)['all_output_sha256'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe original page-cache artifact')
        path = base/predecessor.OUTPUT/name
        need(file_sha(path) == expected,'original full408 output unchanged')
        paths['source/'+predecessor.OUTPUT+'/'+name] = path
    for record in read(root/FIXTURE)['records']:
        name = record['render_path_relative_source_root']
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe reviewed image path')
        need(file_sha(base/name) == record['render_png_sha256'],'reviewed original page render')
        paths['source/'+name] = base/name
    return paths


def verify(base, root, membership, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha,'frozen source V5 request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['document_count'] == 408
         and req['source_issuer_count'] == 391 and req['source_range_issuer_count'] == 394
         and req['parser_contract'] == grammar.CONTRACT and req['input_page_caches_reused_without_reextracting'] is True
         and req['all_V4_supported_observations_must_be_identical'] is True
         and req['financial_numeric_source_parsing_permitted'] is True
         and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'whole408 source-only V5 repair')
    paths = required_paths(base,root,membership)
    predecessor.capture.initial.check(paths,req['input_sha256'])
    need(set(req['method_sha256']) == set(METHODS),'complete V5 method closure')
    for name,digest in req['method_sha256'].items():
        need(digest == req['input_sha256']['repo/'+name],'method/input identity')
    before,_,documents = predecessor.verify(base,root,membership,root/PREVIOUS_REQUEST,PREVIOUS_SHA)
    audit = read(root/AUDIT)
    need(audit['status'] == 'PASS_SEPARATE_INITIAL_SOURCE_PAGE_CACHE_AND_CELL_CHECK_NOT_FACTOR_ADMISSION'
         and audit['audit_code_sha256'] == file_sha(root/AUDIT_CODE) and audit['request_sha256'] == PREVIOUS_SHA
         and audit['all_input_sha256'] == {**before['input_sha256'],'frozen_source_request':PREVIOUS_SHA},'complete original source audit identity')
    folder = base/predecessor.OUTPUT
    need({str(p.relative_to(folder)):file_sha(p) for p in sorted(folder.rglob('*')) if p.is_file()} == audit['all_output_sha256'],
         'all923 original source outputs retained')
    need(documents == req['documents'],'same408 source candidates, versions and original order')
    return req,paths,documents


def inspect_cached_document(base, document):
    key = document['capture_key'];folder = Path(base)/predecessor.OUTPUT
    before,cache = read(folder/(key+'.json')),read(folder/(key+'.pages.json'))
    pages = cache['pages']
    need(cache['extractor'] == 'pypdf6.10.0' and cache['source_sha256'] == document['source_sha256'] == before['source_sha256']
         and 1 <= len(pages) == before['page_count'] <= 1200 and before['all_extracted_page_text_sha256'] == {
             str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)},'original source/page text identity')
    identity = grammar.document_identity(pages,document['instrument'],document['fiscal_year'])
    need(identity == before['identity_evidence'],'issuer/year source evidence unchanged')
    result = {k:v for k,v in before.items() if k not in ('status','source_observations','error','error_type','parser_contract')}
    result.update(parser_contract=grammar.CONTRACT,V4_source_status=before['status'],V4_source_error=before.get('error'))
    if not (identity['code_consistent'] and identity['annual_year_consistent']):
        return {**result,'status':'COVER_IDENTITY_UNVERIFIED','source_observations':[]}
    try:
        cells = grammar.parse_consolidated_tables(pages,document['fiscal_year'])
        observations = [make_observation(document['instrument'],document['fiscal_year'],period,
            document['day'],document['captured_at_utc'],document['source_sha256'],document['announcement_id'],fields)
            for period,fields in cells.items()]
        return {**result,'status':'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW','source_observations':observations}
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':'SOURCE_SCHEMA_UNSUPPORTED','source_observations':[],
                'error_type':type(exc).__name__,'error':str(exc)}


def run(base, root, membership, request_file, expected_sha, out, *, inspector=None):
    need(out.resolve() == (base/OUTPUT).resolve() and not out.exists(),'fresh V5 source output only; no retry/resume')
    req,paths,documents = verify(base,root,membership,request_file,expected_sha)
    paths = {**paths,'frozen_source_request':Path(request_file)}
    expected = {**req['input_sha256'],'frozen_source_request':expected_sha}
    predecessor.capture.initial.check(paths,expected)
    out.mkdir(parents=True)
    results,primary,mismatches,persistence_errors,preserved = {},None,[],[],0
    try:
        write_once(out/'input-before.json',expected)
        inspect = inspect_cached_document if inspector is None else inspector
        for document in documents:
            key = document['capture_key'];result = inspect(base,document)
            need(result['capture_key'] == key and result['source_sha256'] == document['source_sha256'],'source case identity')
            results[key] = result;write_once(out/(key+'.json'),result)
            print('V5 source cache',len(results),'/',len(documents),key,result['status'],flush=True)
        preserved = predecessor.preserve_old_supported(results,read(base/predecessor.OUTPUT/'case_results.json'))
    except BaseException as exc:
        primary = exc
    finally:
        for key,path in paths.items():
            try:
                if file_sha(path) != expected[key]: mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc: mismatches.append({'input':key,'reason':type(exc).__name__})
        post = {'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        terminal = {'status':'HISTORICAL_ALL408_V5_SOURCE_TERMINAL','completed_documents':len(results),
            'pending':[d['capture_key'] for d in documents if d['capture_key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence_errors,'portfolio_returns_computed':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try: write_once(out/name,value)
            except BaseException as exc: persistence_errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence_errors: primary.add_note('V5 source persistence errors: '+str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors and len(results) == len(documents),'complete unchanged V5 source inspection')
    summary = {'status':'ALL408_V5_SOURCE_FORMAT_INSPECTED_NOT_FACTOR_ADMITTED','request_sha256':expected_sha,
        'parser_contract':grammar.CONTRACT,'document_count':len(results),'source_issuer_count':len({d['instrument'] for d in documents}),
        'source_range_issuer_count':req['source_range_issuer_count'],'remaining_source_gap_issuers':req['remaining_source_gap_issuers'],
        'status_counts':dict(Counter(r['status'] for r in results.values())),
        'status_counts_by_exchange':{e:dict(Counter(r['status'] for r in results.values() if r['instrument'].startswith(e))) for e in ('SH','SZ')},
        'unsupported_error_counts':dict(Counter(r['error'] for r in results.values() if 'error' in r)),
        'source_observation_count':sum(len(r['source_observations']) for r in results.values()),
        'supported_source_issuer_count':len({r['instrument'] for r in results.values() if r['source_observations']}),
        'all_V4_supported_reports_preserved_identically':preserved,
        'newly_supported_documents':[key for key,r in results.items() if r['source_observations'] and r['V4_source_status'] != r['status']],
        'current_only_opening_balance_documents':[key for key,r in results.items() if len(r['source_observations']) == 1],
        'input_count':len(paths),'all_inputs_unchanged':True,'page_caches_reused_without_reextracting':True,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'manual_numeric_visual_review_complete':False,
        'economic_sector_compatibility_verified':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'summary.json',summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'): parser.add_argument('--'+name,required=True)
    a = parser.parse_args();base,root = Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result = run(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['status_counts'],flush=True)


if __name__ == '__main__': main()
