"""Separately frozen fixed12 annual PDFs, exact URLs after audited metadata.
Retains two original cached PDFs and downloads34 declared resources once each.
No PDF numeric parsing, ranking, accounts, strategy search or source substitution.
"""
import argparse
from pathlib import Path
import re
import time

from scripts import capture_profitability_initial_annual_metadata as initial
from scripts.immutable_http_capture import ImmutableHttpCapture, need, file_sha, write_once

read = initial.read
META_REQUEST = 'experiments/qlib/profitability-fixed12-initial-metadata-request.json'
META_SHA = 'b17246f79621f8581e2ff0c652643e7d51e46a0cb33a19329c1f04a210c58172'
META_AUDIT = 'experiments/qlib/profitability-fixed12-initial-metadata-audit.json'
META_CODE = 'experiments/qlib/audit_sources/2026-10-22-profitability-initial-metadata-audit.py'
OLD_PRIMARY = 'fundamental-primary-documents-20261017'
OLD_CAPTURE = 'experiments/qlib/fundamental-primary-documents-capture-manifest.json'
OUTPUT = 'gross-profitability-fixed12-annual-pdfs-20261022'
STATUS = 'FROZEN_BEFORE_FIXED12_ANNUAL_PDF_CAPTURE'
METHODS = (*initial.METHODS, 'scripts/capture_profitability_annual_pdfs.py')
PUBLIC = (META_REQUEST, META_AUDIT, META_CODE, OLD_CAPTURE,
          'docs/research/profitability-fixed12-pdf-plan-2026-10-22.md')


