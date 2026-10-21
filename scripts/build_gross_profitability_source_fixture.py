"""Frozen data-only pilot: two original reports, no ranking/accounts/network."""
import argparse
import hashlib
import json
from pathlib import Path

from stock_rsi.annual_profitability import CONTRACT, OBSERVED, RECONSTRUCTED, make_observation, need, parse_consolidated_tables, snapshot_observations

STATUS = 'FROZEN_BEFORE_GP_VINTAGE_SOURCE_FIXTURE_GENERATION'
PRIMARY = 'gross-profitability-primary-20261022'
OLD = 'fundamental-primary-documents-20261017'
CAPTURE = 'experiments/qlib/fundamental-primary-documents-capture-manifest.json'
REVIEW = 'experiments/qlib/gross-profitability-source-review-2026-10-22.json'
METHODS = ('scripts/build_gross_profitability_source_fixture.py', 'src/stock_rsi/annual_profitability.py',
           'src/stock_rsi/data.py', 'src/stock_rsi/models.py', 'src/stock_rsi/time.py')
PUBLIC = (CAPTURE, REVIEW, 'experiments/qlib/fundamental-first-issuer-primary-doc-request.json',
          'experiments/qlib/fundamental-first-issuer-numeric-audit.json',
          'docs/research/gross-profitability-source-plan-2026-10-22.md')
CASES = (('SH600166-2023-12-31-1219874919', (104, 105, 108)),
         ('SH600166-2024-12-31-1223327299', (98, 99, 102, 156)))
PRIMARY_FILES = ('novy-marx-2013-gross-profitability.pdf', 'paper-capture.json',
    *(f'paper-page-{page}.{ext}' for page in (1, 3) for ext in ('txt', 'png')),
    *(f'{stem}-page-{page}.{ext}' for stem, pages in CASES for page in pages for ext in ('txt', 'png')))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def required_paths(base, root):
    paths = {'repo/' + name: root / name for name in (*METHODS, *PUBLIC)}
    paths.update({'source/' + OLD + '/' + stem + '.pdf': base / OLD / (stem + '.pdf') for stem, _ in CASES})
    paths.update({'source/' + PRIMARY + '/' + name: base / PRIMARY / name for name in PRIMARY_FILES})
    return paths


def check(paths, expected):
    need(set(paths) == set(expected), 'complete fixed source/method input set required')
    for key, path in paths.items():
        need(sha(path) == expected[key], 'frozen source or method bytes changed: ' + key)


def verify(base, root, request_file, expected_sha):
    need(sha(request_file) == expected_sha, 'frozen source request changed')
    request = read(request_file)
    need(request['status'] == STATUS and request['contract'] == CONTRACT
         and request['instrument'] == 'SH600166' and request['report_years'] == [2023, 2024]
         and request['pypdf_version'] == '6.10.0' and request['max_publication_day'] == '2025-12-31'
         and request['portfolio_returns_permitted'] is False and request['ranking_permitted'] is False
         and request['2026_financial_or_market_values_permitted'] is False,
         'fixed two-document source-only pilot required')
    need(set(request['method_sha256']) == set(METHODS), 'all source-only methods required')
    paths = required_paths(base, root)
    check(paths, request['input_sha256'])
    for name, digest in request['method_sha256'].items():
        need(digest == request['input_sha256']['repo/' + name], 'method and input identities must agree')
    capture, review = read(root / CAPTURE), read(root / REVIEW)
    need([d['file'] for d in capture['documents']] == [stem + '.pdf' for stem, _ in CASES]
         and len(capture['documents']) == 2 and set(review['expected_cells_CNY']) == {'2023', '2024'},
         'exact original two source documents and manual evidence required')
    need(capture['request_sha256'] == sha(root / 'experiments/qlib/fundamental-first-issuer-primary-doc-request.json')
         and [d['statDate'] for d in capture['documents']] == ['2023-12-31', '2024-12-31'],
         'original capture request and fiscal identities required')
    need(review['contract'] == CONTRACT and review['source_file_sha256'] == {
             name: request['input_sha256']['source/' + PRIMARY + '/' + name] for name in PRIMARY_FILES}
         and review['paper']['source_pdf_sha256'] == sha(base / PRIMARY / 'novy-marx-2013-gross-profitability.pdf'),
         'complete reviewed paper and page evidence identity required')
    for document in capture['documents']:
        need(document['instrument'] == request['instrument'] and document['day'] <= '2025-12-31'
             and sha(base / OLD / document['file']) == document['sha256'], 'original annual source changed')
    return request, paths, capture, review


def pdf_pages(path):
    import pypdf
    need(pypdf.__version__ == '6.10.0', 'frozen PDF text extractor version required')
    return [page.extract_text() or '' for page in pypdf.PdfReader(path).pages]


