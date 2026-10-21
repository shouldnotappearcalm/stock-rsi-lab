"""Separate source-page/cell check, authored after V2; shares pypdf extractor.

No production imports, source changes, rankings or portfolio returns. Not blinded.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re


def need(v, why):
    if not v:
        raise AssertionError(why)


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def child(root, name):
    need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'relative source/input path')
    p = root / name
    need(p.resolve().is_relative_to(root.resolve()), 'path remains inside source/input root')
    return p


def main():
    import pypdf
    need(pypdf.__version__ == '6.10.0', 'same explicit text extractor version')
    parser = argparse.ArgumentParser()
    for name in ('repo-root', 'source-root', 'request', 'expected-request-sha256', 'run-dir', 'output'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args()
    root, base, request, run, out = map(lambda p: Path(p).resolve(),
        (a.repo_root, a.source_root, a.request, a.run_dir, a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base), 'new external report')
    need(sha(request) == a.expected_request_sha256, 'frozen V2 request identity')
    req = read(request)
    need(req['status'] == 'FROZEN_BEFORE_SAME36_SOURCE_GRAMMAR_V2_INSPECTION'
         and req['document_count'] == 36 and not req['security_ranking_or_returns_permitted']
         and not req['2026_financial_or_market_values_permitted'], 'same36 source-only scope')
    expected = {**req['input_sha256'], 'frozen_source_request': a.expected_request_sha256}
    paths = {'frozen_source_request': request}
    for key in req['input_sha256']:
        prefix, name = key.split('/', 1)
        need(prefix in ('repo', 'source'), 'known input roots')
        paths[key] = child(root if prefix == 'repo' else base, name)
    need(len(paths) == 336, 'complete336 bound inputs')
    for key, p in paths.items():
        need(sha(p) == expected[key], 'input hash before source check: ' + key)
    outputs = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    need(len(outputs) == 41, 'complete41 V2 artifacts')
    docs = read(base / 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json')
    old = read(base / 'gross-profitability-fixed12-schema-20261022/case_results.json')
    cases, summary = read(run / 'case_results.json'), read(run / 'summary.json')
    need(set(cases) == {d['capture_key'] for d in docs} and len(cases) == 36, 'all36 cases preserved')
    supported = 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW'
    checked, preserved, checked_docs = 0, 0, []
    money = r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
    for d in docs:
        key, case = d['capture_key'], cases[d['capture_key']]
        need(case == read(run / (key + '.json')) and case['source_sha256'] == d['source_sha256'], 'case/source packet identity')
        need(case['all_extracted_page_text_sha256'] == old[key]['all_extracted_page_text_sha256'], 'all physical page texts unchanged from original run')
        for flag in ('financial_version_history_complete', 'historical_arrival_verified',
                     'economic_sector_compatibility_verified', 'manual_numeric_visual_review_complete', 'investment_factor_admitted'):
            need(case[flag] is False, 'no unearned source/economic admission')
        if case['status'] != supported:
            need(not case['source_observations'] and old[key]['status'] != supported, 'no rejection values or lost original successful parse')
            continue
        need(len(case['source_observations']) == 2, 'two fiscal source columns')
        source = child(base, d['source_path'])
        need(sha(source) == d['source_sha256'], 'original PDF bytes')
        reader = pypdf.PdfReader(source)
        cache = {}
        def page_lines(page):
            if page not in cache:
                text = reader.pages[page - 1].extract_text() or ''
                need(hashlib.sha256(text.encode()).hexdigest() == case['all_extracted_page_text_sha256'][str(page)], 'original page text authentication')
                cache[page] = [line.strip() for line in text.splitlines()]
            return cache[page]
        for observation in case['source_observations']:
            need(observation['record_id'] == digest({k:v for k,v in observation.items() if k != 'record_id'}), 'record digest')
            payload = observation['payload']
            need(observation['instrument'] == d['instrument'] and observation['publication_day'] == d['day']
                 and observation['observed_at'] == d['captured_at_utc'] and payload['document_sha256'] == d['source_sha256']
                 and payload['announcement_id'] == d['announcement_id'], 'source/period/capture conservation')
            index = d['fiscal_year'] - int(observation['fiscal_end'][:4])
            need(index in (0, 1) and set(payload['cells']) == {'revenue', 'cost_of_sales', 'total_assets'}, 'three fields/current-prior pair')
            for field, cell in payload['cells'].items():
                statement = '合并资产负债表' if field == 'total_assets' else '合并利润表'
                parent = '母公司资产负债表' if field == 'total_assets' else '母公司利润表'
                starts, ends = (old[key]['literal_statement_header_pages'][t] for t in (statement, parent))
                need(len(starts) == len(ends) == 1, 'independently bounded exact statement headings for this supported set')
                start, end, page = starts[0], ends[0], cell['page']
                need(start == cell['header_page'] and start <= page <= end and end - start <= 5, 'literal consolidated physical range')
                lines = page_lines(page)
                lo = lines.index(statement) + 1 if page == start else 0
                hi = lines.index(parent) if page == end else len(lines)
                need(lines[lo:hi].count(cell['row_text']) == 1, 'one exact row inside consolidated rather than parent range')
                literals = re.findall(money, cell['row_text'])
                need(len(literals) == 2 and literals[index] == cell['literal'] and cell['column_index'] == index,
                     'two literal amounts and matching fiscal column')
                unit = cell['unit']
                need(unit in ('元', '万元') and cell['unit_evidence_scope'] == 'LOCAL_TABLE_CURRENCY_AND_UNIT', 'explicit table unit for actual8 supported sources')
                header_lines = page_lines(start)
                need(cell['header_line'] in '\n'.join(header_lines) and cell['unit_evidence_literal'] in header_lines,
                     'literal fiscal header and unit on original table header page')
                need(re.fullmatch(r'单位[：:]' + unit + r'币种[：:]人民币', re.sub(r'\s+', '', cell['unit_evidence_literal'])) is not None,
                     'explicit original RMB unit')
                need(Fraction(cell['value_CNY']) == Fraction(cell['literal'].replace(',', '')) * (1 if unit == '元' else 10000), 'independent exact normalized monetary arithmetic')
                need(cell['row_text_sha256'] == digest(cell['row_text']), 'literal row digest')
                checked += 1
        if old[key]['status'] == supported:
            for before, after in zip(old[key]['source_observations'], case['source_observations']):
                need(before['fiscal_end'] == after['fiscal_end'], 'old fiscal order retained')
                for field, cell in before['payload']['cells'].items():
                    for name, value in cell.items():
                        need(after['payload']['cells'][field][name] == value, 'all original cell evidence retained')
                    preserved += 1
        checked_docs.append(key)
    counts = dict(Counter(c['status'] for c in cases.values()))
    need(checked == 48 and preserved == 18 and len(checked_docs) == 8, 'all actual supported cells checked')
    need(summary['status_counts'] == counts and summary['source_observations'] == 16 and summary['documents'] == 36
         and summary['input_count'] == 336 and summary['all_inputs_unchanged'] is True
         and summary['investment_factor_admitted'] is False and summary['objective_achieved'] is False, 'actual V2 summary')
    post = {'all_inputs_unchanged': True, 'count': 336, 'mismatches': [], 'source_request_rehashed_after_processing': True}
    terminal = read(run / 'terminal.json')
    need(read(run / 'input-before.json') == expected and read(run / 'input-postcheck.json') == post
         and terminal['completed_documents'] == 36 and terminal['pending'] == [] and terminal['original_error'] is None
         and terminal['postcheck'] == post and terminal['persistence_errors'] == [], 'complete terminal and input journals')
    for key, p in paths.items():
        need(sha(p) == expected[key], 'input hash after source check: ' + key)
    need(outputs == {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()}, 'outputs unchanged during source audit')
    report = {'status': 'PASS_SEPARATE_V2_SUPPORTED_SOURCE_CELL_CHECK_NOT_FACTOR_ADMISSION',
        'audit_code_sha256': sha(__file__), 'request_sha256': a.expected_request_sha256,
        'all336_input_sha256': expected, 'all41_output_sha256': outputs,
        'status_counts': counts, 'checked_documents': checked_docs, 'original_PDF_cells_checked': checked,
        'old_successful_cells_preserved': preserved, 'all36_page_text_hash_inventories_match_original_run': True,
        'normalization_arithmetic': 'stdlib Fraction, no production factor imports',
        'PDF_text_extractor_shared_with_runner': 'pypdf6.10.0', 'authored_after_run_same_researcher': True,
        'blinded_or_independent_researcher_audit_claimed': False, 'economic_sector_compatibility_verified': False,
        'financial_version_history_complete': False, 'historical_arrival_verified': False,
        'investment_factor_admitted': False, 'security_ranking_or_portfolio_returns_computed': False,
        '2026_financial_or_market_values_read': False, 'objective_achieved': False}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(report['status'], sha(out), checked)


if __name__ == '__main__':
    main()
