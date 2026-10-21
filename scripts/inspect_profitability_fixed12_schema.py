"""Read-only fixed36 filing identity/schema feasibility, no ranking or returns.
Keeps the original narrow parser unchanged; unsupported tables remain explicit.
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import re

from scripts import capture_profitability_annual_pdfs as pdfs
from stock_rsi.annual_profitability import make_observation, parse_consolidated_tables

read, need, file_sha, write_once = pdfs.read, pdfs.need, pdfs.file_sha, pdfs.write_once
PDF_REQUEST = 'experiments/qlib/profitability-fixed12-annual-pdf-request.json'
PDF_SHA = '578b2a18c63944b3c833037608dd1beb493d2fb8a90b89570142b1f4b15ba18f'
PDF_AUDIT = 'experiments/qlib/profitability-fixed12-annual-pdf-byte-audit.json'
PDF_AUDIT_CODE = 'experiments/qlib/audit_sources/2026-10-22-profitability-annual-pdf-byte-audit.py'
OUTPUT = 'gross-profitability-fixed12-schema-20261022'
STATUS = 'FROZEN_BEFORE_FIXED36_FINANCIAL_SOURCE_SCHEMA_INSPECTION'
METHODS = (*pdfs.METHODS, 'src/stock_rsi/annual_profitability.py', 'src/stock_rsi/data.py',
           'src/stock_rsi/models.py', 'src/stock_rsi/time.py', 'scripts/inspect_profitability_fixed12_schema.py')
PUBLIC = (PDF_REQUEST, PDF_AUDIT, PDF_AUDIT_CODE,
          'docs/research/profitability-fixed12-schema-plan-2026-10-22.md')


def inspect_document(document, pages):
    # Preserve line boundaries so a stock code followed by the next line's
    # annual year cannot become a fabricated ten-digit token.
    cover = re.sub(r'[^\S\r\n]+', '', '\n'.join(pages[:5]))
    code, year = document['instrument'][2:], document['fiscal_year']
    cover_code = bool(re.search(r'(?:公司|股票|证券)\s*代码[：:]?\s*' + re.escape(code) + r'(?!\d)', cover))
    cover_year = bool(re.search(str(year) + r'\s*年?\s*年度报告', cover))
    headers = {title: [i+1 for i,p in enumerate(pages) if any(re.sub(r'\s+', '',line)==title for line in p.splitlines())]
               for title in ('合并资产负债表', '母公司资产负债表', '合并利润表', '母公司利润表')}
    base = {'capture_key': document['capture_key'], 'instrument': document['instrument'], 'fiscal_year': year,
            'source_sha256': document['source_sha256'], 'page_count': len(pages),
            'cover_code_consistent': cover_code, 'cover_annual_year_consistent': cover_year,
            'literal_statement_header_pages': headers, 'financial_version_history_complete': False,
            'historical_arrival_verified': False, 'economic_sector_compatibility_verified': False,
            'manual_numeric_visual_review_complete': False, 'investment_factor_admitted': False}
    if not (cover_code and cover_year):
        return {**base, 'status': 'COVER_IDENTITY_UNVERIFIED', 'source_observations': []}
    try:
        cells = parse_consolidated_tables(pages, year)
        observations = [make_observation(document['instrument'], year, period, document['day'],
                         document['captured_at_utc'], document['source_sha256'], document['announcement_id'], data)
                        for period,data in cells.items()]
        return {**base, 'status': 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW', 'source_observations': observations}
    except (ValueError, KeyError, ArithmeticError) as exc:
        return {**base, 'status': 'SOURCE_SCHEMA_UNSUPPORTED', 'error_type': type(exc).__name__, 'error': str(exc),
                'source_observations': []}


def pages_from_pdf(path):
    import pypdf
    need(pypdf.__version__ == '6.10.0', 'fixed pypdf source extractor required')
    reader = pypdf.PdfReader(path)
    need(1 <= len(reader.pages) <= 1200, 'source page count outside1200page cap')
    return [page.extract_text() or '' for page in reader.pages]


def required_paths(base, root):
    paths = pdfs.required_paths(base, root)
    for name in (*METHODS, *PUBLIC):
        paths['repo/' + name] = root / name
    for name in read(root / PDF_AUDIT)['all178_output_sha256']:
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe PDF capture artifact path')
        paths['source/' + pdfs.OUTPUT + '/' + name] = base / pdfs.OUTPUT / name
    return paths


def verify(base, root, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha, 'frozen financial schema request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['document_count'] == 36
         and req['pypdf_version'] == '6.10.0' and req['max_pages_per_document'] == 1200
         and req['financial_numeric_source_parsing_permitted'] is True
         and req['security_ranking_or_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,
         'fixed36 source feasibility inspection only')
    need(set(req['method_sha256']) == set(METHODS), 'complete fixed parser and source methods required')
    paths = required_paths(base, root)
    pdfs.initial.check(paths, req['input_sha256'])
    for name,digest in req['method_sha256'].items():
        need(digest == req['input_sha256']['repo/' + name], 'schema method/input identities disagree')
    pdfs.verify(base, root, root / PDF_REQUEST, PDF_SHA)
    audit = read(root / PDF_AUDIT)
    need(audit['status'] == 'PASS_SEPARATE_FIXED12_ANNUAL_PDF_BYTE_AUDIT' and audit['request_sha256'] == PDF_SHA
         and audit['audit_code_sha256'] == file_sha(root / PDF_AUDIT_CODE), 'source byte audit identity required')
    directory = base / pdfs.OUTPUT
    actual = {str(p.relative_to(directory)): file_sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    need(actual == audit['all178_output_sha256'] and len(actual) == 178
         and file_sha(directory / 'summary.json') == audit['summary_sha256'], 'all audited PDF output bytes required')
    documents = read(directory / 'documents.json')
    need(documents == audit['source_document_records'] and len(documents) == 36, 'complete fixed source records required')
    for d in documents:
        need(d['fiscal_year'] in (2022,2023,2024) and d['day'] <= '2025-12-31'
             and not Path(d['source_path']).is_absolute() and '..' not in Path(d['source_path']).parts
             and file_sha(base / d['source_path']) == d['source_sha256'], 'original pre2026 financial file identity required')
    return req,paths,documents


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
            print('financial schema',key,result['status'],flush=True)
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
        terminal = {'status':'FIXED36_SCHEMA_INSPECTION_TERMINAL','completed_documents':len(results),
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
    summary = {'status':'FIXED36_FINANCIAL_SOURCE_SCHEMA_INSPECTION_COMPLETE_NOT_FACTOR_ADMITTED',
        'request_sha256':expected_sha,'documents':36,'issuer_count':12,'status_counts':counts,'coverage_by_issuer':per_code,
        'source_observations':sum(len(r['source_observations']) for r in results.values()),
        'all3_year_supported_parse_issuers':sum(all(r['status']=='SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW' for r in years.values()) for years in per_code.values()),
        'input_count':len(paths),'all_inputs_unchanged':True,'original_parser_or_financial_source_changed':False,
        'financial_version_history_complete':False,'manual_numeric_visual_review_complete':False,
        'economic_sector_compatibility_verified':False,'historical_arrival_verified':False,
        'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'summary.json',summary)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('source-root','request','expected-request-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);base,root=Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result=run(base,root,Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['status_counts'],flush=True)
if __name__=='__main__':main()
