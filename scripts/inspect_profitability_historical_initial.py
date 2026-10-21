"""Whole initial filing cohort inspection with frozen V4 grammar; no investment test.

Four foreground child processes read original PDFs. All page text stays local,
so subsequent grammar reviews need not repeatedly decode hundreds of PDFs.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
from pathlib import Path
import sys

from scripts import capture_profitability_historical_initial_pdfs as capture
from scripts import inspect_profitability_fixed12_v4 as fixed

read, need, file_sha, write_once = capture.read, capture.need, capture.file_sha, capture.write_once
PDF_REQUEST = 'experiments/qlib/profitability-historical394-initial-pdf-request.json'
PDF_SHA = '26d0f6c56eb336edb5cf87133c3bd1f58b92a2e90b0e755e75e52b83b1fad402'
AUDIT = 'experiments/qlib/profitability-historical394-initial-pdf-byte-audit.json'
AUDIT_CODE = 'experiments/qlib/audit_sources/2026-10-22-historical-initial-pdf-byte-audit.py'
OUTPUT = 'gross-profitability-historical394-initial2022-schema-20261022'
STATUS = 'FROZEN_BEFORE_ALL408_INITIAL_REPORT_CONTENT_INSPECTION'
METHODS = tuple(dict.fromkeys((*capture.METHODS, *fixed.METHODS,
    'src/stock_rsi/calendar.py', 'src/stock_rsi/__init__.py',
    'scripts/inspect_profitability_historical_initial.py')))
PUBLIC = (PDF_REQUEST, AUDIT, AUDIT_CODE,
    'experiments/qlib/profitability-fixed12-v4-results.json',
    'experiments/qlib/profitability-fixed12-v4-source-cell-audit.json',
    'docs/research/profitability-historical394-initial-schema-plan-2026-10-22.md',
    'tests/test_profitability_historical_initial_inspection.py')
WORKERS = 4


def required_paths(base, root, membership):
    paths = {**fixed.required_paths(base, root), **capture.required_paths(base, root, membership)}
    for name in (*METHODS, *PUBLIC):
        paths['repo/' + name] = root / name
    audit = read(root / AUDIT)
    for name in audit['all_output_sha256']:
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe captured output path')
        paths['source/' + capture.OUTPUT + '/' + name] = base / capture.OUTPUT / name
    for document in audit['source_document_records']:
        name = document['source_path']
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe original source path')
        paths['source/' + name] = base / name
    previous = read(root / 'experiments/qlib/profitability-fixed12-v4-source-cell-audit.json')
    for name, digest in previous['all41_output_sha256'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe earlier content artifact')
        path = base / fixed.OUTPUT / name
        need(file_sha(path) == digest, 'prior V4 content result unchanged')
        paths['source/' + fixed.OUTPUT + '/' + name] = path
    return paths


def verify(base, root, membership, request_file, expected_sha):
    need(sys.version.split()[0] == '3.12.14', 'registered PDF Python3.12.14 runtime required')
    need(file_sha(request_file) == expected_sha, 'frozen initial content request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT
         and req['document_count'] == 408 and req['source_issuer_count'] == 391
         and req['source_range_issuer_count'] == 394
         and req['parser_contract'] == fixed.grammar.CONTRACT
         and req['pypdf_version'] == '6.10.0' and req['max_pages_per_document'] == 1200
         and req['python_version'] == '3.12.14'
         and req['workers'] == WORKERS and req['max_outstanding_documents'] == WORKERS
         and req['retain_all_page_text_locally'] is True
         and req['financial_numeric_source_parsing_permitted'] is True
         and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,
         'all408 content-only inspection scope required')
    paths = required_paths(base, root, membership)
    capture.initial.check(paths, req['input_sha256'])
    need(set(req['method_sha256']) == set(METHODS), 'complete inspection method closure')
    for name, digest in req['method_sha256'].items():
        need(digest == req['input_sha256']['repo/' + name], 'method/input agreement')
    capture.verify(base, root, membership, root / PDF_REQUEST, PDF_SHA)
    audit = read(root / AUDIT)
    need(audit['status'].startswith('PASS_') and audit['request_sha256'] == PDF_SHA
         and audit['audit_code_sha256'] == file_sha(root / AUDIT_CODE), 'original byte audit identity')
    folder = base / capture.OUTPUT
    actual = {str(p.relative_to(folder)):file_sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
    need(actual == audit['all_output_sha256'] and len(actual) == 1998, 'complete original byte corpus')
    documents = read(folder / 'documents.json')
    need(documents == audit['source_document_records'] == req['documents'] and len(documents) == 408
         and len({d['capture_key'] for d in documents}) == 408, 'all original editions required')
    for d in documents:
        need(d['fiscal_year'] == 2022 and '2023-01-01' <= d['day'] <= '2023-12-31'
             and file_sha(base / d['source_path']) == d['source_sha256'], 'original FY2022 source identity')
    return req, paths, documents


def inspect_one(base, document):
    path = Path(base) / document['source_path']
    need(file_sha(path) == document['source_sha256'], 'worker source hash changed')
    pages = fixed.pages_from_pdf(path)
    result = fixed.inspect_document(document, pages)
    result['all_extracted_page_text_sha256'] = {
        str(i + 1): hashlib.sha256(page.encode()).hexdigest() for i, page in enumerate(pages)}
    return result, pages


def preserve_old_supported(results, old_results):
    """Same source bytes and grammar must retain all old fiscal cells/coordinates."""
    count = 0
    for key, before in old_results.items():
        if key not in results or before['status'] != 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW':
            continue
        after = results[key]
        need(after['status'] == before['status'], 'old supported initial report lost: ' + key)
        need(after['source_sha256'] == before['source_sha256']
             and after['source_observations'] == before['source_observations'],
             'old initial source observations changed: ' + key)
        count += 1
    return count


def run(base, root, membership, request_file, expected_sha, out, *,
        executor_factory=ProcessPoolExecutor, worker=inspect_one):
    need(out.resolve() == (base / OUTPUT).resolve() and not out.exists(), 'fresh initial content output; no retry/resume')
    req, paths, documents = verify(base, root, membership, request_file, expected_sha)
    paths = {**paths, 'frozen_source_request': Path(request_file)}
    expected = {**req['input_sha256'], 'frozen_source_request': expected_sha}
    capture.initial.check(paths, expected)
    out.mkdir(parents=True)
    results, submitted, primary, mismatches, persistence_errors = {}, [], None, [], []
    old_preserved = 0
    try:
        write_once(out / 'input-before.json', expected)
        # A batch barrier caps outstanding work to four. Workers never write;
        # ordered main-process persistence makes every complete case auditable.
        with executor_factory(max_workers=WORKERS) as pool:
            for start in range(0, len(documents), WORKERS):
                batch = documents[start:start + WORKERS]
                write_once(out / ('batch-' + str(start // WORKERS).zfill(3) + '.json'),
                           {'capture_keys': [d['capture_key'] for d in batch]})
                futures = []
                for document in batch:
                    submitted.append(document['capture_key'])
                    futures.append(pool.submit(worker, str(base), document))
                for document, future in zip(batch, futures):
                    result, pages = future.result()
                    key = document['capture_key']
                    need(result['capture_key'] == key and result['source_sha256'] == document['source_sha256'],
                         'worker result identity')
                    need(result['page_count'] == len(pages) and 1 <= len(pages) <= 1200
                         and result['all_extracted_page_text_sha256'] == {
                             str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)},
                         'complete extracted physical pages')
                    write_once(out / (key + '.pages.json'), {'source_sha256': document['source_sha256'],
                               'extractor': 'pypdf6.10.0', 'pages': pages})
                    write_once(out / (key + '.json'), result)
                    results[key] = result
                    print('initial financial content', len(results), '/', len(documents), key, result['status'], flush=True)
        old_preserved = preserve_old_supported(results, read(base / fixed.OUTPUT / 'case_results.json'))
    except BaseException as exc:
        primary = exc
    finally:
        for key, path in paths.items():
            try:
                if file_sha(path) != expected[key]: mismatches.append({'input':key, 'reason':'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input':key, 'reason':type(exc).__name__})
        post = {'all_inputs_unchanged':not mismatches, 'count':len(paths), 'mismatches':mismatches,
                'source_request_rehashed_after_processing':True}
        terminal = {'status':'HISTORICAL_INITIAL_CONTENT_INSPECTION_TERMINAL',
            'completed_documents':len(results), 'submitted_keys':submitted,
            'pending':[d['capture_key'] for d in documents if d['capture_key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__, 'message':str(primary)},
            'postcheck':post, 'persistence_errors':persistence_errors, 'portfolio_returns_computed':False}
        for name, value in (('case_results.json',results), ('input-postcheck.json',post), ('terminal.json',terminal)):
            try: write_once(out / name, value)
            except BaseException as exc: persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors: primary.add_note('Content inspection persistence errors: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors and len(results) == len(documents), 'complete unchanged source inspection')
    summary = {'status':'ALL_INITIAL_CONTENT_INSPECTED_NOT_FACTOR_ADMITTED', 'request_sha256':expected_sha,
        'parser_contract':fixed.grammar.CONTRACT, 'document_count':len(results),
        'source_issuer_count':len({r['instrument'] for r in results.values()}),
        'source_range_issuer_count':req['source_range_issuer_count'], 'remaining_source_gap_issuers':req['remaining_source_gap_issuers'],
        'status_counts':dict(Counter(r['status'] for r in results.values())),
        'unsupported_error_counts':dict(Counter(r['error'] for r in results.values() if 'error' in r)),
        'source_observation_count':sum(len(r['source_observations']) for r in results.values()),
        'supported_source_issuer_count':len({r['instrument'] for r in results.values() if r['source_observations']}),
        'old_supported_initial_reports_preserved':old_preserved,
        'input_count':len(paths), 'all_inputs_unchanged':True,
        'page_text_retained_locally':True, 'financial_version_history_complete':False,
        'manual_numeric_visual_review_complete':False, 'economic_sector_compatibility_verified':False,
        'historical_arrival_verified':False, 'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False, 'objective_achieved':False}
    write_once(out / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'membership-file', 'request', 'expected-request-sha256'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args(argv)
    base, root = Path(a.source_root).resolve(), Path(__file__).resolve().parents[1]
    result = run(base, root, Path(a.membership_file).resolve(), Path(a.request), a.expected_request_sha256, base / OUTPUT)
    print(result['status'], result['status_counts'], flush=True)


if __name__ == '__main__': main()
