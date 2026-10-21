"""Separate V4 original-page checks; same researcher/extractor, not blinded."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re


def need(v, why):
    if not v: raise AssertionError(why)
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def compact(s): return re.sub(r'\s+','',s)


def main():
    import pypdf
    need(pypdf.__version__ == '6.10.0', 'fixed shared text extractor')
    parser = argparse.ArgumentParser()
    for name in ('repo-root','source-root','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();root,base,request,run,out=map(lambda p:Path(p).resolve(),(a.repo_root,a.source_root,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external audit result')
    need(sha(request)==a.expected_request_sha256,'frozen V4 request identity');req=read(request)
    need(req['status']=='FROZEN_BEFORE_SAME36_SOURCE_CONTEXT_V4_REPAIR' and req['document_count']==36
         and req['security_ranking_or_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'same36 source-only scope')
    expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256};paths={'frozen_source_request':request}
    for key in req['input_sha256']:
        prefix,name=key.split('/',1)
        need(prefix in ('repo','source') and not Path(name).is_absolute() and '..' not in Path(name).parts,'safe bound input')
        paths[key]=(root if prefix=='repo' else base)/name
    need(len(paths)==443,'complete443 bound inputs')
    for key,p in paths.items(): need(sha(p)==expected[key],'unchanged input before source check: '+key)
    outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    cases,summary,terminal=map(lambda n:read(run/n),('case_results.json','summary.json','terminal.json'))
    docs=read(base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json')
    prior=read(base/'gross-profitability-fixed12-grammar-v2-20261022/case_results.json')
    need(set(cases)=={d['capture_key'] for d in docs} and len(cases)==36 and len(outputs)==41,'all36 source cases/41 outputs')
    supported='SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW';checked,preserved=0,0;checked_docs=[];opening=[]
    money=r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
    for d in docs:
        key=d['capture_key'];case=cases[key]
        need(case==read(run/(key+'.json')) and case['source_sha256']==d['source_sha256'],'source/case conservation')
        need(case['all_extracted_page_text_sha256']==prior[key]['all_extracted_page_text_sha256'],'all36 full-page text hash inventories unchanged')
        for flag in ('financial_version_history_complete','historical_arrival_verified','economic_sector_compatibility_verified','manual_numeric_visual_review_complete','investment_factor_admitted'):
            need(case[flag] is False,'no unearned data admission')
        if case['status']!=supported:
            need(case['source_observations']==[] and prior[key]['status']!=supported,'no rejected values or lost V2 success')
            continue
        need(sha(base/d['source_path'])==d['source_sha256'],'original PDF bytes')
        reader=pypdf.PdfReader(base/d['source_path']);cache={}
        def page_lines(page):
            if page not in cache:
                text=reader.pages[page-1].extract_text() or ''
                need(hashlib.sha256(text.encode()).hexdigest()==case['all_extracted_page_text_sha256'][str(page)],'direct original page text hash')
                cache[page]=[t.strip() for t in text.splitlines() if t.strip()]
            return cache[page]
        balance=case['source_observations'][0]['payload']['cells']['total_assets']
        current=f"{d['fiscal_year']}-12-31";comparison=balance['reported_comparative_balance_date']
        periods={current} if comparison==f"{d['fiscal_year']}-01-01" else {current,f"{d['fiscal_year']-1}-12-31"}
        need({o['fiscal_end'] for o in case['source_observations']}==periods
             and len(case['source_observations'])==len(periods),'opening balance cannot fabricate prior-year GP record')
        if len(periods)==1:opening.append(key)
        context=balance['financial_section_context']
        if context['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION':
            first,last=context['start_page'],context['end_page_exclusive']
            scope=[(p,line) for p in range(first,last+1) for line in page_lines(p)]
            starts=[i for i,(p,t) in enumerate(scope) if p==first and t==context['start_literal']]
            ends=[i for i,(p,t) in enumerate(scope) if p==last and t==context['end_literal']]
            need(len(starts)==len(ends)==1 and starts[0]<ends[0] and last-first<=40,'literal primary-section bounds')
            scope=scope[starts[0]:ends[0]]
        else:
            need(context['kind']=='GLOBAL_UNIQUE_TABLES','known statement context')
            scope=[(p,line) for p in range(1,len(reader.pages)+1) for line in page_lines(p)]
        def heading_positions(title):
            matches=[]
            for i,(p,t) in enumerate(scope):
                normalized=compact(t)
                direct=re.sub(r'^\d{1,2}[、.．]','',normalized)==title
                split=(normalized=='、'+title and i>0 and scope[i-1][0]==p and re.fullmatch(r'\d{1,2}',compact(scope[i-1][1])))
                if direct or split:matches.append(i)
            need(len(matches)==1,'unique literal heading inside source section: '+title)
            return matches[0]
        boundaries={t:heading_positions(t) for t in ('合并资产负债表','母公司资产负债表','合并利润表','母公司利润表')}
        for o in case['source_observations']:
            need(o['record_id']==digest({k:v for k,v in o.items() if k!='record_id'}),'record digest')
            need(o['instrument']==d['instrument'] and o['publication_day']==d['day'] and o['observed_at']==d['captured_at_utc']
                 and o['payload']['document_sha256']==d['source_sha256'] and o['payload']['announcement_id']==d['announcement_id'],'source/capture chronology')
            index=d['fiscal_year']-int(o['fiscal_end'][:4]);need(index in (0,1),'current/comparative index')
            for field,cell in o['payload']['cells'].items():
                title='合并资产负债表' if field=='total_assets' else '合并利润表';parent='母公司资产负债表' if field=='total_assets' else '母公司利润表'
                lo,hi=boundaries[title],boundaries[parent];need(lo<hi and cell['statement']==title,'consolidated before parent')
                page=cell['page'];block='\n'+cell['row_text']+'\n';selected='\n'+'\n'.join(t for p,t in scope[lo+1:hi] if p==page)+'\n'
                need(selected.count(block)==1,'exact source row block within consolidated range')
                amounts=re.findall(money,cell['row_text']);need(len(amounts)==2 and amounts[index]==cell['literal'] and cell['column_index']==index,'literal fiscal monetary column')
                need(cell['row_text_sha256']==digest(cell['row_text']) and cell['fiscal_end']==o['fiscal_end'],'literal row/fiscal evidence')
                need(cell['header_line'] in '\n'.join(page_lines(cell['header_page'])),'exact original fiscal header')
                unit=cell['unit'];need(unit in ('元','万元'),'supported explicit monetary unit')
                unit_literal=cell['unit_evidence_literal'];need(unit_literal in page_lines(cell['unit_evidence_page']),'original table unit literal')
                if re.fullmatch(r'单位[：:]'+unit+r'币种[：:]人民币',compact(unit_literal)) is None:
                    need(re.fullmatch(r'单位[：:]'+unit,compact(unit_literal)) and cell['currency_scope_evidence'],'bare unit needs explicit evidence')
                    for evidence in cell['currency_scope_evidence']:
                        quote=evidence['literal'];need(quote in '\n'.join(page_lines(evidence['page'])) and evidence['unit']==unit,'original currency scope quotation')
                        if evidence['scope']=='EXPLICIT_PRIMARY_FINANCIAL_SECTION_RMB':
                            need(any(p==evidence['page'] and t==quote for p,t in scope[:12]) and re.fullmatch(r'财务附注中报表的单位为[：:]人民币'+unit,compact(quote)),'primary-section RMB declaration')
                        else:
                            need(evidence['scope']=='EXPLICIT_REPORT_PREPARATION_CURRENCY_AND_UNIT' and re.fullmatch(
                                r'本集团记账本位币和编制本财务报表所采用的货币均为人民币[。；;]除有特别说明外[，,]?均以人民币'+unit+r'为单位表示[。]?',compact(quote)),
                                'report-preparation currency, not functional currency alone')
                need(Fraction(cell['value_CNY'])==Fraction(cell['literal'].replace(',',''))*(1 if unit=='元' else 10000),'independent exact monetary normalization')
                checked+=1
        if prior[key]['status']==supported:
            new={o['fiscal_end']:o for o in case['source_observations']}
            for before in prior[key]['source_observations']:
                for field,cell in before['payload']['cells'].items():
                    for name in ('value_CNY','literal','column_index','page','statement','fiscal_end'):
                        need(new[before['fiscal_end']]['payload']['cells'][field][name]==cell[name],'all old V2 numeric cells/source coordinates preserved')
                    preserved+=1
        checked_docs.append(key)
    need(checked==69 and preserved==48 and len(checked_docs)==13,'all actual supported source cells covered')
    need(summary['status_counts']==dict(Counter(c['status'] for c in cases.values())) and summary['source_observations']==23
         and summary['current_only_opening_balance_reports']==opening and summary['investment_factor_admitted'] is False,'V4 summary/source coverage')
    post={'all_inputs_unchanged':True,'count':443,'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json')==expected and read(run/'input-postcheck.json')==post and terminal['postcheck']==post
         and terminal['completed_documents']==36 and terminal['pending']==[] and terminal['original_error'] is None and terminal['persistence_errors']==[],'successful terminal/input journals')
    for key,p in paths.items():need(sha(p)==expected[key],'unchanged input after source check: '+key)
    need(outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'output bytes unchanged')
    report={'status':'PASS_SEPARATE_V4_SOURCE_CELL_AND_OPENING_DATE_CHECK_NOT_FACTOR_ADMISSION','audit_code_sha256':sha(__file__),
        'request_sha256':a.expected_request_sha256,'all443_input_sha256':expected,'all41_output_sha256':outputs,
        'original_PDF_cells_checked':checked,'V2_numeric_cells_preserved':preserved,'checked_documents':checked_docs,
        'current_only_opening_balance_reports':opening,'production_modules_imported':False,
        'shares_pypdf6100_with_runner':True,'authored_after_run_same_researcher_not_blinded':True,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'economic_sector_compatibility_verified':False,
        'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(report['status'],sha(out),checked)


if __name__=='__main__':main()
