"""Frozen whole-cohort original NI/CFO source inspection; no scores or account."""
import argparse,hashlib,json,os,sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path
from scripts import inspect_operating_corpus_source as parent
from scripts import decode_low_operating_tencent_pre2026 as legacy
from scripts.recover_low_operating_quotes_pre2026 import sha,tree,changed,persist
from stock_rsi import annual_cash_accruals as cash
from stock_rsi.data import digest

need=parent.need
OLD_REQUEST='experiments/qlib/operating-corpus-source-request.json';OLD_SHA='f0302c00af7e312055aaf5a41f74a547de2bf2aaf9465a65d38aa9bf92da3710'
OLD_PROOF='experiments/qlib/operating-corpus-source-independent-check.json';PROOF_SHA='292aceb7322fe8dd6b15b67a3be4d45ea285ddbbe60876bdde1358d603893581'
OUTPUT='cash-accrual-original-corpus-v1-20261023';SUPPORTED='CASH_ACCRUAL_CELLS_SUPPORTED_PENDING_SOURCE_QA';UNSUPPORTED='CASH_ACCRUAL_SOURCE_SCHEMA_UNSUPPORTED'
DESIGN='docs/research/cash-accrual-source-design-2026-10-23.md';PLAN='docs/superpowers/plans/2026-10-23-cash-accrual-source.md';REVIEW='experiments/qlib/cash-accrual-source-review.json'
METHODS=tuple(dict.fromkeys((*parent.METHODS,'src/stock_rsi/annual_cash_accruals.py','src/stock_rsi/tencent_history.py','scripts/decode_low_operating_tencent_pre2026.py','scripts/recover_low_operating_quotes_pre2026.py','scripts/inspect_cash_accrual_corpus.py','tests/test_annual_cash_accruals.py','tests/test_cash_accrual_corpus.py')))
PROFILE={'status':'FROZEN_CASH_ACCRUAL_ORIGINAL_SOURCE_INSPECTION','output_subdir':OUTPUT,'document_count':1236,'cohort_count':394,'workers':4,'maximum_outstanding_documents':4,'parser_contract':cash.CONTRACT,'maximum_publication_day':'2025-12-31','network_or_new_PDF_extraction_permitted':False,'ratios_rankings_or_returns_permitted':False,'2026_values_permitted':False}

def read(path):return json.loads(Path(path).read_text())
def read_bound(path,expected):
    need(not Path(path).is_symlink(),'regular source JSON');body=Path(path).read_bytes();need(len(body)<=16*1024*1024 and hashlib.sha256(body).hexdigest()==expected,'authenticated actual source JSONbuffer')
    def bad(value):raise ValueError('nonfinite JSONconstant')
    return json.loads(body,parse_constant=bad)

def case_paths(base,document):
    raw=Path(document['source_path']);need(not raw.is_absolute() and '..' not in raw.parts,'safe original source path');phase=document['source_phase'];need(phase in ('INITIAL_AUTHENTICATED_PAGE_CACHE','LATER_ORIGINAL_PDF'),'known original cache phase');key=document['capture_key'];need(Path(key).name==key and key not in ('.','..'),'safe source capture key')
    return (base/raw,base/parent.PARENT_OUTPUT/(key+'.json'),base/(parent.INITIAL_CACHE if phase=='INITIAL_AUTHENTICATED_PAGE_CACHE' else parent.LATER_CACHE)/(key+'.pages.json'))