def metadata_artifacts(base, root):
    req, _ = initial.verify(base, root, root / META_REQUEST, META_SHA)
    audit = read(root / META_AUDIT)
    need(audit['status'] == 'PASS_SEPARATE_FIXED12_INITIAL2022_METADATA_AUDIT'
         and audit['request_sha256'] == META_SHA and audit['audit_code_sha256'] == file_sha(root / META_CODE)
         and audit['all23_input_sha256'] == {**req['input_sha256'], 'frozen_source_request': META_SHA}
         and len(audit['all65_output_sha256']) == 65, 'complete initial metadata audit required')
    directory = base / initial.OUTPUT
    actual = {str(p.relative_to(directory)): file_sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    need(actual == audit['all65_output_sha256'] and file_sha(directory / 'summary.json') == audit['summary_sha256'],
         'audited initial metadata output bytes changed')
    summary = read(directory / 'summary.json')
    need(summary['successful_issuers'] == 12 and summary['logical_attempts'] == 12, 'all12 initial sources required')
    return req, audit, summary


def derive_documents(base, root):
    req, audit, summary = metadata_artifacts(base, root)
    inventory = read(root / initial.INVENTORY)
    cache = read(root / OLD_CAPTURE)['documents']
    cached = {d['announcement_id']: d for d in cache}
    documents, ids = [], set()
    for code in req['codes']:
        initial_rows = summary['results_by_code'][code]['selected_full_reports']
        need(initial_rows == audit['selected_full_reports_by_code'][code] and len(initial_rows) == 1,
             'this exact PDF request requires one initial full report per issuer')
        later = []
        for row in inventory['documents_by_code'][code]['annual_metadata_rows']:
            if any(word in row['title'] for word in ('摘要', '英文', '可视')):
                continue
            match = re.search(r'(2023|2024)年?年度报告(?:全文|（全文）|\(全文\))?$', re.sub(r'\s+', '', row['title']))
            need(match is not None, 'unregistered later full-report title')
            later.append({**row, 'instrument': code, 'fiscal_year': int(match.group(1))})
        rows = [*initial_rows, *later]
        need(len(rows) == 3 and {r['fiscal_year'] for r in rows} == {2022, 2023, 2024}, 'exact three annual documents per fixed issuer')
        for row in sorted(rows, key=lambda r: r['fiscal_year']):
            identity = row['announcement_id']
            need(identity not in ids and row['day'] <= '2025-12-31' and row.get('code', code[2:]) == code[2:]
                 and re.fullmatch(r'finalpage/\d{4}-\d{2}-\d{2}/' + re.escape(identity) + r'\.[pP][dD][fF]', row['pdf_path']),
                 'unique safe fixed document identity required')
            ids.add(identity)
            record = {k: row[k] for k in ('title', 'day', 'timestamp_ms', 'announcement_id', 'pdf_path', 'fiscal_year')}
            record.update(instrument=code, url='https://static.cninfo.com.cn/' + row['pdf_path'],
                          capture_key=code + '-' + str(row['fiscal_year']) + '-' + identity)
            if identity in cached:
                old = cached[identity]
                need(old['instrument'] == code and old['day'] == row['day']
                     and old['statDate'] == str(row['fiscal_year']) + '-12-31'
                     and old['pdf_path'] == row['pdf_path'] and Path(old['file']).name == old['file'], 'old PDF metadata identity changed')
                path = base / OLD_PRIMARY / old['file']
                need(file_sha(path) == old['sha256'], 'authenticated old PDF changed')
                record.update(source_kind='REUSE_AUTHENTICATED_ORIGINAL_PDF', source_path=OLD_PRIMARY + '/' + old['file'],
                              source_sha256=old['sha256'], captured_at_utc=old['captured_at_utc'])
            else:
                record['source_kind'] = 'FRESH_FROZEN_PDF_GET'
            documents.append(record)
    need(len(documents) == 36 and sum(d['source_kind'].startswith('REUSE') for d in documents) == 2,
         'exact36 documents and2 cache reuses required')
    return documents


def resources(documents):
    return {d['capture_key']: {'method': 'GET', 'url': d['url'], 'payload': None}
            for d in documents if d['source_kind'] == 'FRESH_FROZEN_PDF_GET'}


def required_paths(base, root):
    paths = initial.required_paths(base, root)
    for name in (*METHODS, *PUBLIC):
        paths['repo/' + name] = root / name
    audit = read(root / META_AUDIT)
    for name in audit['all65_output_sha256']:
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe original metadata artifact path')
        paths['source/' + initial.OUTPUT + '/' + name] = base / initial.OUTPUT / name
    for document in read(root / OLD_CAPTURE)['documents']:
        need(Path(document['file']).name == document['file'], 'safe authenticated cached PDF filename')
        paths['source/' + OLD_PRIMARY + '/' + document['file']] = base / OLD_PRIMARY / document['file']
    return paths


def verify(base, root, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha, 'frozen PDF request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['metadata_request_sha256'] == META_SHA
         and req['max_logical_attempts'] == 34 and req['per_resource_attempts'] == 1
         and req['max_body_bytes'] == 26214400 and req['timeout_seconds'] == 20
         and req['minimum_request_interval_seconds'] == 0.2 and req['document_count'] == 36
         and req['cache_reuse_count'] == 2 and req['financial_numeric_parsing_permitted'] is False
         and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False, 'one fixed36-document capture request required')
    need(set(req['method_sha256']) == set(METHODS), 'complete frozen PDF methods required')
    paths = required_paths(base, root)
    initial.check(paths, req['input_sha256'])
    for name, digest in req['method_sha256'].items():
        need(digest == req['input_sha256']['repo/' + name], 'PDF method/input identities disagree')
    documents = derive_documents(base, root)
    need(req['documents'] == documents and req['resources'] == resources(documents)
         and len(req['resources']) == 34, 'exact independently sourced document URLs required')
    return req, paths


def capture(base, root, request_file, expected_sha, out, *, opener=None, pause=time.sleep):
    need(out.resolve() == (base / OUTPUT).resolve() and not out.exists(), 'fixed fresh PDF output only; no retry/resume')
    req, paths = verify(base, root, request_file, expected_sha)
    paths = {**paths, 'frozen_source_request': Path(request_file)}
    expected = {**req['input_sha256'], 'frozen_source_request': expected_sha}
    initial.check(paths, expected)
    out.mkdir(parents=True)
    results, primary, mismatches, persistence_errors, journal = {}, None, [], [], None
    try:
        write_once(out / 'input-before.json', expected)
        kwargs = {} if opener is None else {'opener': opener}
        journal = ImmutableHttpCapture(out / 'http', req['resources'], max_attempts=34,
                                       max_body_bytes=26214400, **kwargs)
        consecutive = 0
        for document in req['documents']:
            key = document['capture_key']
            try:
                if document['source_kind'] == 'REUSE_AUTHENTICATED_ORIGINAL_PDF':
                    need(file_sha(base / document['source_path']) == document['source_sha256'], 'old cached PDF mutated')
                    record = {**document, 'status': 'ORIGINAL_PDF_BYTES_REUSED_IDENTITY_REVIEW_SEPARATE'}
                else:
                    receipt, body = journal.fetch(key)
                    need(receipt['record']['http_status'] == 200 and receipt['record']['body_complete'] is True,
                         'complete original PDF HTTP200 required')
                    with body.open('rb') as stream:
                        header = stream.read(5)
                    need(header == b'%PDF-' and body.stat().st_size >= 1000, 'raw response is not a nontrivial PDF; original bytes retained')
                    record = {**document, 'status': 'PDF_MAGIC_CAPTURED_NUMERIC_IDENTITY_REVIEW_PENDING', 'receipt': receipt,
                              'source_path': str(body.relative_to(base)), 'source_sha256': file_sha(body),
                              'captured_at_utc': receipt['record']['captured_at_utc']}
                results[key] = record
                consecutive = 0
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if getattr(exc, 'capture_evidence_persistence_error', False):
                    raise
                results[key] = {**document, 'status': 'PDF_SOURCE_REJECTED', 'error_type': type(exc).__name__, 'error': str(exc)}
                consecutive += 1
            write_once(out / (key + '.json'), results[key])
            print('annual PDF', key, results[key]['status'], flush=True)
            if consecutive == 3:
                raise ValueError('three consecutive PDF source rejections; remaining resources not attempted')
            if document['source_kind'] == 'FRESH_FROZEN_PDF_GET':
                pause(0.2)
    except BaseException as exc:
        primary = exc
    finally:
        for key, path in paths.items():
            try:
                if file_sha(path) != expected[key]:
                    mismatches.append({'input': key, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': key, 'reason': type(exc).__name__})
        post = {'all_inputs_unchanged': not mismatches, 'count': len(paths), 'mismatches': mismatches,
                'source_request_rehashed_after_processing': True}
        terminal = {'status': 'FIXED12_ANNUAL_PDF_CAPTURE_TERMINAL', 'logical_attempts': journal.attempts if journal else 0,
                    'completed_documents': len(results), 'pending': [d['capture_key'] for d in req['documents'] if d['capture_key'] not in results],
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': post, 'persistence_errors': persistence_errors, 'financial_numeric_values_decoded': False}
        for name, value in (('case_results.json', results), ('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write_once(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('PDF terminal persistence errors: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'PDF input changed or terminal evidence failed')
    rejected = sum(r['status'] == 'PDF_SOURCE_REJECTED' for r in results.values())
    summary = {'status': 'FIXED12_ANNUAL_PDF_BYTES_CAPTURED_REVIEW_PENDING' if not rejected else 'FIXED12_ANNUAL_PDF_CAPTURE_INCOMPLETE',
        'request_sha256': expected_sha, 'documents_recorded': len(results), 'rejected_documents': rejected,
        'logical_attempts': journal.attempts, 'cached_reused': 2, 'results_by_document': results,
        'input_count': len(paths), 'all_inputs_unchanged': True, 'financial_numeric_values_decoded': False,
        'financial_version_history_complete': False, 'historical_arrival_verified': False,
        'investment_factor_admitted': False, 'portfolio_returns_computed': False, 'objective_achieved': False}
    write_once(out / 'documents.json', list(results.values()))
    write_once(out / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args(argv)
    base, root = Path(a.source_root).resolve(), Path(__file__).resolve().parents[1]
    result = capture(base, root, Path(a.request), a.expected_request_sha256, base / OUTPUT)
    print(result['status'], result['rejected_documents'], flush=True)
    return 0 if not result['rejected_documents'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
