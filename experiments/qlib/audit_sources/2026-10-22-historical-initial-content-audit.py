"""Separate source/page-cache and monetary-cell reconstruction, not visual QA.

No production imports. Shares the registered pypdf extractor and researcher.
Every original first page and every admitted cell/header/unit page is decoded
directly; other page-cache entries are checked against the run hash inventory.
"""
import argparse
from collections import Counter
from datetime import date, datetime, time, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def need(value, why):
    if not value: raise AssertionError(why)
def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def compact(text): return re.sub(r'\s+', '', text)


def main():
    import pypdf
    need(pypdf.__version__ == '6.10.0', 'registered shared extractor')
    parser = argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args()
    root,base,membership,request,run,out = map(lambda p:Path(p).resolve(),
        (a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base), 'fresh external audit')
    need(sha(request) == a.expected_request_sha256, 'frozen content request')
    req = read(request)
    need(req['status'] == 'FROZEN_BEFORE_ALL408_INITIAL_REPORT_CONTENT_INSPECTION'
         and req['document_count'] == 408 and req['workers'] == req['max_outstanding_documents'] == 4
         and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False, 'all408 source-only scope')
    old = base / 'cninfo-csi500-reports-20261017'
    fixed_dir = base / 'gross-profitability-fixed12-annual-pdfs-20261022'
    fixed_docs = {d['capture_key']:d for d in read(fixed_dir / 'documents.json')}
    special = {'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
        'PDF_document_records':fixed_dir/'documents.json',
        'inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    expected = {**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    paths = {'frozen_source_request':request}
    for key in req['input_sha256']:
        prefix,name = key.split('/',1)
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'safe input path')
        if prefix == 'repo': path = root/name
        elif prefix == 'source': path = base/name
        else:
            need(prefix == 'catalog','known historical catalog alias')
            if name in special: path = special[name]
            elif name.startswith('metadata/'): path = old/'codes'/(name.split('/',1)[1]+'.json')
            else:
                need(name.startswith('PDF/') and name[4:] in fixed_docs,'known catalog PDF')
                path = base/fixed_docs[name[4:]]['source_path']
        paths[key] = path
    for key,path in paths.items(): need(sha(path) == expected[key], 'unchanged input before: '+key)
    outputs = {str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    cases,summary,terminal = (read(run/name) for name in ('case_results.json','summary.json','terminal.json'))
    docs = read(base/'gross-profitability-historical394-initial2022-pdfs-20261022/documents.json')
    need(docs == req['documents'] and len(docs) == 408 and len({d['instrument'] for d in docs}) == 391
         and set(cases) == {d['capture_key'] for d in docs}, 'all editions and source issuers')
    cohort = read(root/'experiments/qlib/profitability-historical394-source-inventory.json')['dated_cohort']
    gaps = [c for c in cohort if c not in {d['instrument'] for d in docs}]
    need(gaps == req['remaining_source_gap_issuers'] == summary['remaining_source_gap_issuers']
         and len(cohort) == req['source_range_issuer_count'] == 394, 'uncovered source issuers retained')
    prior = read(base/'gross-profitability-fixed12-source-context-v4-20261022/case_results.json')
    allowed = {'input-before.json','input-postcheck.json','case_results.json','terminal.json','summary.json'}
    for start in range(0,408,4):
        name = 'batch-'+str(start//4).zfill(3)+'.json'
        allowed.add(name)
        need(read(run/name) == {'capture_keys':[d['capture_key'] for d in docs[start:start+4]]}, 'ordered bounded batches')
    checked_cells,checked_original_pages,preserved,observation_count = 0,0,0,0
    supported_issuers,opening = set(),[]
    money = r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
    for index,d in enumerate(docs):
        key = d['capture_key']; case = cases[key]
        allowed |= {key+'.json',key+'.pages.json'}
        cache = read(run/(key+'.pages.json')); pages = cache['pages']
        need(case == read(run/(key+'.json')) and case['source_sha256'] == cache['source_sha256'] == d['source_sha256']
             and sha(base/d['source_path']) == d['source_sha256'], 'source/case/cache identity')
        need(cache['extractor'] == 'pypdf6.10.0' and 1 <= len(pages) == case['page_count'] <= 1200
             and case['all_extracted_page_text_sha256'] == {
                 str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)}, 'complete page text conservation')
        for flag in ('financial_version_history_complete','historical_arrival_verified','economic_sector_compatibility_verified',
                     'manual_numeric_visual_review_complete','investment_factor_admitted'):
            need(case[flag] is False,'no unearned admission')
        reader = pypdf.PdfReader(base/d['source_path'])
        need(len(reader.pages) == len(pages), 'original physical page count')
        direct = set()
        def verify_original(page):
            nonlocal checked_original_pages
            if page not in direct:
                need((reader.pages[page-1].extract_text() or '') == pages[page-1], 'direct original physical page text')
                direct.add(page); checked_original_pages += 1
        verify_original(1)
        if key in prior:
            need(case['all_extracted_page_text_sha256'] == prior[key]['all_extracted_page_text_sha256'], 'all overlapping full-page hashes')
            if prior[key]['source_observations']:
                need(case['status'] == prior[key]['status'] and case['source_observations'] == prior[key]['source_observations'], 'old supported source observations')
                preserved += 1
        if case['status'] != 'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW':
            need(case['status'] in ('COVER_IDENTITY_UNVERIFIED','SOURCE_SCHEMA_UNSUPPORTED')
                 and case['source_observations'] == [], 'unparsed originals retained without financial substitution')
            continue
        supported_issuers.add(d['instrument'])
        observations = case['source_observations']; observation_count += len(observations)
        comparison = observations[0]['payload']['cells']['total_assets']['reported_comparative_balance_date']
        periods = {'2022-12-31'} if comparison == '2022-01-01' else {'2022-12-31','2021-12-31'}
        need(comparison in ('2022-01-01','2021-12-31') and {o['fiscal_end'] for o in observations} == periods
             and len(observations) == len(periods),'opening balance cannot become prior Dec31')
        if len(periods) == 1: opening.append(key)
        for observation in observations:
            need(observation['record_id'] == digest({k:v for k,v in observation.items() if k != 'record_id'}), 'observation digest')
            need(observation['instrument'] == d['instrument'] and observation['publication_day'] == d['day']
                 and observation['observed_at'] == d['captured_at_utc'] and observation['payload']['document_sha256'] == d['source_sha256']
                 and observation['payload']['announcement_id'] == d['announcement_id'],'source timing and edition')
            public_end = datetime.combine(date.fromisoformat(d['day']),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
            need(observation['public_day_end_at'] == public_end.isoformat(),'publication-day end remains conditional')
            column = 2022-int(observation['fiscal_end'][:4])
            need(set(observation['payload']['cells']) == {'revenue','cost_of_sales','total_assets'},'literal three-field source')
            for field,cell in observation['payload']['cells'].items():
                page = cell['page']; verify_original(page); verify_original(cell['header_page']); verify_original(cell['unit_evidence_page'])
                lines = [line.strip() for line in pages[page-1].splitlines() if line.strip()]
                need(('\n'+'\n'.join(lines)+'\n').count('\n'+cell['row_text']+'\n') == 1,'exact original row block')
                numbers = re.findall(money,cell['row_text'])
                need(len(numbers) == 2 and numbers[column] == cell['literal'] and cell['column_index'] == column
                     and cell['fiscal_end'] == observation['fiscal_end'] and cell['row_text_sha256'] == digest(cell['row_text']),'literal column and fiscal period')
                label = {'revenue':r'^(?:其中[：:]\s*)?营业收入\s*','cost_of_sales':r'^(?:其中[：:]\s*)?营业成本\s*','total_assets':r'^资产总计\s*'}[field]
                need(re.match(label,cell['row_text']), 'exact financial row label; no net income or total cost proxy')
                need(cell['statement'] == ('合并资产负债表' if field == 'total_assets' else '合并利润表'),'consolidated statement role')
                header_lines = [line.strip() for line in pages[cell['header_page']-1].splitlines() if line.strip()]
                need(cell['header_line'] in '\n'.join(header_lines),'original fiscal header block')
                unit = cell['unit']; need(unit in ('元','万元'),'explicit supported unit')
                unit_lines = [line.strip() for line in pages[cell['unit_evidence_page']-1].splitlines() if line.strip()]
                quote = cell['unit_evidence_literal']; need(quote in unit_lines,'original unit evidence')
                if re.fullmatch(r'单位[：:]'+unit+r'币种[：:]人民币',compact(quote)) is None:
                    need(re.fullmatch(r'单位[：:]'+unit,compact(quote)) and cell['currency_scope_evidence'],'bare unit needs currency evidence')
                    for evidence in cell['currency_scope_evidence']:
                        verify_original(evidence['page'])
                        source = '\n'.join(line.strip() for line in pages[evidence['page']-1].splitlines() if line.strip())
                        need(evidence['literal'] in source and evidence['unit'] == unit,'original currency scope quote')
                        pattern = (r'财务附注中报表的单位为[：:]人民币'+unit if evidence['scope'] == 'EXPLICIT_PRIMARY_FINANCIAL_SECTION_RMB'
                            else r'本集团记账本位币和编制本财务报表所采用的货币均为人民币[。；;]除有特别说明外[，,]?均以人民币'+unit+r'为单位表示[。]?')
                        need(re.fullmatch(pattern,compact(evidence['literal'])),'explicit financial reporting currency')
                amount = Fraction(cell['literal'].replace(',',''))*(1 if unit == '元' else 10000)
                need(amount == Fraction(cell['value_CNY']) and (amount > 0 if field == 'total_assets' else amount >= 0),'exact independent monetary conversion')
                checked_cells += 1
        print('content source audit',index+1,'/408',key,flush=True)
    need(set(outputs) == allowed and len(outputs) == 923,'exact923 complete inspection outputs')
    need(summary['document_count'] == 408 and summary['source_issuer_count'] == 391
         and summary['status_counts'] == dict(Counter(c['status'] for c in cases.values()))
         and summary['unsupported_error_counts'] == dict(Counter(c['error'] for c in cases.values() if 'error' in c))
         and summary['source_observation_count'] == observation_count and summary['supported_source_issuer_count'] == len(supported_issuers)
         and summary['old_supported_initial_reports_preserved'] == preserved,'actual supported/unsupported counts')
    for flag in ('financial_version_history_complete','manual_numeric_visual_review_complete','economic_sector_compatibility_verified',
                 'historical_arrival_verified','investment_factor_admitted','security_ranking_or_portfolio_returns_computed',
                 '2026_financial_or_market_values_read','objective_achieved'):
        need(summary[flag] is False,'summary evidence boundaries')
    post = {'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json') == expected and read(run/'input-postcheck.json') == post and terminal['postcheck'] == post
         and terminal['completed_documents'] == 408 and terminal['submitted_keys'] == [d['capture_key'] for d in docs]
         and terminal['pending'] == [] and terminal['original_error'] is None and terminal['persistence_errors'] == [],'complete terminal and input journals')
    for key,path in paths.items(): need(sha(path) == expected[key],'unchanged input after: '+key)
    need(outputs == {str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'output corpus unchanged')
    report = {'status':'PASS_SEPARATE_INITIAL_SOURCE_PAGE_CACHE_AND_CELL_CHECK_NOT_FACTOR_ADMISSION',
        'audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,
        'all_input_sha256':expected,'all_output_sha256':outputs,'source_documents':408,'source_issuers':391,
        'source_range_issuers':394,'source_gaps':gaps,'status_counts':summary['status_counts'],
        'literal_monetary_cells_checked':checked_cells,'source_observations_checked':observation_count,
        'supported_source_issuers':len(supported_issuers),'old_supported_initial_reports_preserved':preserved,
        'direct_original_PDF_pages_checked':checked_original_pages,'other_page_cache_entries_checked_against_run_hashes_only':True,
        'current_only_opening_balance_documents':opening,'production_modules_imported':False,
        'shares_pypdf6100_with_runner':True,'authored_after_run_started_same_researcher_not_blinded':True,
        'manual_numeric_visual_review_complete':False,'full_consolidated_boundary_grammar_independently_reimplemented':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'economic_sector_compatibility_verified':False,
        'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    with out.open('x') as stream: json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False); stream.write('\n')
    print(report['status'],sha(out),checked_cells,flush=True)


if __name__ == '__main__': main()
