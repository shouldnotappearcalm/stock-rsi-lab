"""Separate V7 current-date/column/source QA; reuses prior separate QA helpers.
No production imports. Shared pypdf and same researcher after run start.
"""
import argparse
from collections import Counter
from datetime import date,datetime,time,timezone
from fractions import Fraction
import importlib.util
from pathlib import Path
import re
from zoneinfo import ZoneInfo

helper=Path(__file__).with_name('2026-10-22-profitability-all1236-v6-source-cells.py')
spec=importlib.util.spec_from_file_location('previous_separate_source_QA',helper)
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
read,need,sha,digest,compact,inventory=qa.read,qa.need,qa.sha,qa.digest,qa.compact,qa.inventory
OLD='gross-profitability-all1236-source-v6-20261022'
SUPPORTED=qa.SUPPORTED
NOTE=r'(?:附注(?:[一二三四五六七八九十百]{1,4}|（[一二三四五六七八九十百]{1,4}）|\([一二三四五六七八九十百]{1,4}\))?)?'


def admitted_periods(case):
    year=case['fiscal_year'];observations=case['source_observations']
    need(observations,'supported source needs observations')
    balance=observations[0]['payload']['cells']['total_assets'];comparison=balance['reported_comparative_balance_date']
    if balance.get('comparative_date_is_unresolved'):
        need(comparison is None and balance['balance_header_semantics']=='GENERIC_CURRENT_AND_UNDATED_OPENING'
             and balance['current_column_date_is_inferred_from_explicit_statement_date'] is True,'generic opening date must remain null and inference labelled')
        periods={f'{year}-12-31'}
    else:
        need(comparison in (f'{year}-01-01',f'{year-1}-12-31'),'only explicit comparative balance dates admitted')
        periods={f'{year}-12-31'} if comparison==f'{year}-01-01' else {f'{year}-12-31',f'{year-1}-12-31'}
    need({o['fiscal_end'] for o in observations}==periods and len(observations)==len(periods),'no fabricated opening-column comparative observation')
    return periods


def verify_anchor(cell,year,direct,segment):
    need(cell['comparative_date_is_unresolved'] is True and cell['reported_comparative_balance_date'] is None
         and cell['current_column_date_is_inferred_from_explicit_statement_date'] is True,'date inference must be explicit')
    a=cell['balance_current_date_anchor'];page=cell['header_page'];header=cell['header_line']
    need(a['page']==page and a['date']==f'{year}-12-31' and compact(a['literal'])==f'{year}年12月31日'
         and a['scope']=='SAME_PAGE_STATEMENT_DATE_BEFORE_GENERIC_BALANCE_HEADER' and 1<=len(a['literal'].splitlines())<=7,'one same-page quoted annual date')
    local='\n'.join(t for p,t in segment if p==page)
    need(('\n'+header+'\n') in ('\n'+local+'\n') and ('\n'+a['literal']+'\n') in ('\n'+direct(page)+'\n'),'original date and generic column quotes')
    prefix=local.split(header,1)[0]
    source_lines,quoted=prefix.splitlines(),a['literal'].splitlines()
    need(sum(source_lines[i:i+len(quoted)]==quoted for i in range(len(source_lines)))==1,'unique selected statement date before its generic header')


def verify_headers(cell,year,field,direct,segment):
    occurrences=cell['header_occurrences'];need(1<=len(occurrences)<=6 and len({e['page'] for e in occurrences})==len(occurrences),'bounded distinct continuation pages')
    need(occurrences[0]=={'page':cell['header_page'],'literal':cell['header_line']}
         and [e['page'] for e in occurrences]==sorted(e['page'] for e in occurrences),'primary/continuation source order')
    if field!='total_assets':suffix=f'{year}年度{year-1}年度'
    elif cell.get('comparative_date_is_unresolved'):
        suffix='期末余额期初余额';verify_anchor(cell,year,direct,segment)
    else:
        comparison=cell['reported_comparative_balance_date']
        suffix=f'{year}年12月31日'+(f'{year}年1月1日' if comparison==f'{year}-01-01' else f'{year-1}年12月31日')
        need(cell['balance_current_date_anchor'] is None and cell['current_column_date_is_inferred_from_explicit_statement_date'] is False,'explicit calendar header has no generic date inference')
    expected=compact(cell['header_line']);need(re.fullmatch('项目'+NOTE+re.escape(suffix),expected),'exact source fiscal/period labels')
    for e in occurrences:
        need(compact(e['literal'])==expected and 1<=len(e['literal'].splitlines())<=20,'identical bounded continuation header')
        qa.verify_source_header(e['literal'],e['page'],direct,segment)


