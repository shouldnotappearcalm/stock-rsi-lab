"""Fixed12 initial2022 annual filing metadata, data-only and one HTTP attempt each."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time

from scripts.immutable_http_capture import ImmutableHttpCapture, need, file_sha, write_once

STATUS = 'FROZEN_BEFORE_FIXED12_INITIAL2022_ANNUAL_METADATA_CAPTURE'
OUTPUT = 'gross-profitability-initial2022-metadata-20261022'
OLD = 'cninfo-csi500-reports-20261017'
SAMPLE = 'experiments/qlib/fundamental-value-pilot-capture-request.json'
INVENTORY = 'experiments/qlib/gross-profitability-fixed12-annual-metadata-inventory.json'
METHODS = ('scripts/immutable_http_capture.py', 'scripts/capture_profitability_initial_annual_metadata.py')
PUBLIC = (SAMPLE, INVENTORY, 'experiments/qlib/cninfo-report-admission-2026-10-16.json',
          'experiments/qlib/gross-profitability-source-request.json',
          'experiments/qlib/gross-profitability-source-run-verification.json',
          'docs/research/profitability-fixed12-initial-metadata-plan-2026-10-22.md')


def read(path):
    return json.loads(Path(path).read_text())


def metadata_resource(code, org):
    return {'method': 'POST', 'url': 'https://www.cninfo.com.cn/new/hisAnnouncement/query',
            'payload': {'pageNum': '1', 'pageSize': '30', 'column': 'szse', 'tabName': 'fulltext',
                        'plate': '', 'stock': code[2:] + ',' + org, 'searchkey': '', 'secid': '',
                        'category': 'category_ndbg_szsh', 'trade': '', 'seDate': '2023-01-01~2023-12-31',
                        'sortName': '', 'sortType': '', 'isHLtitle': 'true'}}


def select_rows(code, data):
    need(type(data) is dict and type(data.get('totalAnnouncement')) is int
         and not isinstance(data['totalAnnouncement'], bool), 'original metadata count required')
    total, rows = data['totalAnnouncement'], data.get('announcements') or []
    need(0 <= total <= 30 and type(rows) is list and len(rows) == total
         and data.get('hasMore') in (None, False), 'one complete30-row metadata page required')
    normalized, selected, seen = [], [], set()
    for row in rows:
        need(type(row) is dict and row['secCode'] == code[2:] and type(row['announcementTime']) is int,
             'original issuer and dated metadata required')
        day = datetime.fromtimestamp(row['announcementTime'] / 1000, timezone(timedelta(hours=8))).date().isoformat()
        need('2023-01-01' <= day <= '2023-12-31', 'initial metadata outside2023 publication window')
        identity, title, path = str(row['announcementId']), row['announcementTitle'], row.get('adjunctUrl')
        need(identity.isdigit() and identity not in seen and type(title) is str, 'unique original announcement identity required')
        seen.add(identity)
        kind = 'OTHER_ANNUAL_CATEGORY_NOTICE'
        if '摘要' in title:
            kind = 'SUMMARY'
        elif '英文' in title:
            kind = 'ENGLISH_EDITION'
        elif '可视' in title:
            kind = 'VISUAL_EDITION'
        elif re.search(r'2022年?年度报告(?:全文|[（(](?:全文|修订版?|修订稿|更正后|更新后|中文版)[）)])?$', re.sub(r'\s+', '', title)):
            kind = 'FULL_2022_ANNUAL_REPORT'
            need(type(path) is str and re.fullmatch(r'finalpage/\d{4}-\d{2}-\d{2}/' + re.escape(identity) + r'\.[pP][dD][fF]', path),
                 'safe original full-report PDF path required')
        record = {'instrument': code, 'fiscal_year': 2022 if kind == 'FULL_2022_ANNUAL_REPORT' else None,
                  'title': title, 'day': day, 'timestamp_ms': row['announcementTime'],
                  'announcement_id': identity, 'pdf_path': path, 'classification': kind}
        normalized.append(record)
        if kind == 'FULL_2022_ANNUAL_REPORT':
            selected.append(record)
    need(1 <= len(selected) <= 2, 'one or two initial full reports required; no arbitrary edition selection')
    return normalized, selected


def required_paths(base, root):
    paths = {'repo/' + name: root / name for name in (*METHODS, *PUBLIC)}
    for name in ('manifest.json', 'plan.json'):
        paths['source/' + OLD + '/' + name] = base / OLD / name
    codes = read(root / SAMPLE)['codes']
    for code in codes:
        paths['source/' + OLD + '/codes/' + code + '.json'] = base / OLD / 'codes' / (code + '.json')
    return paths


def check(paths, expected):
    need(set(paths) == set(expected), 'complete fixed source metadata and method bindings required')
    for key, path in paths.items():
        need(file_sha(path) == expected[key], 'frozen source metadata or code changed: ' + key)


def verify(base, root, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha, 'frozen initial metadata request changed')
    request = read(request_file)
    codes = read(root / SAMPLE)['codes']
    orgs = read(base / OLD / 'plan.json')['org_by_code']
    need(request['status'] == STATUS and request['codes'] == codes and len(codes) == len(set(codes)) == 12
         and request['publication_window'] == ['2023-01-01', '2023-12-31']
         and request['fiscal_year'] == 2022 and request['max_logical_attempts'] == 12
         and request['per_resource_attempts'] == 1 and request['page_cap'] == 1
         and request['max_body_bytes'] == 1048576 and request['timeout_seconds'] == 20
         and request['minimum_request_interval_seconds'] == 0.2
         and request['output_subdir'] == OUTPUT and request['PDF_download_permitted'] is False
         and request['ranking_or_portfolio_returns_permitted'] is False
         and request['2026_financial_or_market_values_permitted'] is False, 'one fixed12 source-only metadata request required')
    need(request['resources'] == {code: metadata_resource(code, orgs[code]) for code in codes}
         and set(request['method_sha256']) == set(METHODS), 'exact original addressing and methods required')
    paths = required_paths(base, root)
    check(paths, request['input_sha256'])
    for name, digest in request['method_sha256'].items():
        need(digest == request['input_sha256']['repo/' + name], 'method/input identities disagree')
    manifest = read(base / OLD / 'manifest.json')
    inventory = read(root / INVENTORY)
    need(manifest['plan_sha256'] == file_sha(base / OLD / 'plan.json')
         and inventory['metadata_manifest_sha256'] == file_sha(base / OLD / 'manifest.json')
         and inventory['sample_codes'] == codes, 'original metadata inventory and addressing anchors changed')
    for code in codes:
        need(file_sha(base / OLD / 'codes' / (code + '.json')) == manifest['per_code_sha256'][code]
             == inventory['documents_by_code'][code]['original_packet_sha256'], 'original issuer metadata changed')
    return request, paths


def capture(base, root, request_file, expected_sha, out, *, opener=None, pause=time.sleep):
    need(out.resolve() == (base / OUTPUT).resolve() and not out.exists(), 'fixed fresh output only; no retry/resume')
    request, paths = verify(base, root, request_file, expected_sha)
    paths = {**paths, 'frozen_source_request': Path(request_file)}
    expected = {**request['input_sha256'], 'frozen_source_request': expected_sha}
    check(paths, expected)
    out.mkdir(parents=True)
    results, primary, mismatches, persistence_errors, journal = {}, None, [], [], None
    try:
        write_once(out / 'input-before.json', expected)
        kwargs = {} if opener is None else {'opener': opener}
        journal = ImmutableHttpCapture(out / 'http', request['resources'], max_attempts=12,
                                       max_body_bytes=1048576, **kwargs)
        consecutive = 0
        for code in request['codes']:
            try:
                receipt, body = journal.fetch(code)
                need(receipt['record']['http_status'] == 200, 'official metadata HTTP status not200')
                normalized, selected = select_rows(code, json.loads(body.read_bytes()))
                results[code] = {'status': 'INITIAL2022_FULL_REPORT_METADATA_CAPTURED', 'receipt': receipt,
                                 'all_normalized_rows': normalized, 'selected_full_reports': selected}
                consecutive = 0
            except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
                if getattr(exc, 'capture_evidence_persistence_error', False):
                    raise
                results[code] = {'status': 'INITIAL_METADATA_SOURCE_REJECTED',
                                 'error_type': type(exc).__name__, 'error': str(exc)}
                consecutive += 1
            write_once(out / (code + '.json'), results[code])
            print('initial annual metadata', code, results[code]['status'], flush=True)
            if consecutive == 3:
                raise ValueError('three consecutive source rejections; remaining resources not attempted')
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
        terminal = {'status': 'INITIAL2022_METADATA_CAPTURE_TERMINAL', 'logical_attempts': journal.attempts if journal else 0,
                    'completed_issuers': len(results), 'pending': [c for c in request['codes'] if c not in results],
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': post, 'persistence_errors': persistence_errors, 'PDFs_downloaded': 0,
                    'portfolio_returns_computed': False}
        for name, value in (('case_results.json', results), ('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write_once(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('Metadata terminal persistence errors: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'metadata input changed or terminal evidence persistence failed')
    good = sum(r['status'] == 'INITIAL2022_FULL_REPORT_METADATA_CAPTURED' for r in results.values())
    summary = {'status': 'INITIAL2022_METADATA_CAPTURE_COMPLETE' if good == 12 else 'INITIAL2022_METADATA_CAPTURE_INCOMPLETE',
        'request_sha256': expected_sha, 'successful_issuers': good, 'rejected_issuers': len(results) - good,
        'logical_attempts': journal.attempts, 'results_by_code': results, 'input_count': len(paths),
        'all_inputs_unchanged': True, 'PDFs_downloaded': 0, 'current_org_mapping_is_historical_master': False,
        'financial_version_history_complete': False, 'historical_arrival_verified': False,
        'investment_factor_admitted': False, 'new_market_or_financial_values_decoded': False,
        'portfolio_returns_computed': False, 'objective_achieved': False}
    write_once(out / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args(argv)
    base, root = Path(a.source_root).resolve(), Path(__file__).resolve().parents[1]
    result = capture(base, root, Path(a.request), a.expected_request_sha256, base / OUTPUT)
    print(result['status'], result['successful_issuers'], flush=True)
    return 0 if result['successful_issuers'] == 12 else 2


if __name__ == '__main__':
    raise SystemExit(main())
