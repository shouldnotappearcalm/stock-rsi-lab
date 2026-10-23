"""Separate source/context QA plus pdfminer row geometry; no production imports."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import date,datetime,time,timezone
import hashlib,importlib.util,json,re
from pathlib import Path
from zoneinfo import ZoneInfo

WORKERS=4
MONEY=r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
SPACED_MONEY=r'(?<![\d,.])-?(?:\d(?:\s*\d){0,2}(?:\s*,\s*\d(?:\s*\d){2})+|\d(?:\s*\d)*)\s*\.\s*\d\s*\d(?![\d,.])'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def compact(v):return re.sub(r'\s+','',v)
def need(x,m):
    if not x:raise ValueError(m)
def load(p,name):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}


def asset_row(lines,expected_values):
    """Pair the literal label and two monetary columns at the same physical row."""
    headers=[v for v in lines if re.fullmatch(r'(?:\d+[、.])?合并资产负债表',compact(v[4]))]
    parents=[v for v in lines if re.fullmatch(r'(?:\d+[、.])?母公司资产负债表',compact(v[4]))]
    matched=[]
    for label in lines:
        if not compact(label[4]).startswith('资产总计'):continue
        y=(label[1]+label[3])/2
        if headers and not any(y<(v[1]+v[3])/2 for v in headers):continue
        if parents and not any(y>(v[1]+v[3])/2 for v in parents):continue
        def same_row(v):
            height=min(label[3]-label[1],v[3]-v[1])
            overlap=min(label[3],v[3])-max(label[1],v[1])
            return height>0 and overlap>=height/2
        group=sorted((v for v in lines if same_row(v)),key=lambda v:v[0])
        text=' '.join(v[4] for v in group);values=[compact(v) for v in re.findall(SPACED_MONEY,text)]
        if values==expected_values:matched.append({'literal_values':values,'row_mid_y':y,'text':text,
            'line_boxes':[[*v[:4],v[4]] for v in group]})
    need(len(matched)==1,'one unambiguous pdfminer consolidated asset row with exact same-height monetary columns')
    return matched[0]


def native_checker(repo):
    evidence=read(Path(repo)/'experiments/qlib/annual-assets-all1236-source-audit.json')
    path=Path(__file__).with_name('2026-10-22-annual-assets-source-audit.py')
    need(sha(path)==evidence['audit_code_sha256'],'pinned prior separate annual-assets checker')
    native=load(path,'prior_separate_asset_source_native');hashes={str(path):sha(path)};stack=[native];seen=set()
    while stack:
        m=stack.pop();p=getattr(m,'__file__',None)
        if not p or p in seen:continue
        seen.add(p);hashes[p]=sha(p)
        rel=str(Path(p).relative_to(Path(repo)))
        old=evidence['all_input_sha256'].get('repo/'+rel)
        if old:need(hashes[p]==old,'unchanged previous shared QA helper')
        for attr in ('oldqa','qa'):
            child=getattr(m,attr,None)
            if child is not None and getattr(child,'__file__',None):stack.append(child)
    need(sha(Path(native.oldqa.__file__))==evidence['prior_separate_QA_helper_sha256'],'same previous header/currency helper')
    return native,hashes


def pdfminer_lines(pdf,pages):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextLine
    output={}
    def walk(obj):
        if isinstance(obj,LTTextLine):
            text=obj.get_text().strip()
            if text:yield (*obj.bbox,text)
        else:
            for child in getattr(obj,'_objs',[]):yield from walk(child)
    for page,layout in zip(sorted(pages),extract_pages(pdf,page_numbers={p-1 for p in pages})):
        output[page]=list(walk(layout))
    need(set(output)==set(pages),'complete selected physical pages from second extractor');return output


def check_one(base,repo,doc,run):
    base,run=Path(base),Path(run);native,helpers=native_checker(repo);key=doc['key'];casefile=run/(key+'.json');case=read(casefile)
    case_before=sha(casefile)
    need(case['capture_key']==key and case['instrument']==doc['instrument'] and case['source_sha256']==doc['source_sha256'],
        'original source/case identity')
    pdf=base/doc['source_path'];need(sha(pdf)==doc['source_sha256'],'original PDF before source QA')
    if case['status']=='SOURCE_PDF_EXTRACTION_UNSUPPORTED':
        need(case['asset_report'] is None,'failed PDF has no admitted source cells')
        return {'capture_key':key,'status':case['status'],'asset_cells_checked':0,'PDF_extraction_failure_retained_not_reclassified':True},helpers
    cachefile=run/(key+'.pages.json');cache_before=sha(cachefile);cache=read(cachefile);pages=cache['pages']
    need(sha(cachefile)==case['source_page_cache_sha256'] and cache['source_sha256']==doc['source_sha256']
        and cache['extractor']=='pypdf6.10.0' and len(pages)==case['page_count']
        and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}==case['all_extracted_page_text_sha256'],
        'complete original page-text cache/hash binding')
    year=case['fiscal_year'];identity=native.qa.source_identity(pages,doc['instrument'],year) if year is not None else None
    if case['status']=='COVER_IDENTITY_UNVERIFIED':
        need(case['asset_report'] is None,'unverified identity is not silently admitted')
        return {'capture_key':key,'status':case['status'],'asset_cells_checked':0,'cover_failure_retained_not_reclassified':True,
            'separate_cover_code_consistent':None if identity is None else identity['code_consistent'],
            'separate_cover_year_consistent':None if identity is None else identity['annual_year_consistent']},helpers
    need(identity['code_consistent'] and identity['annual_year_consistent'],'separate cover identity')
    if case['status']=='ASSET_SOURCE_SCHEMA_UNSUPPORTED':
        need(case['asset_report'] is None,'unsupported financial schema has no source report')
        return {'capture_key':key,'status':case['status'],'asset_cells_checked':0,'schema_failure_retained_not_proven_complete':True},helpers
    need(case['status']=='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA','known supported source state')
    report=case['asset_report'];need(report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'})
        and report['instrument']==doc['instrument'] and report['report_year']==year
        and report['publication_day']==doc['day'] and report['observed_at']==doc['captured_at_utc']
        and report['payload']['document_sha256']==doc['source_sha256'] and report['payload']['announcement_id']==doc['announcement_id'],
        'source report identity,arrival and digest')
    counters=Counter();native.source_cells(report,{**doc,'effective_fiscal_year':year},pages,counters,pdf)
    balances=report['payload']['balances'];selected={c['page'] for c in balances.values()}|{c['header_page'] for c in balances.values()}|{c['unit_evidence_page'] for c in balances.values()}
    second=pdfminer_lines(pdf,selected);receipts={}
    for period,cell in balances.items():
        expected=re.findall(MONEY,cell['row_text']);need(len(expected)==2,'two native source monetary values')
        row=asset_row(second[cell['page']],expected);header=''.join(compact(v[4]) for v in second[cell['header_page']])
        if cell['balance_header_semantics']=='EXPLICIT_TWO_FISCAL_COLUMNS':
            need(f'{year}年12月31日' in header,'second extractor literal current annual header')
            comparative=cell['reported_comparative_balance_date'];d=date.fromisoformat(comparative)
            need(f'{d.year}年{d.month}月{d.day}日' in header,'second extractor explicit comparative date')
        else:need('期末余额' in header and '期初余额' in header,'second extractor unresolved generic balance header')
        receipts[period]={'row_page':cell['page'],'header_page':cell['header_page'],'literal_values':row['literal_values'],
            'row_mid_y':row['row_mid_y'],'source_row_sha256':cell['row_text_sha256'],'pdfminer_row_text_sha256':hashlib.sha256(row['text'].encode()).hexdigest()}
    need(sha(pdf)==doc['source_sha256'] and sha(casefile)==case_before and sha(cachefile)==cache_before,'original PDF/source/cache unchanged after QA')
    return {'capture_key':key,'status':case['status'],'asset_cells_checked':len(balances),
        'native_source_counters':dict(counters),'second_extractor':'pdfminer20251230','pdfminer_physical_pages_checked':len(selected),
        'second_extractor_receipts':receipts},helpers


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','run-dir','request','expected-request-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base,repo,run,request,out=map(Path,(a.source_root,a.repo_root,a.run_dir,a.request,a.output_dir))
    need(not out.exists() and sha(request)==a.expected_request_sha256,'fresh separate source QA/frozen extraction request')
    req=read(request);terminal=read(run/'terminal.json');summary=read(run/'summary.json');before=inventory(run)
    need(terminal['completed_resources']==400 and not terminal['pending'] and terminal['original_error'] is None
        and not terminal['changed_original_inputs'] and not terminal['persistence_errors'],'complete400 immutable extraction')
    bound={request:a.expected_request_sha256}
    for group,parent in (('method_sha256',repo),('public_sha256',repo),('currency_source_sha256',base)):
        for n,h in req[group].items():bound[parent/n]=h
    sourceqa=read(repo/'experiments/qlib/asset-expansion-2026-annual-pdf-byte-audit.json')
    for n,h in sourceqa['all_output_sha256'].items():bound[base/'asset-expansion-2026-annual-pdfs-20261023'/n]=h
    for f,h in bound.items():need(sha(f)==h,'source input before '+str(f))
    out.mkdir(parents=True);results={};helpers={};original=None
    try:
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            for start in range(0,400,WORKERS):
                batch=req['documents'][start:start+WORKERS];futures=[pool.submit(check_one,str(base),str(repo),d,str(run)) for d in batch]
                for doc,future in zip(batch,futures):
                    result,h=future.result();results[doc['key']]=result;helpers.update(h)
                    with (out/(doc['key']+'.json')).open('x') as f:json.dump(result,f,indent=2);f.write('\n')
                    print('separate2026assets',len(results),'/400',doc['key'],result['status'],flush=True)
    except BaseException as exc:original=exc
    finally:
        changed=[str(f) for f,h in bound.items() if not f.is_file() or sha(f)!=h]
        changed.extend(f for f,h in helpers.items() if not Path(f).is_file() or sha(f)!=h)
        outputs_unchanged=inventory(run)==before
        t={'completed':len(results),'pending':[d['key'] for d in req['documents'] if d['key'] not in results],
            'original_error':None if original is None else {'type':type(original).__name__,'message':str(original)},
            'changed_inputs_or_helpers':changed,'original_extraction_outputs_unchanged':outputs_unchanged}
        with (out/'terminal.json').open('x') as f:json.dump(t,f,indent=2);f.write('\n')
    if original is not None:raise original
    need(not changed and outputs_unchanged and len(results)==400,'complete immutable source-cell QA')
    result={'status':'SEPARATE_ALL400_ANNUAL_ASSET_CASES_AND_SUPPORTED_CELLS_CHECKED_NOT_INVESTMENT_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':sha(request),'summary_sha256':sha(run/'summary.json'),
        'document_count':400,'source_case_results':results,'shared_prior_separate_helpers_sha256':helpers,
        'supported_asset_cells_checked':sum(v['asset_cells_checked'] for v in results.values()),
        'second_extractor_physical_pages_checked':sum(v.get('pdfminer_physical_pages_checked',0) for v in results.values()),
        'all_original_extraction_output_sha256':before,'all_original_inputs_unchanged':True,'no_production_imports':True,
        'same_researcher_separate_QA':True,'complete_manual_numeric_visual_review':False,'unsupported_schema_failures_not_reclassified':True,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'2026_portfolio_returns_computed':False,'objective_achieved':False}
    with (out/'summary.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],'cells',result['supported_asset_cells_checked'])

if __name__=='__main__':main()
