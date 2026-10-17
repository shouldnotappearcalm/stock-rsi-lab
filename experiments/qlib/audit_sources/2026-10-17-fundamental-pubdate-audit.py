"""Read-only metadata comparison. Matching dates do not certify financial values."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser()
for key in ('capture-dir', 'report-dir', 'request', 'calendar-file', 'output'):
    parser.add_argument('--'+key, required=True)
args = parser.parse_args()
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
digest = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
    separators=(',', ':'), allow_nan=False).encode()).hexdigest()
root, reports = Path(args.capture_dir), Path(args.report_dir)
manifest = json.loads((root/'manifest.json').read_text()); req = json.loads(Path(args.request).read_text())
assert manifest['status'] == 'FUNDAMENTAL_PILOT_CAPTURE_COMPLETE_NOT_ADMITTED_FOR_STRATEGY'
assert manifest['request_sha256'] == sha(args.request)
assert (root/'request.json').read_bytes() == Path(args.request).read_bytes()
assert all(sha(name) == h for name, h in req['method_sha256'].items())
assert sha(reports/'manifest.json') == req['cninfo_manifest_sha256']
assert sha(args.calendar_file) == req['calendar_sha256']
expected_days = [d for d in Path(args.calendar_file).read_text().splitlines() if req['window'][0] <= d <= req['window'][1]]
cm = json.loads((reports/'manifest.json').read_text())
assert manifest['codes'] == req['codes'] and manifest['query_attempt_reservations'] <= req['max_query_attempt_reservations']
for filename, h in manifest['journal_artifact_sha256'].items(): assert sha(root/filename) == h
assert len(list(root.rglob('reserved-*.json'))) == manifest['query_attempt_reservations']
patterns = {'annual': r'年度报告', 'q1': r'(?:第一季度|一季度)报告', 'h1': r'半年度报告',
            'q3': r'(?:第三季度|三季度)报告'}
ends = {'annual': '-12-31', 'q1': '-03-31', 'h1': '-06-30', 'q3': '-09-30'}
counts = Counter(); matrix = []; source_queries = 0; daily_rows = financial_rows = 0
for code in req['codes']:
    path = root/'codes'/(code+'.json'); assert sha(path) == manifest['per_code_sha256'][code]
    packet = json.loads(path.read_text()); assert packet['instrument'] == code
    assert [r['date'] for r in packet['daily']] == expected_days
    assert packet['daily'] == [dict(zip(packet['raw_daily']['fields'], r)) for r in packet['raw_daily']['rows']]
    assert len(packet['source_query_receipts']) == 10
    for ref in packet['source_query_receipts']:
        for key in ('request', 'reserved', 'response'): assert sha(root/ref[key+'_file']) == ref[key+'_sha256']
        response = json.loads((root/ref['response_file']).read_text())
        reservation = json.loads((root/ref['reserved_file']).read_text())
        identity = json.loads((root/ref['request_file']).read_text())
        assert identity['code'] == code[:2].lower()+'.'+code[2:]
        assert response['status'] == 'CAPTURED' and digest(response['payload']) == response['payload_sha256']
        assert response['reservation_sha256'] == sha(root/ref['reserved_file'])
        assert response['identity_sha256'] == reservation['identity_sha256'] == digest(identity)
        source_queries += 1
    quarters = packet['raw_quarters']; assert [(q['year'], q['quarter']) for q in quarters] == [tuple(q) for q in req['quarters']]
    raw_financial = [dict(zip(q['fields'], row)) for q in quarters for row in q['rows']]
    assert raw_financial == packet['financial'] + [r['record'] for r in packet['quarantine']] or (
        sorted(map(digest, raw_financial)) == sorted(map(digest, packet['financial']+[r['record'] for r in packet['quarantine']])))
    meta_path = reports/'codes'/(code+'.json'); assert sha(meta_path) == cm['per_code_sha256'][code]
    metadata = json.loads(meta_path.read_text()); primary = defaultdict(list)
    for kind, docs in metadata['reports'].items():
        for doc in docs:
            if re.search(r'20\d{2}年?'+patterns[kind]+r'(?:全文|（全文）|\(全文\)|\.docx)?$', doc['title']):
                year = re.findall(r'20\d{2}', doc['title'])[-1]
                primary[year+ends[kind]].append(doc)
    for financial in packet['financial']:
        docs = primary[financial['statDate']]
        match = any(doc['day'] == financial['pubDate'] for doc in docs)
        status = ('MATCHES_A_PRIMARY_REPORT_DATE' if match else
                  'PUBLICATION_DATE_DIFFERS' if docs else 'NO_PRIMARY_IN_EXISTING_METADATA_WINDOW')
        counts[status] += 1
        matrix.append({'instrument': code, 'statDate': financial['statDate'], 'vendor_pubDate': financial['pubDate'],
            'status': status, 'primary_report_count': len(docs), 'primary_reports': docs,
            'date_match_does_not_certify_numeric_vintage': True})
    daily_rows += len(packet['daily']); financial_rows += len(packet['financial'])
assert source_queries == req['unique_data_query_keys'] == 120
result = {'status': 'FUNDAMENTAL_PILOT_PUBLICATION_DATE_AUDIT_ONLY', 'source_manifest_sha256': sha(root/'manifest.json'),
    'request_sha256': sha(args.request), 'audit_script_sha256': sha(__file__), 'codes': req['codes'],
    'daily_rows': daily_rows, 'schema_valid_pre2026_financial_rows': financial_rows,
    'captured_unique_query_keys': source_queries, 'query_attempt_reservations': manifest['query_attempt_reservations'],
    'publication_match_counts': dict(counts), 'publication_matrix': matrix,
    'financial_version_history_complete': False, 'financial_values_verified_against_original_reports': False,
    'investment_factor_admitted': False, 'strategy_return_computed': False,
    '2026_market_or_return_values_queried': False, 'objective_achieved': False}
output = Path(args.output); assert not output.exists(); output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print('fundamental pubDate matrix', dict(counts))
