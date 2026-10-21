"""Separate V5 old-observation conservation and newly supported source-cell QA.
No production imports. Old cells reuse the unchanged earlier audit; new cells
and currency/unit/header pages are decoded directly with the shared extractor.
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


def need(value,why):
    if not value: raise AssertionError(why)
def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def compact(text): return re.sub(r'\s+','',text)


def main():
    import pypdf
    need(pypdf.__version__ == '6.10.0','registered shared extractor')
    parser=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args()
    root,base,membership,request,run,out=map(lambda p:Path(p).resolve(),
        (a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external audit result')
    need(sha(request) == a.expected_request_sha256,'frozen V5 source request')
    req=read(request)
    need(req['status'] == 'FROZEN_BEFORE_ALL408_CURRENCY_AND_NOTE_V5_SOURCE_INSPECTION' and req['document_count'] == 408
         and req['all_V4_supported_observations_must_be_identical'] is True
         and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'whole408 source-only V5 scope')
    old_dir=base/'gross-profitability-historical394-initial2022-schema-20261022'
    old_audit=read(root/'experiments/qlib/profitability-historical394-initial-schema-audit.json')
    need(old_audit['status'] == 'PASS_SEPARATE_INITIAL_SOURCE_PAGE_CACHE_AND_CELL_CHECK_NOT_FACTOR_ADMISSION'
         and old_audit['audit_code_sha256'] == sha(root/'experiments/qlib/audit_sources/2026-10-22-historical-initial-content-audit.py')
         and old_audit['request_sha256'] == 'ce6f7699c24df53aa31c3519ffd474e6b4e705f718bcc4684549e1454bb81309',
         'earlier source-cell audit identity')
    need({str(p.relative_to(old_dir)):sha(p) for p in sorted(old_dir.rglob('*')) if p.is_file()} == old_audit['all_output_sha256'],
         'all923 earlier outputs including actual text caches unchanged')
    old=base/'cninfo-csi500-reports-20261017';fixed=base/'gross-profitability-fixed12-annual-pdfs-20261022'
    fixed_docs={d['capture_key']:d for d in read(fixed/'documents.json')}
    special={'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
        'PDF_document_records':fixed/'documents.json','inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    paths={'frozen_source_request':request};expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    for key in req['input_sha256']:
        prefix,name=key.split('/',1)
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe bound input')
        if prefix == 'repo': path=root/name
        elif prefix == 'source': path=base/name
        else:
            need(prefix == 'catalog','known source catalog')
            if name in special: path=special[name]
            elif name.startswith('metadata/'): path=old/'codes'/(name.split('/',1)[1]+'.json')
            else:
                need(name.startswith('PDF/') and name[4:] in fixed_docs,'known cached source')
                path=base/fixed_docs[name[4:]]['source_path']
        paths[key]=path
    for key,path in paths.items(): need(sha(path) == expected[key],'unchanged input before: '+key)
    outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    cases,summary,terminal=(read(run/name) for name in ('case_results.json','summary.json','terminal.json'))
    before=read(old_dir/'case_results.json')
    docs=read(base/'gross-profitability-historical394-initial2022-pdfs-20261022/documents.json')
    need(docs == req['documents'] and len(docs) == 408 and len({d['instrument'] for d in docs}) == 391
         and set(cases) == set(before) == {d['capture_key'] for d in docs},'all original editions and source identities')
    cohort=read(root/'experiments/qlib/profitability-historical394-source-inventory.json')['dated_cohort']
    gaps=[c for c in cohort if c not in {d['instrument'] for d in docs}]
    need(gaps == req['remaining_source_gap_issuers'] == summary['remaining_source_gap_issuers'] and len(cohort) == 394,'complete source range including gaps')
    allowed={'input-before.json','input-postcheck.json','terminal.json','case_results.json','summary.json'}
    supported='SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW'
    preserved,new_docs,new_cells,direct_pages,observations=0,[],0,0,0
    money=r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
    for d in docs:
        key=d['capture_key'];case=cases[key];prior=before[key];allowed.add(key+'.json')
        need(case == read(run/(key+'.json')) and case['source_sha256'] == prior['source_sha256'] == d['source_sha256']
             and case['identity_evidence'] == prior['identity_evidence']
             and case['all_extracted_page_text_sha256'] == prior['all_extracted_page_text_sha256']
             and case['V4_source_status'] == prior['status'] and case['V4_source_error'] == prior.get('error'),'old/new case source identity and evidence')
        for flag in ('financial_version_history_complete','historical_arrival_verified','economic_sector_compatibility_verified',
                     'manual_numeric_visual_review_complete','investment_factor_admitted'):
            need(case[flag] is False,'source-only evidence flags')
        observations+=len(case['source_observations'])
        if prior['status'] == supported:
            need(case['status'] == supported and case['source_observations'] == prior['source_observations'],'exact complete old observations retained')
            preserved+=1;continue
        if case['status'] != supported:
            need(case['status'] in ('SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED') and case['source_observations'] == [],'all unresolved originals retained')
            continue
        need(case['cover_code_consistent'] and case['cover_annual_year_consistent'],'new values need unchanged source identity gate')
        new_docs.append(key)
        pages=read(old_dir/(key+'.pages.json'))['pages']
        need(case['all_extracted_page_text_sha256'] == {str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)},'original full page cache hashes')
        reader=pypdf.PdfReader(base/d['source_path']);checked=set()
        need(len(reader.pages) == len(pages) == case['page_count'],'original physical page count')
        def direct(page):
            nonlocal direct_pages
            if page not in checked:
                need((reader.pages[page-1].extract_text() or '') == pages[page-1],'direct original page text')
                checked.add(page);direct_pages+=1
            return '\n'.join(t.strip() for t in pages[page-1].splitlines() if t.strip())
        comparison=case['source_observations'][0]['payload']['cells']['total_assets']['reported_comparative_balance_date']
        periods={'2022-12-31'} if comparison == '2022-01-01' else {'2022-12-31','2021-12-31'}
        need(comparison in ('2022-01-01','2021-12-31') and {o['fiscal_end'] for o in case['source_observations']} == periods
             and len(case['source_observations']) == len(periods),'no Jan1 to priorDec31 fabrication')
        for observation in case['source_observations']:
            need(observation['record_id'] == digest({k:v for k,v in observation.items() if k != 'record_id'}),'exact observation digest')
            need(observation['instrument'] == d['instrument'] and observation['publication_day'] == d['day']
                 and observation['observed_at'] == d['captured_at_utc'] and observation['payload']['document_sha256'] == d['source_sha256']
                 and observation['payload']['announcement_id'] == d['announcement_id'],'source edition/capture timing')
            end=datetime.combine(date.fromisoformat(d['day']),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
            need(observation['public_day_end_at'] == end.isoformat(),'conditional publication-day end')
            need(set(observation['payload']['cells']) == {'revenue','cost_of_sales','total_assets'},'exact three financial fields')
            index=2022-int(observation['fiscal_end'][:4])
            for field,cell in observation['payload']['cells'].items():
                source=direct(cell['page'])
                need(('\n'+source+'\n').count('\n'+cell['row_text']+'\n') == 1,'exact original same-page row block')
                values=re.findall(money,cell['row_text'])
                need(len(values) == 2 and values[index] == cell['literal'] and cell['column_index'] == index
                     and cell['fiscal_end'] == observation['fiscal_end'] and cell['row_text_sha256'] == digest(cell['row_text']),'literal current/prior monetary column')
                label={'revenue':r'^(?:其中[：:]\s*)?营业收入\s*','cost_of_sales':r'^(?:其中[：:]\s*)?营业成本\s*','total_assets':r'^资产总计\s*'}[field]
                need(re.match(label,cell['row_text']) and cell['statement'] == ('合并资产负债表' if field == 'total_assets' else '合并利润表'),'consolidated literal field, no financial proxy')
                need(cell['header_line'] in direct(cell['header_page']),'exact original fiscal header')
                unit=cell['unit'];need(unit in ('元','万元'),'explicit local monetary unit')
                quote=cell['unit_evidence_literal'];need(quote in direct(cell['unit_evidence_page']).splitlines(),'original local unit line')
                normalized=compact(quote).replace('：',':').replace('（','(').replace('）',')')
                explicit=(normalized.endswith('单位:'+unit+'币种:人民币') or normalized.endswith('单位:人民币'+unit)
                          or normalized.endswith('人民币'+unit+')'))
                if not explicit:
                    need(normalized == '单位:'+unit and cell['currency_scope_evidence'],'bare unit needs financial report currency')
                    for evidence in cell['currency_scope_evidence']:
                        text=direct(evidence['page']);literal=evidence['literal'];plain=compact(literal)
                        need(literal in pages[evidence['page']-1] or literal in text,'literal original report currency quote')
                        scope=evidence['scope']
                        if scope == 'EXPLICIT_PRIMARY_FINANCIAL_SECTION_RMB':
                            need(evidence['unit'] == unit and re.fullmatch(r'财务附注中报表的单位为[：:]人民币'+unit,plain),'primary-section RMB declaration')
                        elif scope == 'EXPLICIT_REPORT_PREPARATION_CURRENCY_AND_UNIT':
                            need(evidence['unit'] == unit and re.fullmatch(r'本集团记账本位币和编制本财务报表所采用的货币均为人民币[。；;]除有特别说明外[，,]?均以人民币'+unit+r'为单位表示[。]?',plain),'old complete preparation/unit declaration')
                        else:
                            need(evidence['currency'] == 'CNY' and 'unit' not in evidence,'currency-only evidence must not invent a unit')
                            if scope == 'EXPLICIT_REPORT_PRESENTATION_CURRENCY_ONLY':pattern=r'本财务报表以人民币列示[。；;]'
                            else:
                                need(scope == 'EXPLICIT_REPORT_PREPARATION_CURRENCY_ONLY','known explicit currency scope')
                                pattern=r'(?:(?:本公司|本集团|公司)编制本财务报表时所采用的货币为|本(?:公司|集团)记账本位币和编制本财务报表所采用的货币均为)人民币[。；;]'
                            need(re.fullmatch(pattern,plain),'explicit report currency, not functional currency alone')
                amount=Fraction(cell['literal'].replace(',',''))*(1 if unit == '元' else 10000)
                need(amount == Fraction(cell['value_CNY']) and (amount > 0 if field == 'total_assets' else amount >= 0),'independent exact monetary normalization')
                new_cells+=1
        print('new V5 source cells checked',len(new_docs),key,flush=True)
    need(preserved == 139 and set(outputs) == allowed and len(outputs) == 413,'all139 old successes and exact413 new output files')
    need(summary['status_counts'] == dict(Counter(c['status'] for c in cases.values()))
         and summary['unsupported_error_counts'] == dict(Counter(c['error'] for c in cases.values() if 'error' in c))
         and summary['status_counts_by_exchange'] == {e:dict(Counter(c['status'] for c in cases.values() if c['instrument'].startswith(e))) for e in ('SH','SZ')}
         and summary['newly_supported_documents'] == new_docs and summary['all_V4_supported_reports_preserved_identically'] == preserved
         and summary['source_observation_count'] == observations,'complete actual V5 coverage')
    for flag in ('financial_version_history_complete','historical_arrival_verified','manual_numeric_visual_review_complete',
                 'economic_sector_compatibility_verified','investment_factor_admitted','security_ranking_or_portfolio_returns_computed',
                 '2026_financial_or_market_values_read','objective_achieved'):need(summary[flag] is False,'unearned result gate')
    post={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json') == expected and read(run/'input-postcheck.json') == post and terminal['postcheck'] == post
         and terminal['completed_documents'] == 408 and terminal['pending'] == [] and terminal['original_error'] is None
         and terminal['persistence_errors'] == [],'complete terminal/input journals')
    for key,path in paths.items():need(sha(path) == expected[key],'unchanged input after: '+key)
    need(outputs == {str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'all V5 outputs unchanged')
    report={'status':'PASS_SEPARATE_V5_OLD_OBSERVATION_AND_NEW_SOURCE_CELL_CHECK_NOT_FACTOR_ADMISSION',
        'audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,'all_input_sha256':expected,'all_output_sha256':outputs,
        'documents':408,'source_issuers':391,'source_gaps':gaps,'status_counts':summary['status_counts'],
        'old_supported_reports_preserved_identically':preserved,'old828_cells_reused_from_unchanged_prior_audit':True,
        'newly_supported_documents':new_docs,'new_literal_monetary_cells_checked':new_cells,'direct_original_PDF_pages_checked':direct_pages,
        'production_modules_imported':False,'shares_pypdf6100_with_runner':True,'same_researcher_after_run_started_not_blinded':True,
        'full_consolidated_boundary_grammar_independently_reimplemented':False,'manual_numeric_visual_review_complete':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'economic_sector_compatibility_verified':False,
        'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    with out.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(report['status'],sha(out),new_cells,flush=True)


if __name__=='__main__':main()
