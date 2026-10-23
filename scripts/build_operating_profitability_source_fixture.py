"""Frozen two-report source pilot; no network, selection, account or return APIs."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from stock_rsi import annual_operating as op

CONTRACT = op.CONTRACT
STATUS = 'FROZEN_BEFORE_CN_OPERATING_SOURCE_FIXTURE'
REVIEW_STATUS = 'MANUAL_RAW_CELLS_REVIEWED_BEFORE_METRIC'
OLD = 'fundamental-primary-documents-20261017'
PRIMARY = 'gross-profitability-primary-20261022'
INSPECTION = 'cash-profitability-two-report-source-inspection-20261023'
OLD_REQUEST = 'experiments/qlib/fundamental-first-issuer-primary-doc-request.json'
CAPTURE = 'experiments/qlib/fundamental-primary-documents-capture-manifest.json'
REVIEW = 'experiments/qlib/operating-profitability-source-review.json'
MAPPING_REVIEW = 'experiments/qlib/cash-profitability-two-report-source-mapping-review.json'
CASES = (('SH600166-2023-12-31-1219874919', (104, 105, 108)),
         ('SH600166-2024-12-31-1223327299', (98, 99, 102, 156)))
METHODS = ('scripts/build_operating_profitability_source_fixture.py', 'src/stock_rsi/annual_operating.py',
           'src/stock_rsi/annual_profitability.py',
           *(f'src/stock_rsi/annual_profitability_v{i}.py' for i in range(2, 8)),
           'src/stock_rsi/data.py', 'src/stock_rsi/models.py', 'src/stock_rsi/time.py')
PUBLIC = (OLD_REQUEST, CAPTURE, REVIEW, MAPPING_REVIEW,
          'docs/research/annual-operating-profitability-source-design-2026-10-23.md',
          'docs/superpowers/plans/2026-10-23-annual-operating-profitability-source.md')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def required_paths(base, root):
    paths = {'repo/'+name: root/name for name in (*METHODS, *PUBLIC)}
    paths['source/'+INSPECTION+'/manifest.json'] = base/INSPECTION/'manifest.json'
    for stem, pages in CASES:
        paths['source/'+OLD+'/'+stem+'.pdf'] = base/OLD/(stem+'.pdf')
        for page in pages:
            for ext in ('txt', 'png'):
                key = PRIMARY+'/'+stem+f'-page-{page}.'+ext
                paths['source/'+key] = base/key
            for reader in ('pypdf', 'pdfminer'):
                key = INSPECTION+'/'+stem+f'/{reader}-page-{page}.txt'
                paths['source/'+key] = base/key
    return paths


def check(paths, expected):
    op.need(set(paths) == set(expected), 'complete fixed source/method set required')
    for key, path in paths.items():
        op.need(sha(path) == expected[key], 'frozen source/method bytes changed: '+key)


def verify(base, root, request_file, expected_sha):
    op.need(sha(request_file) == expected_sha, 'frozen source request changed')
    request = read(request_file)
    op.need(request['status'] == STATUS and request['contract'] == CONTRACT
            and request['instrument'] == 'SH600166' and request['report_years'] == [2023, 2024]
            and request['pypdf_version'] == '6.10.0' and request['max_publication_day'] == '2025-12-31'
            and request['portfolio_returns_permitted'] is False and request['ranking_permitted'] is False
            and request['2026_financial_or_market_values_permitted'] is False, 'fixed source-only two-report scope required')
    paths = required_paths(base, root)
    check(paths, request['input_sha256'])
    op.need(set(request['method_sha256']) == set(METHODS) and all(
        request['method_sha256'][name] == request['input_sha256']['repo/'+name] for name in METHODS), 'complete consistent method bindings required')
    capture, review, original = read(root/CAPTURE), read(root/REVIEW), read(root/OLD_REQUEST)
    op.need([d['file'] for d in capture['documents']] == [stem+'.pdf' for stem, _ in CASES]
            and len(original['documents']) == 2 and capture['request_sha256'] == sha(root/OLD_REQUEST), 'exact original capture chain required')
    for document, old in zip(capture['documents'], original['documents']):
        op.need(document['instrument'] == 'SH600166' and document['day'] <= '2025-12-31'
                and all(document[k] == old[k] for k in ('instrument', 'statDate', 'day', 'announcement_id'))
                and sha(base/OLD/document['file']) == document['sha256'], 'original annual source identity changed')
    op.need(review['status'] == REVIEW_STATUS and review['contract'] == CONTRACT and review['instrument'] == 'SH600166'
            and set(review['expected_cells_CNY']) == {'2023', '2024'}
            and review['source_pdf_sha256'] == {d['file']: d['sha256'] for d in capture['documents']}
            and review['source_mapping_review_sha256'] == sha(root/MAPPING_REVIEW)
            and review['expected_current_measure_is_not_precomputed'] is True, 'reviewed raw cells and source mapping required')
    return request, paths, capture, review


def pdf_pages(path):
    import pypdf
    op.need(pypdf.__version__ == '6.10.0', 'frozen PDF reader required')
    return [page.extract_text() or '' for page in pypdf.PdfReader(path).pages]


def generate(base, root, request_file, expected_sha, out):
    op.need(not out.exists(), 'source output already exists; never overwrite')
    request, paths, capture, review = verify(base, root, request_file, expected_sha)
    paths = {**paths, 'frozen_source_request': Path(request_file)}
    expected = {**request['input_sha256'], 'frozen_source_request': expected_sha}
    check(paths, expected)
    out.mkdir(parents=True)
    primary, result, mismatches, persistence_errors = None, None, [], []
    try:
        write(out/'input-before.json', expected)
        reports, page_hashes = [], {}
        for document in capture['documents']:
            year = int(document['statDate'][:4]);stem = Path(document['file']).stem
            pages = pdf_pages(base/OLD/document['file'])
            identity = op.grammar.document_identity(pages, 'SH600166', year)
            op.need(identity['code_consistent'] and identity['annual_year_consistent'], 'original PDF instrument/title identity required')
            parsed = op.parse_report(pages, year)
            normalized = {'income': {period: {field: c['value_CNY'] for field, c in fields.items()}
                                      for period, fields in parsed['income'].items()},
                          'balances': {period: c['value_CNY'] for period, c in parsed['balances'].items()}}
            op.need(normalized == review['expected_cells_CNY'][str(year)], 'extracted raw cells differ from reviewed originals')
            selected = dict(CASES)[stem]
            for page in selected:
                op.need(pages[page-1] == (base/PRIMARY/f'{stem}-page-{page}.txt').read_text()
                        == (base/INSPECTION/stem/f'pypdf-page-{page}.txt').read_text(), 'reviewed physical page text changed')
            for fields in (*parsed['income'].values(), *({'total_assets': cell} for cell in parsed['balances'].values())):
                for cell in fields.values():
                    op.need(cell['page'] in selected, 'numeric cell outside reviewed physical pages')
                    alternate = (base/INSPECTION/stem/f'pdfminer-page-{cell["page"]}.txt').read_text()
                    op.need(op.compact(cell['literal']) in op.compact(alternate), 'independent-reader source amount anchor missing')
            reports.append(op.make_report('SH600166', year, document['day'], document['captured_at_utc'],
                                          document['sha256'], document['announcement_id'], parsed))
            page_hashes[document['file']] = {'physical_pages': len(pages),
                'text_sha256': {str(i+1): hashlib.sha256(text.encode()).hexdigest() for i, text in enumerate(pages)}}
        op.need(len(reports) == 2, 'exact two filing records required')
        snapshots = {mode: {day: op.snapshot_reports(reports, day+'T15:05:00+08:00', mode=mode)
                            for day in ('2024-04-26', '2024-04-27', '2024-04-29', '2024-12-31',
                                        '2025-04-25', '2025-04-26', '2025-04-28', '2025-12-31')}
                     for mode in (op.OBSERVED, op.RECONSTRUCTED)}
        op.need(all(not view['records'] for view in snapshots[op.OBSERVED].values()), 'actual2026 capture cannot backdate observed data')
        earlier = op.snapshot_reports(reports[:1], '2024-12-31T15:05:00+08:00', mode=op.RECONSTRUCTED)
        op.need(earlier == snapshots[op.RECONSTRUCTED]['2024-12-31'], 'future filing changed earlier source snapshot')
        for name, value in (('reports.json', reports), ('snapshots.json', snapshots), ('page-text-sha256.json', page_hashes)):
            write(out/name, value)
        result = {'status': 'CN_OPERATING_SOURCE_FIXTURE_COMPLETE_NOT_STRATEGY_ADMITTED', 'contract': CONTRACT,
            'request_sha256': expected_sha, 'issuer_count': 1, 'original_documents': 2, 'filing_records': 2,
            'raw_numeric_cells': 24, 'current_year_measures': 2, 'comparative_ratios_computed': False, 'snapshot_queries': 16,
            'all_observed_historical_snapshots_empty': True, 'later_filing_does_not_backfill': True,
            'source_document_sha256': {d['file']: d['sha256'] for d in capture['documents']},
            'artifacts_sha256': {name: sha(out/name) for name in ('reports.json', 'snapshots.json', 'page-text-sha256.json')},
            'source_measure_is_not_portfolio_return': True, 'historical_arrival_verified': False,
            'historical_universe_coverage_complete': False, 'financial_cross_issuer_comparability_verified': False,
            'full_cash_profitability_replication': False, 'investment_factor_admitted': False,
            'security_ranking_computed': False, 'portfolio_returns_computed': False,
            '2026_financial_or_market_values_read': False, 'original_accounts_strategies_and_failed_results_changed': False,
            'objective_achieved': False}
        result.update(input_count=len(paths), all_inputs_unchanged=True)
        # Staged evidence is never the completed summary. Interruptions here are
        # caught before the source/request postcheck, even after a partial write.
        write(out/'.summary-pending.json', result)
    except BaseException as exc:
        primary = exc
    finally:
        for key, path in paths.items():
            try:
                if sha(path) != expected[key]:mismatches.append({'input': key, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': key, 'reason': type(exc).__name__})
        post = {'count': len(paths), 'all_inputs_unchanged': not mismatches, 'mismatches': mismatches,
                'source_request_rehashed_after_processing': True}
        try:
            write(out/'input-postcheck.json', post)
        except BaseException as exc:
            persistence_errors.append('input-postcheck.json:'+type(exc).__name__)
            if primary is None:primary = exc
        if result is not None and primary is None and not mismatches and not persistence_errors:
            try:
                os.replace(out/'.summary-pending.json', out/'summary.json')
            except BaseException as exc:
                primary = exc
        terminal = {'status': 'CN_OPERATING_SOURCE_TERMINAL',
                    'completed': result is not None and primary is None and not mismatches and not persistence_errors,
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': post, 'persistence_errors': persistence_errors, 'portfolio_returns_computed': False}
        try:
            write(out/'.terminal-pending.json', terminal)
            os.replace(out/'.terminal-pending.json', out/'terminal.json')
        except BaseException as exc:
            persistence_errors.append('terminal.json:'+type(exc).__name__)
            if primary is None:primary = exc
            if (out/'summary.json').exists():
                try:os.replace(out/'summary.json', out/'uncommitted-summary.json')
                except BaseException as cleanup:persistence_errors.append('summary-demotion:'+type(cleanup).__name__)
            terminal.update(completed=False,original_error={'type':type(primary).__name__,'message':str(primary)})
            try:
                write(out/'.terminal-failure.json', terminal)
                os.replace(out/'.terminal-failure.json', out/'terminal.json')
            except BaseException as failure:persistence_errors.append('terminal-failure:'+type(failure).__name__)
    if primary is not None:
        if persistence_errors:primary.add_note('terminal persistence errors: '+str(persistence_errors))
        raise primary
    op.need(not mismatches and not persistence_errors, 'source changed or terminal evidence persistence failed')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256', 'output-dir'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args(argv)
    result = generate(Path(args.source_root).resolve(), Path(__file__).resolve().parents[1],
                      Path(args.request), args.expected_request_sha256, Path(args.output_dir))
    print(result['status'])


if __name__ == '__main__':
    main()
