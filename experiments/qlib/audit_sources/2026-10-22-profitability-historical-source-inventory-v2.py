"""Read-only existing-source catalog, no new network, fields, ranks or returns."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def need(v, message):
    if not v: raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'membership-file', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args()
    base, membership, out = map(lambda x: Path(x).resolve(), (a.source_root, a.membership_file, a.output_dir))
    need(not out.exists(), 'fresh catalog output only')
    need(sha(membership) == 'ea377505b12eaeb234122b8b7523bbce0d38d4783090cbee2c47da44a9b61c35', 'authenticated membership intervals')
    cohort = sorted({code for code, start, end in (line.split() for line in membership.read_text().splitlines())
                     if start <= '2024-01-02' <= end and code.startswith(('SH60', 'SZ00'))})
    need(len(cohort) == 394, 'fixed historical main-board source-coverage cohort')
    folder = base / 'cninfo-csi500-reports-20261017'
    manifest = read(folder / 'manifest.json')
    need(sha(folder / 'manifest.json') == '3adcf64870b6300be87bed4ebddc216b2ed3c0619d3f99a795698f2bc6bf2eb2'
         and manifest['input_instrument_sha256'] == sha(membership)
         and sha(folder / 'plan.json') == manifest['plan_sha256'], 'existing metadata capture identities')
    paths = {'membership_intervals': membership, 'metadata_manifest': folder / 'manifest.json',
             'metadata_plan': folder / 'plan.json', 'PDF_document_records': base / 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json',
             'inventory_code': Path(__file__).resolve()}
    docs = read(paths['PDF_document_records'])
    need(len(docs) == 36 and {d['instrument'] for d in docs} <= set(cohort), 'old fixed12 sources belong to dated cohort')
    cached = {}
    for d in docs:
        need(d['day'] <= '2025-12-31' and not Path(d['source_path']).is_absolute() and '..' not in Path(d['source_path']).parts,
             'safe original pre2026 PDF record')
        source = base / d['source_path']
        need(sha(source) == d['source_sha256'], 'captured PDF bytes unchanged')
        paths['PDF/' + d['capture_key']] = source
        cached[(d['instrument'], d['fiscal_year'], d['announcement_id'])] = d
    packets = {}
    for code in cohort:
        p = folder / 'codes' / (code + '.json')
        need(sha(p) == manifest['per_code_sha256'][code], 'actual issuer metadata packet identity')
        packet = read(p)
        need(packet['code'] == code and packet['query_window'] == ['2024-01-01', '2025-12-31'], 'issuer/window identity')
        packets[code] = packet
        paths['metadata/' + code] = p
    expected = {k: sha(p) for k,p in paths.items()}
    cases = {}
    initial_cached = {(d['instrument'], d['fiscal_year']): d for d in docs if d['fiscal_year'] == 2022}
    for code in cohort:
        cells = {}
        for year in (2022, 2023, 2024):
            candidates, other_versions = [], []
            if year == 2022:
                d = initial_cached.get((code, year))
                if d:
                    candidates = [{k:d[k] for k in ('title', 'day', 'announcement_id', 'pdf_path')}]
            else:
                for row in packets[code]['reports']['annual']:
                    need(row['code'] == code[2:] and '2024-01-01' <= row['day'] <= '2025-12-31', 'source annual metadata issuer/window')
                    title = re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', row['title']))
                    if re.search(str(year) + r'年?年度报告', title) is None:
                        continue
                    if re.search(str(year) + r'年?年度报告(?:全文|（全文）|\(全文\)|\.docx)?$', title):
                        candidates.append(row)
                    elif '摘要' not in title and '英文' not in title:
                        other_versions.append(row)
            status = ('ONE_FULL_REPORT_METADATA_CANDIDATE' if len(candidates) == 1 else
                      'MULTIPLE_FULL_REPORT_METADATA_CANDIDATES' if candidates else
                      'INITIAL2022_METADATA_NOT_CAPTURED' if year == 2022 else 'NO_LITERAL_FULL_REPORT_METADATA_CANDIDATE')
            cells[str(year)] = {'status': status, 'full_report_candidates': candidates,
                'other_annual_title_rows_retained': other_versions,
                'candidate_PDFs_already_captured': [r['announcement_id'] for r in candidates
                    if (code, year, r['announcement_id']) in cached]}
        cases[code] = cells
    counts = {str(year): dict(Counter(c[str(year)]['status'] for c in cases.values())) for year in (2022,2023,2024)}
    metadata_cells = sum(bool(c[str(year)]['full_report_candidates']) for c in cases.values() for year in (2022,2023,2024))
    for key,p in paths.items(): need(sha(p) == expected[key], 'input unchanged after catalog: ' + key)
    out.mkdir(parents=True)
    def write(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write('case_results.json', cases)
    summary = {'status':'HISTORICAL394_PREFIX_AWARE_SOURCE_CATALOG_NOT_INVESTMENT_UNIVERSE_ADMISSION',
        'inventory_code_sha256': sha(__file__), 'company_name_title_prefix_supported':True, 'as_of':'2024-01-02', 'mainboard_cohort_count':394,
        'SH_count':sum(c.startswith('SH') for c in cohort),'SZ_count':sum(c.startswith('SZ') for c in cohort),
        'dated_cohort':cohort,'fiscal_years':[2022,2023,2024],'expected_issuer_year_cells':1182,
        'status_counts_by_fiscal_year':counts,'issuer_year_cells_with_full_report_metadata':metadata_cells,
        'authenticated_existing_PDF_documents':36,'initial2022_metadata_still_needed':382,
        'other_missing_or_ambiguous_metadata_cells':{str(year):[code for code in cohort if cases[code][str(year)]['status'] != 'ONE_FULL_REPORT_METADATA_CANDIDATE'] for year in (2023,2024)},
        'all_input_sha256':expected,'all_inputs_unchanged':True,'case_results_sha256':sha(out/'case_results.json'),
        'new_network_requests':0,'PDF_financial_text_or_numeric_values_decoded':False,
        'historical_nonfinancial_classification_complete':False,'current_org_lookup_is_historical_security_master':False,
        'all_filing_corrections_or_original_content_history_complete':False,'historical_arrival_verified':False,
        'financial_field_coverage_complete':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,
        'objective_achieved':False}
    write('summary.json',summary)
    print(summary['status'], counts, 'metadata_cells', metadata_cells, 'inputs',len(expected))


if __name__ == '__main__': main()
