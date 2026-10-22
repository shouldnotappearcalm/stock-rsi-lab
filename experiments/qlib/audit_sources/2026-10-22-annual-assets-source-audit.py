"""Separate whole-corpus/old-cell/native-PDF QA; no production imports.
Reuses prior separate QA header/currency helpers and the same pypdf engine.
"""
import argparse
from collections import Counter
from datetime import date,datetime,time,timezone
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

helper=Path(__file__).with_name('2026-10-22-profitability-all1236-v7-source-cells.py')
spec=importlib.util.spec_from_file_location('prior_separate_source_qa',helper)
oldqa=importlib.util.module_from_spec(spec);spec.loader.exec_module(oldqa)
qa=oldqa.qa
read,sha,need,digest,compact,inventory=qa.read,qa.sha,qa.need,qa.digest,qa.compact,qa.inventory
PARENT='gross-profitability-all1236-header-v7-20261022'
INITIAL='gross-profitability-historical394-initial2022-schema-20261022'
LATER='gross-profitability-all1236-source-v6-20261022'
CONTRACT='CONSOLIDATED_ANNUAL_TOTAL_ASSETS_EDITION_V1'


def section_segment(lines,context):
    if context['kind']=='GLOBAL_UNIQUE_TABLES':return lines
    need(context['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION','known primary-section context')
    starts=[i for i,(_,text) in enumerate(lines) if compact(text)=='二、财务报表']
    need(len(starts)==1,'unique original primary section start')
    start=starts[0]
    ends=[i for i,(_,text) in enumerate(lines) if i>start and compact(text) in
          ('三、公司基本情况','三、财务报表附注','财务报表附注')]
    need(ends,'original following financial-notes/company boundary')
    end=min(ends)
    need(lines[start]==(context['start_page'],context['start_literal'])
         and lines[end]==(context['end_page_exclusive'],context['end_literal'])
         and 0<lines[end][0]-lines[start][0]<=40,'metadata matches earliest actual following section boundary')
    return lines[start:end]


def source_cells(report,document,pages,counters,original_pdf):
    import pypdf
    reader=pypdf.PdfReader(original_pdf);checked=set()
    need(len(reader.pages)==len(pages),'original physical PDF page count')
    def direct(page):
        need(type(page) is int and 1<=page<=len(pages),'bounded physical source page')
        if page not in checked:
            need((reader.pages[page-1].extract_text() or '')==pages[page-1],'direct original PDF/cache page equality')
            checked.add(page);counters['original_PDF_pages_checked']+=1
        return '\n'.join(s.strip() for s in pages[page-1].splitlines() if s.strip())
    identity=qa.source_identity(pages,document['instrument'],document['effective_fiscal_year'])
    need(identity['code_consistent'] and identity['annual_year_consistent'],'separate source cover identity')
    for e in identity['literal_code_evidence']:need(e['literal'] in direct(e['physical_page']),'original security token')
    year=document['effective_fiscal_year']
    need(any(re.search(qa.annual_title_pattern(year),direct(i+1)) for i in range(min(5,len(pages)))),'original annual report title')
    lines=qa.page_lines(pages);balances=report['payload']['balances']
    for period,cell in balances.items():
        context=cell['financial_section_context']
        if context['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION':
            need(context['start_literal'] in direct(context['start_page']) and context['end_literal'] in direct(context['end_page_exclusive']),
                 'original financial section boundary quotes')
        selected=section_segment(lines,context)
        starts=[i for i,(_,t) in enumerate(selected) if qa.title(t)=='合并资产负债表']
        ends=[i for i,(_,t) in enumerate(selected) if qa.title(t)=='母公司资产负债表']
        need(len(starts)==len(ends)==1 and starts[0]<ends[0],'unique consolidated balance before parent')
        segment=selected[starts[0]:ends[0]];row=cell['row_text'];page=cell['page']
        need(segment[-1][0]-segment[0][0]<=5 and segment[0][0]<=page<=segment[-1][0], 'bounded original balance region')
        direct(segment[0][0]);direct(selected[ends[0]][0])
        raw_lines=direct(page).splitlines();quoted=row.splitlines()
        need(sum(raw_lines[i:i+len(quoted)]==quoted for i in range(len(raw_lines)))==1
             and row in '\n'.join(t for _,t in segment) and len(quoted)<=4 and re.match(r'^资产总计\s*',row),
             'unique literal asset row,not parent/profit/total liabilities')
        values=re.findall(r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])',row)
        column=year-int(period[:4])
        need(len(values)==2 and cell['column_index']==column and cell['fiscal_end']==period
             and cell['literal']==values[column] and cell['row_text_sha256']==digest(row)
             and cell['statement']=='合并资产负债表' and cell['parser_contract']==CONTRACT,'exact literal fiscal column')
        value=Fraction(values[column].replace(',',''))*{'元':1,'万元':10000}[cell['unit']]
        need(value>0 and value==Fraction(cell['value_CNY']),'independent exact literal/unit conversion')
        oldqa.verify_headers(cell,year,'total_assets',direct,segment)
        inferred=qa.currency(cell,direct,pages,context,year)
        counters['CAS_inferred_new_cells']+=inferred
        comparison=cell['reported_comparative_balance_date']
        expected={f'{year}-12-31',f'{year-1}-12-31'} if comparison==f'{year-1}-12-31' else {f'{year}-12-31'}
        need(set(balances)==expected,'no Jan1/undated opening to priorDecember31 backfill')
        counters['new_asset_cells_checked']+=1


def main():
    import pypdf
    need(pypdf.__version__=='6.10.0','same authenticated original-cache text extractor')
    p=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();root,base,membership,request,run,output=(Path(getattr(a,k)).resolve() for k in
        ('repo_root','source_root','membership_file','request','run_dir','output'))
    need(not output.exists() and not output.is_relative_to(run),'fresh external asset QA output')
    need(sha(request)==a.expected_request_sha256,'frozen asset request')
    req=read(request);need(req['document_count']==1236 and req['old_GP_supported_reports']==791 and req['old_GP_asset_cell_count']==1243,
        'complete registered source/control scope')
    partial={**req,'input_sha256':{k:v for k,v in req['input_sha256'].items() if k!='membership'}}
    paths=qa.paths_for(partial,root,base,membership,request);paths['frozen_request']=paths.pop('frozen_source_request')
    if 'membership' in req['input_sha256']:paths['membership']=membership
    expected={**req['input_sha256'],'frozen_request':a.expected_request_sha256}
    for key,path in paths.items():need(sha(path)==expected[key],'input before '+key)
    old=read(base/PARENT/'case_results.json');cases=read(run/'case_results.json');summary=read(run/'summary.json');terminal=read(run/'terminal.json')
    need(set(cases)==set(old)=={d['capture_key'] for d in req['documents']},'all1236 cases/editions retained')
    outputs=inventory(run);allowed={d['capture_key']+'.json' for d in req['documents']}|{
        'case_results.json','input-before.json','input-postcheck.json','terminal.json','summary.json','visibility-checks.json'}
    need(set(outputs)==allowed and len(outputs)==1242 and read(run/'input-before.json')==expected,'exact1242 files and complete input inventory')
    post=read(run/'input-postcheck.json')
    need(post['all_inputs_unchanged'] and not post['mismatches'] and post['count']==len(paths)
         and terminal['completed_documents']==1236 and not terminal['pending'] and terminal['original_error'] is None
         and not terminal['persistence_errors'],'complete unchanged source termination')
    counters=Counter();reports=[];new=[];states=Counter();strategies=Counter()
    for document in req['documents']:
        key=document['capture_key'];case=cases[key];previous=old[key]
        need(case==read(run/(key+'.json')) and case['instrument']==document['instrument']
             and case['source_sha256']==document['source_sha256'] and case['fiscal_year']==document['effective_fiscal_year']
             and case['parent_case_sha256']==sha(base/PARENT/(key+'.json')) and case['GP_source_status']==previous['status'], 'case source identity')
        states[case['status']]+=1;strategies[case['source_strategy']]+=1
        report=case['asset_report']
        if report is None:
            need(case['status'] in ('COVER_IDENTITY_UNVERIFIED','ASSET_SOURCE_SCHEMA_UNSUPPORTED'),'explicit unresolved source state')
            need(not previous['source_observations'],'old successful assets cannot disappear')
            if case['status']=='COVER_IDENTITY_UNVERIFIED':need(not(previous['cover_code_consistent'] and previous['cover_annual_year_consistent']),'unverified identity retained')
            continue
        need(case['status']=='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA' and report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'})
             and report['contract']==CONTRACT and report['instrument']==document['instrument']
             and report['report_year']==document['effective_fiscal_year'] and report['publication_day']==document['day']
             and datetime.fromisoformat(report['observed_at'])==datetime.fromisoformat(document['captured_at_utc'])
             and report['payload']['document_sha256']==document['source_sha256'] and report['payload']['announcement_id']==document['announcement_id']
             and report['payload']['scope']=='CONSOLIDATED','coherent one-document edition')
        public=datetime.combine(date.fromisoformat(document['day']),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
        need(report['public_day_end_at']==public.isoformat(),'conservative public-day end')
        for flag in ('financial_version_history_complete','historical_arrival_verified','financial_reporting_compatibility_verified','investment_factor_admitted'):
            need(report[flag] is False,'source-only report evidence limits')
        balances=report['payload']['balances'];year=document['effective_fiscal_year']
        need(f'{year}-12-31' in balances and set(balances)<={f'{year}-12-31',f'{year-1}-12-31'},'bounded annual dates')
        if previous['source_observations']:
            need(case['source_strategy']=='REUSE_AUDITED_GP_ASSET_CELLS' and balances=={
                o['fiscal_end']:o['payload']['cells']['total_assets'] for o in previous['source_observations']}
                 and case['source_GP_record_ids']==[o['record_id'] for o in previous['source_observations']], 'all old asset cells/record IDs preserved verbatim')
            counters['old_supported_reports_preserved']+=1;counters['old_asset_cells_preserved']+=len(balances)
        else:
            need(case['source_strategy']=='BALANCE_ONLY_FROM_AUTHENTICATED_CACHE','new asset source does not rewrite old cells')
            folder=INITIAL if document['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER
            cachefile=base/folder/(key+'.pages.json');cache=read(cachefile);pages=cache['pages']
            need(case['source_page_cache_sha256']==sha(cachefile) and cache['source_sha256']==document['source_sha256']
                 and len(pages)==case['page_count'] and cache['extractor']=='pypdf6.10.0'
                 and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}==previous['all_extracted_page_text_sha256'], 'authenticated original text cache')
            source_cells(report,document,pages,counters,base/document['source_path']);new.append(key)
        reports.append(report)
    need(counters['old_supported_reports_preserved']==791 and counters['old_asset_cells_preserved']==1243,'complete protected old-asset controls')
    need(summary['document_count']==1236 and summary['status_counts']==dict(states) and summary['source_strategy_counts']==dict(strategies)
         and summary['asset_report_count']==len(reports) and summary['asset_cell_count']==sum(len(r['payload']['balances']) for r in reports)
         and summary['paired_explicit_annual_report_count']==sum(len(r['payload']['balances'])==2 for r in reports)
         and summary['newly_supported_documents']==new,'independent whole-corpus counts')
    visibility=read(run/'visibility-checks.json')
    for year in (2024,2025):
        clock=datetime.fromisoformat(f'{year}-12-31T15:05:00+08:00')
        for mode in ('OBSERVED','RECONSTRUCTED_PUBLICATION_DAY_END'):
            visible=[]
            for r in reports:
                public,observed=datetime.fromisoformat(r['public_day_end_at']),datetime.fromisoformat(r['observed_at'])
                if clock>=(max(public,observed) if mode=='OBSERVED' else public):visible.append(r['record_id'])
            need(visibility[str(year)+'/'+mode]=={'count':len(visible),'record_ids':visible,'all_visible_supported_editions_not_latest_eligibility':True},
                 'all-edition dual-clock source checks,not investment eligibility')
    need(summary['observed_pre2026_reports_visible']==0,'default observed sources hidden historically')
    for flag in ('historical_arrival_verified','financial_version_history_complete','investment_factor_admitted',
                 'asset_growth_values_or_stock_ranks_computed','portfolio_returns_computed','2026_financial_or_market_values_read','objective_achieved'):
        need(summary[flag] is False,'summary evidence limit')
    for key,path in paths.items():need(sha(path)==expected[key],'input after '+key)
    need(inventory(run)==outputs,'all asset outputs unchanged through QA')
    result={'status':'SEPARATE_ASSET_CORPUS_AND_NEW_ORIGINAL_PDF_CELL_AUDIT_PASSED_NOT_FACTOR_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'prior_separate_QA_helper_sha256':sha(helper),'request_sha256':a.expected_request_sha256,
        'all_input_sha256':expected,'all_output_sha256':outputs,'all_inputs_and_outputs_unchanged':True,
        'document_count':len(cases),'asset_report_count':len(reports),'newly_supported_report_count':len(new),**dict(counters),
        'no_production_imports':True,'shared_prior_separate_header_currency_QA':True,'shared_pypdf6_10_0_engine':True,
        'same_researcher_after_source_run':True,'complete_manual_numeric_visual_review':False,
        'investment_factor_admitted':False,'objective_achieved':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if not k.startswith('all_')},ensure_ascii=False))


if __name__=='__main__':main()
