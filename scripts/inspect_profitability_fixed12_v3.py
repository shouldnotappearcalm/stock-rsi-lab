"""Frozen V3 source context, same36 originals, no investment selection or ROI."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path

from scripts import inspect_profitability_fixed12_v2 as predecessor
from stock_rsi import annual_profitability_v3 as grammar
from stock_rsi.annual_profitability import make_observation

original = predecessor.original
pdfs = predecessor.pdfs
read, need, file_sha, write_once = predecessor.read, predecessor.need, predecessor.file_sha, predecessor.write_once
pages_from_pdf = predecessor.pages_from_pdf
PREVIOUS_REQUEST = 'experiments/qlib/profitability-fixed12-v2-request.json'
PREVIOUS_SHA = 'e57cd393d7b9e3ae44f7ba681d34cb984f86ce8104c3f80b0035ed41dc75a6c0'
PREVIOUS_AUDIT = 'experiments/qlib/profitability-fixed12-v2-source-cell-audit.json'
PREVIOUS_AUDIT_CODE = 'experiments/qlib/audit_sources/2026-10-22-profitability-v2-source-cells.py'
METHODS = (*predecessor.METHODS, 'src/stock_rsi/annual_profitability_v3.py', 'scripts/inspect_profitability_fixed12_v3.py')
PUBLIC = (PREVIOUS_REQUEST, PREVIOUS_AUDIT, PREVIOUS_AUDIT_CODE,
    'experiments/qlib/profitability-fixed12-v2-results.json',
    'docs/research/profitability-fixed12-v2-results-2026-10-22.md',
    'docs/research/profitability-fixed12-v3-plan-2026-10-22.md',
    'experiments/qlib/profitability-fixed12-v3-source-context-review.json',
    'tests/fixtures/annual-profitability-v3-real-context-excerpts.json',
    'tests/test_annual_profitability_v3.py', 'tests/test_profitability_schema_v3_inspection.py')
OUTPUT = 'gross-profitability-fixed12-source-context-v3-20261022'
STATUS = 'FROZEN_BEFORE_SAME36_SOURCE_CONTEXT_V3_INSPECTION'


def inspect_document(document, pages):
    identity = grammar.document_identity(pages, document['instrument'], document['fiscal_year'])
    base = {'capture_key': document['capture_key'], 'instrument': document['instrument'],
        'fiscal_year': document['fiscal_year'], 'source_sha256': document['source_sha256'],
        'page_count': len(pages), 'parser_contract': grammar.CONTRACT, 'identity_evidence': identity,
        'cover_code_consistent': identity['code_consistent'],
        'cover_annual_year_consistent': identity['annual_year_consistent'],
        'financial_version_history_complete': False, 'historical_arrival_verified': False,
        'economic_sector_compatibility_verified': False, 'manual_numeric_visual_review_complete': False,
        'investment_factor_admitted': False}
    if not (identity['code_consistent'] and identity['annual_year_consistent']):
        return {**base, 'status': 'COVER_IDENTITY_UNVERIFIED', 'source_observations': []}
    try:
        cells = grammar.parse_consolidated_tables(pages, document['fiscal_year'])
        observations = [make_observation(document['instrument'], document['fiscal_year'], period,
            document['day'], document['captured_at_utc'], document['source_sha256'],
            document['announcement_id'], fields) for period, fields in cells.items()]
        return {**base, 'status': 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW',
                'source_observations': observations}
    except (ValueError, KeyError, ArithmeticError) as exc:
        return {**base, 'status': 'SOURCE_SCHEMA_UNSUPPORTED', 'error_type': type(exc).__name__,
                'error': str(exc), 'source_observations': []}


def required_paths(base, root):
    paths = predecessor.required_paths(base, root)
    for name in (*METHODS, *PUBLIC):
        paths['repo/' + name] = root / name
    for name in read(root / PREVIOUS_AUDIT)['all41_output_sha256']:
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe V2 source artifact')
        paths['source/' + predecessor.OUTPUT + '/' + name] = base / predecessor.OUTPUT / name
    for record in read(root / 'experiments/qlib/profitability-fixed12-v3-source-context-review.json')['records']:
        name = 'gross-profitability-v3-format-evidence-20261022/' + record['capture_key'] + '-p' + str(record['physical_page']) + '.png'
        need(file_sha(base / name) == record['render_PNG_sha256'], 'source-context reviewed image identity')
        paths['source/' + name] = base / name
    return paths


def verify(base, root, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha, 'frozen source context v3 request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['document_count'] == 36
         and req['parser_contract'] == grammar.CONTRACT and req['pypdf_version'] == '6.10.0'
         and req['max_pages_per_document'] == 1200 and req['code_window_pages'] == 20
         and req['annual_title_window_pages'] == 5 and req['max_fiscal_header_lines'] == 8
         and req['max_monetary_row_lines'] == 4 and req['max_primary_section_pages'] == 40
         and req['opening_Jan1_comparative_not_relabelled_as_prior_Dec31'] is True
         and req['financial_numeric_source_parsing_permitted'] is True
         and req['security_ranking_or_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False, 'same36 source-only V3 context contract')
    paths = required_paths(base, root)
    pdfs.initial.check(paths, req['input_sha256'])
    need(set(req['method_sha256']) == set(METHODS), 'complete V3 source-method closure')
    for name, digest in req['method_sha256'].items():
        need(digest == req['input_sha256']['repo/' + name], 'source method/input identity agreement')
    _, _, documents = predecessor.verify(base, root, root / PREVIOUS_REQUEST, PREVIOUS_SHA)
    check = read(root / PREVIOUS_AUDIT)
    need(check['status'] == 'PASS_SEPARATE_V2_SUPPORTED_SOURCE_CELL_CHECK_NOT_FACTOR_ADMISSION'
         and check['audit_code_sha256'] == file_sha(root / PREVIOUS_AUDIT_CODE)
         and check['request_sha256'] == PREVIOUS_SHA, 'V2 source audit identity')
    directory = base / predecessor.OUTPUT
    actual = {str(p.relative_to(directory)): file_sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    need(actual == check['all41_output_sha256'] and len(actual) == 41, 'all V2 outputs preserved')
    need(file_sha(root / 'experiments/qlib/profitability-fixed12-v2-results.json') == file_sha(directory / 'summary.json'),
         'actual prior source results equal public record')
    return req, paths, documents


def run(base, root, request_file, expected_sha, out):
    need(out.resolve() == (base / OUTPUT).resolve() and not out.exists(), 'fixed fresh schema output required')
    req,paths,documents = verify(base, root, request_file, expected_sha)
    paths = {**paths,'frozen_source_request':Path(request_file)}
    expected = {**req['input_sha256'],'frozen_source_request':expected_sha}
    pdfs.initial.check(paths,expected)
    out.mkdir(parents=True)
    results,primary,mismatches,persistence_errors = {},None,[],[]
    try:
        write_once(out / 'input-before.json',expected)
        for document in documents:
            key = document['capture_key']
            pages = pages_from_pdf(base / document['source_path'])
            result = inspect_document(document,pages)
            result['all_extracted_page_text_sha256'] = {str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)}
            results[key] = result
            write_once(out / (key + '.json'),result)
            print('financial source v3',key,result['status'],flush=True)
        prior_cases = read(base / predecessor.OUTPUT / 'case_results.json')
        for key, before in prior_cases.items():
            if before['status'] != 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW':
                continue
            after = results[key]
            need(after['status'] == before['status'], 'old supported report lost: ' + key)
            current = {o['fiscal_end']: o for o in after['source_observations']}
            for observation in before['source_observations']:
                need(observation['fiscal_end'] in current, 'old fiscal observation lost: ' + key)
                for field, cell in observation['payload']['cells'].items():
                    for name in ('value_CNY', 'literal', 'column_index', 'page', 'statement', 'fiscal_end'):
                        need(current[observation['fiscal_end']]['payload']['cells'][field][name] == cell[name],
                             'old cell numerical/source coordinate changed: ' + key)
    except BaseException as exc:
        primary = exc
    finally:
        for key,path in paths.items():
            try:
                if file_sha(path) != expected[key]: mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input':key,'reason':type(exc).__name__})
        post = {'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,
                'source_request_rehashed_after_processing':True}
        terminal = {'status':'FIXED36_SCHEMA_V3_INSPECTION_TERMINAL','completed_documents':len(results),
                    'pending':[d['capture_key'] for d in documents if d['capture_key'] not in results],
                    'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
                    'postcheck':post,'persistence_errors':persistence_errors,'portfolio_returns_computed':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try: write_once(out/name,value)
            except BaseException as exc: persistence_errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence_errors: primary.add_note('Schema terminal persistence errors: '+str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors,'schema input changed or terminal persistence failed')
    need(len(results)==36,'all fixed36 source classifications required')
    counts = dict(Counter(r['status'] for r in results.values()))
    per_code = {code:{str(r['fiscal_year']):{'capture_key':r['capture_key'],'status':r['status'],'error':r.get('error')}
                      for r in results.values() if r['instrument']==code}
                for code in dict.fromkeys(d['instrument'] for d in documents)}
    summary = {'status':'FIXED36_SOURCE_CONTEXT_V3_COMPLETE_NOT_FACTOR_ADMITTED',
        'parser_contract':grammar.CONTRACT,'request_sha256':expected_sha,'documents':36,'issuer_count':12,'status_counts':counts,'coverage_by_issuer':per_code,
        'source_observations':sum(len(r['source_observations']) for r in results.values()),
        'all3_year_supported_parse_issuers':sum(all(r['status']=='SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW' for r in years.values()) for years in per_code.values()),
        'input_count':len(paths),'all_inputs_unchanged':True,'original_parser_or_financial_source_changed':False,
        'financial_version_history_complete':False,'manual_numeric_visual_review_complete':False,
        'economic_sector_compatibility_verified':False,'historical_arrival_verified':False,
        'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    prior = read(base / predecessor.OUTPUT / 'case_results.json')
    summary['old_status_counts'] = dict(Counter(r['status'] for r in prior.values()))
    summary['transitions_by_document'] = {key: {'old': prior[key]['status'], 'v2': value['status']} for key,value in results.items()}
    summary['all_V2_supported_numeric_cells_and_coordinates_preserved'] = True
    summary['current_only_opening_balance_reports'] = [key for key,r in results.items() if len(r['source_observations']) == 1]
    write_once(out/'summary.json',summary)
    return summary



def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args(argv)
    base, root = Path(a.source_root).resolve(), Path(__file__).resolve().parents[1]
    result = run(base, root, Path(a.request), a.expected_request_sha256, base / OUTPUT)
    print(result['status'], result['status_counts'], flush=True)


if __name__ == '__main__':
    main()