def inspect_one(base,document,normative_basis,known):
    base=Path(base);raw,case_path,cache_path=case_paths(base,document);expected=lambda p:known[str(p.resolve())]
    need(not raw.is_symlink() and sha(raw)==expected(raw)==document['source_sha256'],'authenticated original PDF bytes')
    old=read_bound(case_path,expected(case_path));cache=read_bound(cache_path,expected(cache_path));pages=cache['pages'];year=document['effective_fiscal_year']
    need(old['capture_key']==document['capture_key'] and old['instrument']==document['instrument'] and old['fiscal_year']==year and old['source_sha256']==document['source_sha256'],'original source case identity')
    need(cache['source_sha256']==document['source_sha256'] and cache['extractor']=='pypdf6.10.0' and type(pages) is list and pages and all(type(p) is str for p in pages) and len(pages)==old['page_count'] and {str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(pages)}==old['all_extracted_page_text_sha256'],'authenticated cached physical page text')
    result={'capture_key':document['capture_key'],'instrument':document['instrument'],'fiscal_year':year,'publication_day':document['day'],'source_sha256':document['source_sha256'],'parent_case_sha256':expected(case_path),'source_page_cache_sha256':expected(cache_path),'report':None,'protected_asset_cells_compared':0,'historical_arrival_verified':False,'investment_factor_admitted':False}
    if not(old['cover_code_consistent'] and old['cover_annual_year_consistent']):return {**result,'status':'COVER_IDENTITY_UNVERIFIED'}
    try:parsed=cash.parse_report(pages,year,normative_basis=normative_basis);report=cash.make_report(document,parsed)
    except (ValueError,KeyError,ArithmeticError) as exc:return {**result,'status':UNSUPPORTED,'error_type':type(exc).__name__,'error':str(exc)}
    controls=0
    for observation in old['source_observations']:
        need(observation['record_id']==digest({k:v for k,v in observation.items() if k!='record_id'}),'protected old GP observation identity');period=observation['fiscal_end'];before=observation['payload']['cells']['total_assets'];after=parsed['balances'][period]
        need(all(before[k]==after[k] for k in ('value_CNY','literal','fiscal_end','column_index')),'protected old asset source cell disagreement');controls+=1
    return {**result,'status':SUPPORTED,'report':report,'protected_asset_cells_compared':controls}

def bindings(base,root,membership):
    need(sha(root/OLD_REQUEST)==OLD_SHA and sha(root/OLD_PROOF)==PROOF_SHA,'frozen original source request/proof');old=read_bound(root/OLD_REQUEST,OLD_SHA);paths=parent.required_paths(base,root,membership);known={}
    def bind(path,h):
        path=Path(path);need(not path.is_symlink() and sha(path)==h,'unchanged source input '+str(path));key=str(path.resolve());need(key not in known or known[key]==h,'same resolved source identity');known[key]=h
    need(set(paths)==set(old['input_sha256']),'original source closure')
    for key,p in paths.items():bind(p,old['input_sha256'][key])
    bind(root/OLD_REQUEST,OLD_SHA);bind(root/OLD_PROOF,PROOF_SHA);proof=read_bound(root/OLD_PROOF,PROOF_SHA)
    for n,h in proof['all_output_sha256'].items():need(not Path(n).is_absolute() and '..' not in Path(n).parts,'safe original source output');bind(base/parent.OUTPUT/n,h)
    for n in (*METHODS,DESIGN,PLAN,REVIEW):bind(root/n,sha(root/n))
    return known

def verify(base,root,membership,request,expected):
    req=read_bound(request,expected);need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed whole-cohort source-only profile');known=bindings(base,root,membership)
    need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS) and all(sha(root/n)==h for n,h in req['method_sha256'].items()),'exact new source/method closure')
    old,_=parent.verify(base,root,membership,root/OLD_REQUEST,OLD_SHA)
    need(req['documents']==old['documents'] and req['cohort']==old['cohort'] and req['normative_basis']==old['normative_basis'] and len(req['documents'])==1236 and len({v['capture_key'] for v in req['documents']})==1236 and all(v['day']<='2025-12-31' for v in req['documents']),'complete original editions/cohort/units; no future source')
    known[str(request.resolve())]=expected;req['request_sha256']=expected;return req,known

def validate_case(case,document,base,known):
    _,prior,cache=case_paths(base,document);need(case['parent_case_sha256']==known[str(prior.resolve())] and case['source_page_cache_sha256']==known[str(cache.resolve())],'worker authenticated source provenance')
    need(all(case[k]==document[d] for k,d in [('capture_key','capture_key'),('instrument','instrument'),('fiscal_year','effective_fiscal_year'),('publication_day','day'),('source_sha256','source_sha256')]),'worker original case identity')
    need(case['status'] in (SUPPORTED,UNSUPPORTED,'COVER_IDENTITY_UNVERIFIED'),'known source classification')
    if case['status']==SUPPORTED:need(cash.make_report(document,case['report']['parsed'])==case['report'],'worker supported report identity/source evidence')
    else:need(case['report'] is None,'failed source cannot supply monetary report')