def generate(base, root, request_file, expected_sha, out):
    need(not out.exists(), 'source fixture output already exists')
    request, paths, capture, review = verify(base, root, request_file, expected_sha)
    paths = {**paths, 'frozen_source_request': Path(request_file)}
    expected = {**request['input_sha256'], 'frozen_source_request': expected_sha}
    check(paths, expected)
    out.mkdir(parents=True)
    primary, result, mismatches, persistence_errors = None, None, [], []
    try:
        write(out / 'input-before.json', expected)
        records, page_hashes = [], {}
        for document in capture['documents']:
            year = int(document['statDate'][:4])
            pages = pdf_pages(base / OLD / document['file'])
            fields = parse_consolidated_tables(pages, year)
            need(set(fields) == set(review['expected_cells_CNY'][str(year)]), 'both current/comparative periods required')
            for fiscal_end, cells in fields.items():
                need({name: cell['value_CNY'] for name, cell in cells.items()}
                     == review['expected_cells_CNY'][str(year)][fiscal_end], 'source cells differ from visually checked originals')
                records.append(make_observation(document['instrument'], year, fiscal_end, document['day'],
                    document['captured_at_utc'], document['sha256'], document['announcement_id'], cells))
            page_hashes[document['file']] = {'page_count': len(pages),
                'all_extracted_physical_page_text_sha256': {str(i + 1): hashlib.sha256(t.encode()).hexdigest()
                                                          for i, t in enumerate(pages)}}
            selected = dict(CASES)[Path(document['file']).stem]
            for number in selected:
                text_path = base / PRIMARY / (Path(document['file']).stem + '-page-' + str(number) + '.txt')
                need(text_path.read_text() == pages[number - 1], 'frozen rendered-page text differs from extraction')
        need(len(records) == 4, 'exact four fiscal-period observations required')
        snapshots = {mode: {day: snapshot_observations(records, day + 'T15:05:00+08:00', mode=mode)
                            for day in ('2024-04-26', '2024-04-27', '2024-04-29', '2024-12-31',
                                        '2025-04-25', '2025-04-26', '2025-04-28', '2025-12-31')}
                     for mode in (OBSERVED, RECONSTRUCTED)}
        need(all(not row['records'] for row in snapshots[OBSERVED].values()), 'observed2026 captures cannot enter historical snapshots')
        old_only = [r for r in records if r['payload']['report_year'] == 2023]
        before = snapshot_observations(old_only, '2024-12-31T15:05:00+08:00', mode=RECONSTRUCTED)
        need(before == snapshots[RECONSTRUCTED]['2024-12-31'], 'later comparative filing changed an earlier snapshot')
        for name, value in (('observations.json', records), ('snapshots.json', snapshots), ('page_text_sha256.json', page_hashes)):
            write(out / name, value)
        result = {'status': 'GP_VINTAGE_SOURCE_FIXTURE_COMPLETE_NOT_STRATEGY_ADMITTED', 'contract': CONTRACT,
                  'request_sha256': expected_sha, 'issuer_count': 1, 'original_documents': 2, 'observations': 4,
                  'distinct_fiscal_periods': 3, 'snapshot_queries': 16, 'method_sha256': request['method_sha256'],
                  'all_observed_historical_snapshots_empty': True, 'later_restatement_does_not_backfill': True,
                  'original_2023_cost_CNY': review['expected_cells_CNY']['2023']['2023-12-31']['cost_of_sales'],
                  'later_comparative_2023_cost_CNY': review['expected_cells_CNY']['2024']['2023-12-31']['cost_of_sales'],
                  'source_document_sha256': {d['file']: d['sha256'] for d in capture['documents']},
                  'artifacts_sha256': {n: sha(out / n) for n in ('observations.json', 'snapshots.json', 'page_text_sha256.json')},
                  'gross_profitability_ratio_is_not_a_stock_return': True, 'financial_version_history_complete': False,
                  'historical_arrival_verified': False, 'investment_factor_admitted': False,
                  'historical_universe_coverage_complete': False, 'financial_cross_issuer_comparability_verified': False,
                  'portfolio_returns_computed': False, 'security_ranking_computed': False,
                  'original_accounts_strategies_and_failed_results_changed': False,
                  '2026_financial_or_market_values_read': False, 'objective_achieved': False}
    except BaseException as exc:
        primary = exc
    finally:
        for name, path in paths.items():
            try:
                if sha(path) != expected[name]:
                    mismatches.append({'input': name, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': name, 'reason': type(exc).__name__})
        post = {'all_inputs_unchanged': not mismatches, 'count': len(paths), 'mismatches': mismatches,
                'source_request_rehashed_after_processing': True}
        terminal = {'status': 'GP_SOURCE_FIXTURE_TERMINAL', 'completed': result is not None,
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': post, 'persistence_errors': persistence_errors, 'portfolio_returns_computed': False}
        for name, value in (('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('Source fixture terminal persistence errors: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'source input changed or terminal persistence failed')
    result.update(input_count=len(paths), all_inputs_unchanged=True)
    write(out / 'summary.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    result = generate(Path(args.source_root).resolve(), Path(__file__).resolve().parents[1], Path(args.request),
                      args.expected_request_sha256, Path(args.output_dir))
    print(result['status'])


if __name__ == '__main__':
    main()