def main():
    import pypdf
    need(pypdf.__version__=='6.10.0','registered shared PDF extractor')
    p=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();root,base,membership,request,run,out=map(lambda x:Path(x).resolve(),(a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external QA output')
    need(sha(request)==a.expected_request_sha256,'frozen V7 source request')
    req=read(request)
    need(req['status']=='FROZEN_BEFORE_ALL1236_CURRENT_DATE_ANCHORED_HEADER_V7_SOURCE_INSPECTION' and req['document_count']==1236
         and req['old_supported_report_count']==665 and req['new_PDF_text_decodings_permitted'] is False
         and req['generic_opening_balance_date_must_remain_unresolved'] is True and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'full1236 source-only V7 scope')
    paths=qa.paths_for(req,root,base,membership,request);expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    need(len(paths)==12760,'complete V7 input closure')
    for key,path in paths.items():need(sha(path)==expected[key],'input before: '+key)
    old_audit=read(root/'experiments/qlib/profitability-all1236-v6-source-audit.json')
    need(old_audit['audit_code_sha256']==sha(helper) and inventory(base/OLD)==old_audit['all_output_sha256'],'unchanged audited complete V6 corpus')
    old_req=read(root/'experiments/qlib/profitability-all1236-v6-request.json')
    need(old_audit['all_input_sha256']=={**old_req['input_sha256'],'frozen_source_request':'fc7ddecfac53f0d478180ecac7013f1dc6fe8460cc2be41fed7571d0418870f9'},'old complete input audit')
    docs=req['documents'];old=read(base/OLD/'case_results.json');cases,summary,terminal=(read(run/name) for name in ('case_results.json','summary.json','terminal.json'))
    need(docs==old_req['documents'] and len(docs)==1236 and len({d['announcement_id'] for d in docs})==1236
         and set(cases)==set(old)=={d['capture_key'] for d in docs},'same full originals/editions/cases')
    outputs=inventory(run);allowed={'input-before.json','input-postcheck.json','terminal.json','case_results.json','summary.json'}
    for start in range(0,len(docs),4):
        name='batch-'+str(start//4).zfill(3)+'.json';allowed.add(name)
        need(read(run/name)=={'capture_keys':[d['capture_key'] for d in docs[start:start+4]]},'same source-order batch')
    new,preserved,generic,observations,direct_pages,cell_count=[],0,[],0,0,0
    money=r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
    for d in docs:
        key=d['capture_key'];c=cases[key];before=old[key];year=d['effective_fiscal_year'];allowed.add(key+'.json')
        need(c==read(run/(key+'.json')) and c['source_sha256']==d['source_sha256']==before['source_sha256']
             and c['V6_source_status']==before['status'] and c['V6_source_error']==before.get('error')
             and c['identity_evidence']==before['identity_evidence'] and c['all_extracted_page_text_sha256']==before['all_extracted_page_text_sha256'],'old/new source case provenance')
        for flag in ('investment_factor_admitted','financial_version_history_complete','historical_arrival_verified','economic_sector_compatibility_verified','manual_numeric_visual_review_complete'):need(c[flag] is False,'source-only flag')
        folder=base/qa.CACHE if d['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else base/OLD
        cache=read(folder/(key+'.pages.json'));pages=cache['pages']
        need(cache['source_sha256']==d['source_sha256'] and cache['extractor']=='pypdf6.10.0'
             and c['page_count']==len(pages) and c['all_extracted_page_text_sha256']=={str(i+1):__import__('hashlib').sha256(t.encode()).hexdigest() for i,t in enumerate(pages)},'exact authenticated complete text cache')
        need(c['identity_evidence']==qa.source_identity(pages,d['instrument'],year),'same source-scoped issuer/year identity')
        observations+=len(c['source_observations'])
        if before['source_observations']:
            need(c['status']==SUPPORTED and c['source_observations']==before['source_observations'],'all old complete financial observations unchanged')
            preserved+=1
        if c['status']!=SUPPORTED:
            need(c['status'] in ('SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED') and c['source_observations']==[],'all unsupported cases retained without values')
            continue
        admitted_periods(c)
        if any(o['payload']['cells']['total_assets'].get('comparative_date_is_unresolved') for o in c['source_observations']):generic.append(key)
        if before['source_observations']:continue
        new.append(key);reader=pypdf.PdfReader(base/d['source_path']);checked=set();need(len(reader.pages)==len(pages),'original physical page count')
        def direct(page):
            nonlocal direct_pages
            need(type(page) is int and 1<=page<=len(pages),'physical page bound')
            if page not in checked:
                need((reader.pages[page-1].extract_text() or '')==pages[page-1],'direct original PDF page')
                checked.add(page);direct_pages+=1
            return '\n'.join(t.strip() for t in pages[page-1].splitlines() if t.strip())
        for e in c['identity_evidence']['literal_code_evidence']:need(e['literal'] in direct(e['physical_page']),'direct source issuer code')
        need(any(re.search(qa.annual_title_pattern(year),direct(i+1)) for i in range(min(5,len(pages)))),'direct annual report title')
        lines=qa.page_lines(pages)
        for o in c['source_observations']:
            need(o['record_id']==digest({k:v for k,v in o.items() if k!='record_id'}) and o['instrument']==d['instrument']
                 and o['publication_day']==d['day'] and o['observed_at']==d['captured_at_utc']
                 and o['payload']['document_sha256']==d['source_sha256'] and o['payload']['announcement_id']==d['announcement_id'],'complete observation identity and availability metadata')
            need(o['public_day_end_at']==datetime.combine(date.fromisoformat(d['day']),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).isoformat(),'conditional publication-day end')
            need(set(o['payload']['cells'])=={'revenue','cost_of_sales','total_assets'},'three literal financial fields')
            col=year-int(o['fiscal_end'][:4])
            for field,cell in o['payload']['cells'].items():
                source=direct(cell['page']);row=cell['row_text'];values=re.findall(money,row)
                need(('\n'+source+'\n').count('\n'+row+'\n')==1 and len(row.splitlines())<=4 and len(values)==2
                     and values[col]==cell['literal'] and cell['column_index']==col and cell['fiscal_end']==o['fiscal_end']
                     and cell['row_text_sha256']==digest(row),'exact same-page two-cell row/current-comparative column')
                need(re.match({'revenue':r'^(?:其中[：:]\s*)?营业收入\s*','cost_of_sales':r'^(?:其中[：:]\s*)?营业成本\s*','total_assets':r'^资产总计\s*'}[field],row),'literal financial field not proxy')
                context=cell['financial_section_context'];selected=lines
                if context['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION':
                    need(context['start_literal'] in direct(context['start_page']) and context['end_literal'] in direct(context['end_page_exclusive']),'direct primary financial boundaries')
                    starts=[i for i,(p,t) in enumerate(lines) if p==context['start_page'] and t==context['start_literal']]
                    ends=[i for i,(p,t) in enumerate(lines) if p==context['end_page_exclusive'] and t==context['end_literal']]
                    need(len(starts)==len(ends)==1 and starts[0]<ends[0],'unique primary section positions');selected=lines[starts[0]:ends[0]]
                else:need(context['kind']=='GLOBAL_UNIQUE_TABLES','known source section scope')
                statement='合并资产负债表' if field=='total_assets' else '合并利润表';following='母公司资产负债表' if field=='total_assets' else '母公司利润表'
                starts=[i for i,(_,t) in enumerate(selected) if qa.title(t)==statement];ends=[i for i,(_,t) in enumerate(selected) if qa.title(t)==following]
                need(cell['statement']==statement and len(starts)==len(ends)==1 and starts[0]<ends[0],'consolidated before parent, no substitute table')
                segment=selected[starts[0]:ends[0]];region='\n'.join(t for _,t in segment)
                need(row in region and segment[0][0]<=cell['page']<=segment[-1][0] and segment[-1][0]-segment[0][0]<=5,'row inside bounded consolidated source table')
                direct(segment[0][0]);direct(selected[ends[0]][0]);verify_headers(cell,year,field,direct,segment)
                need(cell['unit_evidence_literal'] in region and segment[0][0]<=cell['unit_evidence_page']<=segment[-1][0],'local consolidated monetary unit')
                qa.currency(cell,direct,pages,context,year)
                need(cell['unit'] in ('元','万元'),'explicit source unit')
                value=Fraction(cell['literal'].replace(',',''))*(1 if cell['unit']=='元' else 10000)
                need(value==Fraction(cell['value_CNY']) and (value>0 if field=='total_assets' else value>=0),'independent rational monetary normalization')
                cell_count+=1
        print('V7 separate new source cells',len(new),key,cell_count,flush=True)
    need(len(outputs)==1550 and set(outputs)==allowed and preserved==665,'all1550 outputs and665 protected successes')
    need(summary['status']=='WHOLE1236_V7_SOURCE_INSPECTED_NOT_FACTOR_ADMITTED' and summary['request_sha256']==a.expected_request_sha256
         and summary['document_count']==1236 and summary['source_range_issuer_count']==394 and summary['input_count']==len(paths)
         and summary['all_inputs_unchanged'] is True and summary['all_cached_text_reused'] is True and summary['original_PDF_text_decodings_performed']==0,'complete cached source result')
    need(summary['status_counts']==dict(Counter(c['status'] for c in cases.values()))
         and summary['status_counts_by_fiscal_year']=={str(y):dict(Counter(c['status'] for c in cases.values() if c['fiscal_year']==y)) for y in sorted({c['fiscal_year'] for c in cases.values()})}
         and summary['status_counts_by_exchange']=={e:dict(Counter(c['status'] for c in cases.values() if c['instrument'].startswith(e))) for e in ('SH','SZ')}
         and summary['unsupported_error_counts']==dict(Counter(c['error'] for c in cases.values() if 'error' in c)),'full actual coverage counts')
    complete=sorted({c['instrument'] for c in cases.values() if all(any(x['instrument']==c['instrument'] and x['fiscal_year']==y and x['source_observations'] for x in cases.values()) for y in (2022,2023,2024))})
    need(summary['source_observation_count']==observations and summary['old_supported_reports_preserved_identically']==preserved
         and summary['newly_supported_documents']==new and summary['generic_balance_current_only_documents']==generic
         and summary['issuers_with_supported_current_reports_2022_2023_2024']==complete
         and summary['supported_source_issuer_count']==len({c['instrument'] for c in cases.values() if c['source_observations']}),'new/current-only/old conservation and three-year coverage')
    for flag in ('investment_factor_admitted','financial_version_history_complete','historical_arrival_verified','economic_sector_compatibility_verified',
                 'manual_numeric_visual_review_complete','security_ranking_or_portfolio_returns_computed','2026_financial_or_market_values_read','objective_achieved'):need(summary[flag] is False,'no unearned evidence gate')
    post={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json')==expected and read(run/'input-postcheck.json')==post and terminal['postcheck']==post
         and terminal['completed_documents']==1236 and terminal['submitted_keys']==[d['capture_key'] for d in docs]
         and terminal['pending']==[] and terminal['original_error'] is None and terminal['persistence_errors']==[],'complete unchanged-input/terminal journals')
    for key,path in paths.items():need(sha(path)==expected[key],'input after: '+key)
    need(inventory(run)==outputs,'all V7 outputs unchanged during QA')
    report={'status':'PASS_SEPARATE_ALL1236_V7_CURRENT_DATE_AND_SOURCE_CELL_CHECK_NOT_FACTOR_ADMISSION',
        'audit_code_sha256':sha(__file__),'prior_separate_QA_helper_sha256':sha(helper),'request_sha256':a.expected_request_sha256,
        'all_input_sha256':expected,'all_output_sha256':outputs,'document_count':1236,'dated_source_issuer_count':394,'status_counts':summary['status_counts'],
        'old_supported_reports_preserved_identically':preserved,'old_unchanged_source_cell_audit_reused':True,'newly_supported_documents':new,
        'new_literal_monetary_cells_checked':cell_count,'direct_original_PDF_pages_checked':direct_pages,'generic_balance_current_only_documents':generic,
        'generic_opening_fiscal_dates_or_comparative_observations_invented':False,'three_year_parse_issuer_count_not_investment_universe':len(complete),
        'production_modules_imported':False,'reuses_prior_separate_QA_helpers':True,'shares_pypdf6100_with_runner':True,
        'same_researcher_after_run_started_not_blinded':True,'full_consolidated_boundary_grammar_independently_reimplemented':False,
        'every_cached_page_independently_redecoded':False,'manual_numeric_visual_review_complete':False,'historical_arrival_verified':False,
        'financial_version_history_complete':False,'economic_sector_compatibility_verified':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    import json
    with out.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(report['status'],sha(out),cell_count,direct_pages,flush=True)


if __name__=='__main__':main()