def execute(req,known,out,base,*,worker=inspect_one,executor_factory=ProcessPoolExecutor):
    out=Path(out);base=Path(base);need(not out.exists() and not out.is_symlink() and not changed(known),'fresh output and all source inputs unchanged');out.mkdir();outputs={};results={};submitted=[];failed=[];primary=None;stage='SETUP';row_index=None
    def stamp(p):
        info=Path(p).stat();return (info.st_ino,info.st_size,info.st_mtime_ns)
    stamps={}
    terminal={'status':'CASH_ACCRUAL_SOURCE_INCOMPLETE','complete':False,'request_sha256':req['request_sha256'],'investment_factor_admitted':False,'ratios_rankings_or_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False,'failed_stage':None,'failed_row_index':None}
    def save(n,v):persist(out,n,v,outputs)
    def boundary():need(all(stamp(p)==v for p,v in stamps.items()) and tree(out)==outputs,'source metadata or intended outputs changed between batches')
    try:
        stamps={p:stamp(p) for p in known}
        with executor_factory(max_workers=4) as pool:
            for start in range(0,len(req['documents']),4):
                boundary();stage='BATCH';peers=[];batch_error=None;first_error_index=None
                for i,doc in enumerate(req['documents'][start:start+4]):
                    row_index=start+i
                    try:
                        subset={str(p.resolve()):known[str(p.resolve())] for p in case_paths(base,doc)};future=pool.submit(worker,base,deepcopy(doc),req['normative_basis'],subset)
                    except BaseException as exc:batch_error=exc;first_error_index=row_index;break
                    submitted.append(doc['capture_key']);peers.append((start+i,doc,future))
                for i,doc,future in peers:
                    row_index=i
                    try:
                        case=future.result();validate_case(case,doc,base,known);save('cases/'+doc['capture_key']+'.json',case);results[doc['capture_key']]={'status':case['status'],'sha256':outputs['cases/'+doc['capture_key']+'.json'],'instrument':case['instrument'],'fiscal_year':case['fiscal_year'],'protected_asset_cells_compared':case['protected_asset_cells_compared'],'error':case.get('error')}
                    except BaseException as exc:
                        failed.append({'capture_key':doc['capture_key'],'type':type(exc).__name__,'error':str(exc)})
                        if batch_error is None:batch_error=exc;first_error_index=i
                if batch_error is not None:row_index=first_error_index;raise batch_error
                boundary()
                if len(results)%100==0 or len(results)==len(req['documents']):print('cash-accrual source',len(results),'/',len(req['documents']),flush=True)
        stage='FINAL_SOURCE_CHECK';need(not changed(known),'all source bytes unchanged after processing');need(set(results)=={d['capture_key'] for d in req['documents']},'all original cases required')
        supported=[c for c in results.values() if c['status']==SUPPORTED];terminal.update(status='CASH_ACCRUAL_ORIGINAL_CELLS_COMPLETE_NOT_FACTOR_ADMITTED',complete=True,summary={'document_count':len(results),'cohort_count':len(req['cohort']),'status_counts':dict(Counter(c['status'] for c in results.values())),'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if c['error'])),'supported_source_issuer_count':len({c['instrument'] for c in supported}),'raw_monetary_cells':len(supported)*6,'protected_asset_cells_compared':sum(c['protected_asset_cells_compared'] for c in supported),'original_PDF_text_decodings_performed':0,'manual_visual_QA_complete':False,'financial_version_history_complete':False,'financial_cross_issuer_comparability_verified':False})
    except BaseException as exc:primary=exc;terminal.update(error_type=type(exc).__name__,error=str(exc),failed_stage=stage,failed_row_index=row_index,complete=False)
    terminal.update(completed_documents=len(results),submitted_keys=submitted,failed_documents=failed,unsubmitted_keys=[d['capture_key'] for d in req['documents'] if d['capture_key'] not in submitted],pending=[d['capture_key'] for d in req['documents'] if d['capture_key'] not in results])
    try:save('case_index.json',results)
    except BaseException as exc:
        terminal.update(complete=False)
        if primary is None:primary=exc;terminal.update(error_type=type(exc).__name__,error=str(exc),failed_stage='CASE_INDEX',failed_row_index=None)
        else:primary.add_note('case index persistence: '+type(exc).__name__)
    try:value=legacy.finish_source(out,terminal,known,outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal persistence: '+type(exc).__name__)
    if primary is not None:raise primary
    return value

def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];req,known=verify(base,root,Path(a.membership_file).resolve(),Path(a.request).resolve(),a.expected_request_sha256)
    if a.preflight_only:print('source preflight PASS; no new financial field decode');return
    print(execute(req,known,base/OUTPUT,base)['status'])
if __name__=='__main__':main()
