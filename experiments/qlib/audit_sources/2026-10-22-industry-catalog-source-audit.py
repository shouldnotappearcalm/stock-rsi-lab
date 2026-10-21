"""Independent native PDFium source-cell QA; no production/parser imports.
Written by the same researcher after extraction; not a blinded/manual review.
"""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pypdfium2 as pdfium


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def compact(value):
    return re.sub(r'\s+', '', value)


def inventory(folder):
    return {str(p.relative_to(folder)): sha(p)
            for p in sorted(folder.rglob('*')) if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    for name in ('repo-root', 'source-root', 'membership-file', 'request',
                 'expected-request-sha256', 'run-dir', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    root, base, membership, request, run, output = (
        Path(getattr(args, n)).resolve() for n in
        ('repo_root', 'source_root', 'membership_file', 'request', 'run_dir', 'output'))
    need(not output.exists() and not output.is_relative_to(run), 'fresh external QA output')
    need(sha(request) == args.expected_request_sha256, 'frozen request hash')
    req = read(request)
    paths = {'frozen_source_request': request}
    for key in req['input_sha256']:
        if key == 'membership':
            paths[key] = membership
        elif key.startswith('repo/'):
            paths[key] = root / key[5:]
        elif key.startswith('source/'):
            paths[key] = base / key[7:]
        else:
            raise ValueError('unknown input namespace')
    expected = {**req['input_sha256'], 'frozen_source_request': args.expected_request_sha256}
    need(len(paths) == 48, 'complete48-input closure')
    for key, path in paths.items():
        need(sha(path) == expected[key], 'input before: ' + key)
    outputs = inventory(run)
    names = {f'page-{n:03}.json' for n in range(1, 108)}
    names.update(('catalog.json', 'cohort-snapshots.json', 'summary.json',
                  'terminal.json', 'input-before.json', 'input-postcheck.json'))
    need(set(outputs) == names, 'exact113-file output inventory')
    need(read(run / 'input-before.json') == expected, 'input manifest')
    post, terminal = read(run / 'input-postcheck.json'), read(run / 'terminal.json')
    need(post['all_inputs_unchanged'] and post['count'] == 48 and not post['mismatches']
         and terminal['completed_geometry_pages'] == 107 and not terminal['pending_physical_pages']
         and terminal['original_error'] is None and not terminal['persistence_errors'], 'complete successful source termination')
    catalog, snapshots, summary = (read(run / name) for name in
                                     ('catalog.json', 'cohort-snapshots.json', 'summary.json'))
    records = catalog['records']
    need(catalog['record_count'] == len(records) == summary['source_classification_records'], 'record counts')
    need(catalog['classification_period'] == '2021Q3' and catalog['physical_pages'] == 107,
         'vintage and complete pages')
    need(catalog['public_content_available_by'] == req['public_content_available_by']
         and catalog['observed_at'] == req['source_observed_at'], 'catalog clocks')
    packets = {n: read(run / f'page-{n:03}.json') for n in range(1, 108)}
    cells, events, data_rows = {}, {n: [] for n in range(3)}, {}
    for n, packet in packets.items():
        need(packet['physical_page'] == n and packet['source_sha256'] == req['source_pdf_sha256']
             and len(packet['tables']) == 1 and packet['tables'][0]['table_index'] == 0,
             'complete original page/table identity')
        need(hashlib.sha256(packet['page_text'].encode()).hexdigest() == packet['page_text_sha256'], 'raw page text digest')
        rows = packet['tables'][0]['rows']
        need([r['row_index'] for r in rows] == list(range(len(rows))), 'row inventory')
        need([compact(c['literal']) for c in rows[0]['cells']] ==
             ['门类名称及代码', '行业大类代码', '行业大类名称', '上市公司代码', '上市公司简称'], 'literal header')
        for row in rows[1:]:
            position = (n, 0, row['row_index'])
            need(len(row['cells']) == 5, 'five source columns')
            data_rows[position] = compact(row['cells'][3]['literal'])
            for col, cell in enumerate(row['cells']):
                cells[(*position, col)] = cell
                if col < 3 and cell['literal'] and cell['literal'].strip():
                    events[col].append(position)
    need(len(data_rows) == len(records), 'no omitted original data row')
    pdf_path = base / req['source_pdf_relative_path']
    need(sha(pdf_path) == req['source_pdf_sha256'], 'original PDF identity')
    archive = pdf_path.parent.parent / 'archive-payload/body.bin'
    need(sha(archive) == sha(pdf_path), 'byte-identical historical archived PDF')
    native_codes, checked, page_handles = [], set(), {}
    fields = ('sector', 'industry_code', 'industry_name', 'stock_code', 'stock_name')
    with pdfium.PdfDocument(pdf_path) as doc:
        need(len(doc) == 107, 'native original page count')
        try:
            for i in range(len(doc)):
                page = doc[i]
                text = page.get_textpage()
                page_handles[i + 1] = (page, text)
                native_codes.extend(re.findall(r'(?<![0-9])[0-9]{6}(?![0-9])', text.get_text_range()))
                w, h = page.get_size()
                need(abs(w - packets[i + 1]['width']) < .1 and abs(h - packets[i + 1]['height']) < .1,
                     'independent physical dimensions')
            need(len(set(native_codes)) == len(native_codes), 'unique native code inventory')
            need(Counter(native_codes) == Counter(r['stock_code'] for r in records), 'complete native stock-code inventory')
            seen_rows = set()
            for record in records:
                need(record['record_id'] == digest({k: v for k, v in record.items() if k != 'record_id'}), 'record digest')
                position = (record['physical_page'], record['table_index'], record['row_index'])
                need(position not in seen_rows and data_rows[position] == record['stock_code'], 'one record per original row')
                seen_rows.add(position)
                need(record['classification_period'] == '2021Q3' and record['source_sha256'] == sha(pdf_path)
                     and record['source_vintage_not_actual_current_business'] is True, 'source vintage identity')
                inherited = []
                for col, field in enumerate(fields):
                    src = record['field_sources'][field]
                    origin = (src['physical_page'], src['table_index'], src['row_index'])
                    need(src['column_index'] == col and cells[(*origin, col)] ==
                         {'literal': src['literal'], 'bbox': src['bbox']}, 'exact source-cell pointer')
                    need(origin <= position, 'no future label source')
                    if origin != position:
                        inherited.append(field)
                    if col < 3:
                        idx = bisect_right(events[col], position) - 1
                        need(idx >= 0 and events[col][idx] == origin, 'latest explicit field interval')
                        if col > 0:
                            start = bisect_right(events[0], origin) - 1
                            now = bisect_right(events[0], position) - 1
                            need(compact(cells[(*events[0][start], 0)]['literal']) ==
                                 compact(cells[(*events[0][now], 0)]['literal']), 'minor field belongs to same sector')
                    else:
                        need(origin == position, 'stock identity must be literal in its own row')
                    identity = (*origin, col)
                    if identity not in checked:
                        page, text = page_handles[src['physical_page']]
                        height = page.get_size()[1]
                        x0, y0, x1, y1 = src['bbox']
                        native = text.get_text_bounded(left=x0 + .12, right=x1 - .12,
                                                       bottom=height - y1 + .12, top=height - y0 - .12,
                                                       errors='strict')
                        need(compact(native) == compact(src['literal']),
                             f'native cell mismatch {identity}: {native!r} != {src["literal"]!r}')
                        checked.add(identity)
                need(record['inherited_fields'] == inherited and record['classification_context_carried_across_pages'] ==
                     any(s['physical_page'] < position[0] for s in record['field_sources'].values()), 'inheritance annotations')
                literals = {f: compact(record['field_sources'][f]['literal']) for f in fields}
                match = re.fullmatch(r'(.+?)[(（]([A-Z])[)）]', literals['sector'])
                need(match and (record['sector_name'], record['sector_code']) == match.groups(), 'sector literal')
                need((record['sector_code'] == 'J') == (record['sector_name'] == '金融业'), 'financial identity')
                for field in fields[1:]:
                    need(record[field] == literals[field], 'literal scalar: ' + field)
        finally:
            for page, text in page_handles.values():
                text.close()
                page.close()
    cohort = sorted({c for c, start, end in (line.split() for line in membership.read_text().splitlines())
                     if start <= '2024-01-02' <= end and c.startswith(('SH60', 'SZ00'))})
    need(cohort == req['cohort'] and len(cohort) == 394, 'independent dated full cohort')
    indexed = {r['stock_code']: r for r in records}
    utc = lambda x: datetime.fromisoformat(x).astimezone(timezone.utc)
    need(set(snapshots) == {q['id'] for q in req['snapshot_queries']} and len(snapshots) == 7, 'seven exact clock queries')
    for query in req['snapshot_queries']:
        snap = snapshots[query['id']]
        public, observed, clock = map(utc, (req['public_content_available_by'], req['source_observed_at'], query['as_of']))
        visible = clock >= (max(public, observed) if query['mode'] == 'OBSERVED' else public)
        need(snap['as_of'] == clock.isoformat() and snap['visibility_mode'] == query['mode']
             and snap['classification_visible'] == visible, 'snapshot clock boundary')
        expected_rows = []
        for code in cohort:
            source = indexed.get(code[2:])
            if not visible:
                row = {'instrument': code, 'status': 'NOT_AVAILABLE_AT_CLOCK'}
            elif source is None:
                row = {'instrument': code, 'status': 'NOT_IN_SOURCE_VINTAGE'}
            else:
                row = {'instrument': code, 'status': 'FINANCIAL_IN_SOURCE_VINTAGE' if source['sector_code'] == 'J' else 'NONFINANCIAL_IN_SOURCE_VINTAGE',
                       'classification_period': '2021Q3', 'record_id': source['record_id'], 'source_record': source,
                       'vintage_carryforward_is_not_current_business_verification': True}
            expected_rows.append(row)
        need(snap['classifications'] == expected_rows, 'all cohort rows and full source records: ' + query['id'])
        for flag in ('current_business_identity_verified', 'classification_history_complete',
                     'historical_research_system_arrival_verified', 'investment_factor_admitted'):
            need(snap[flag] is False, 'snapshot evidence limit')
    counts = dict(Counter(r['status'] for r in snapshots['reconstructed2024']['classifications']))
    need(summary['reconstructed2024_source_vintage_status_counts'] == counts
         and summary['request_sha256'] == args.expected_request_sha256
         and summary['observed_pre2026_visible_classifications'] == 0
         and summary['reconstructed2024_2025_record_ids_equal'] is True, 'summary independent counts/clock')
    for flag in ('current_business_identity_verified', 'classification_history_complete', 'financial_reporting_compatibility_verified',
                 'historical_nonfinancial_identity_complete', 'investment_factor_admitted',
                 'stock_ranking_or_portfolio_returns_computed', '2026_financial_or_market_values_read', 'objective_achieved'):
        need(summary[flag] is False, 'summary evidence limit: ' + flag)
    for key, path in paths.items():
        need(sha(path) == expected[key], 'input after: ' + key)
    need(inventory(run) == outputs, 'all output bytes unchanged after QA')
    result = {'status': 'INDEPENDENT_NATIVE_PDFIUM_SOURCE_CELL_AUDIT_PASSED_NOT_FACTOR_ADMITTED',
              'audit_code_sha256': sha(Path(__file__)), 'request_sha256': args.expected_request_sha256,
              'original_pages_independently_read': len(page_handles), 'native_stock_code_count': len(native_codes),
              'unique_source_cells_independently_read': len(checked), 'source_records_checked': len(records),
              'cohort_count': len(cohort), 'clock_queries_checked': len(snapshots), 'source_vintage_status_counts': counts,
              'all_input_sha256': expected, 'all_output_sha256': outputs,
              'all_inputs_and_outputs_unchanged': True, 'no_production_imports': True,
              'same_researcher_after_extraction': True, 'complete_manual_business_review': False,
              'current_business_identity_verified': False, 'investment_factor_admitted': False,
              'stock_ranking_or_portfolio_returns_computed': False, 'objective_achieved': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({k: v for k, v in result.items() if not k.startswith('all_')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
