"""Frozen caption-only continuation; exact V1 cases/reports remain evidence."""
import argparse,json,os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path
from scripts import inspect_cash_accrual_corpus as v1
from stock_rsi import annual_cash_accruals_v2 as cash

sha,tree,changed,persist,read,read_bound,need,digest=v1.sha,v1.tree,v1.changed,v1.persist,v1.read,v1.read_bound,v1.need,v1.digest
legacy=v1.legacy
SUPPORTED,UNSUPPORTED=v1.SUPPORTED,v1.UNSUPPORTED
PREVIOUS_REQUEST='experiments/qlib/cash-accrual-source-request.json';PREVIOUS_SHA='19c36e97ffc5da71ed8c3e6933b257a561c6a815a44f5045d1892f5bd3286ec7'
PROOF='experiments/qlib/cash-accrual-source-root-check.json';PROOF_SHA='b672e0f4a1e7a69c6e7b30b9d9f9482ea5603d7ab629c3c434377b188e0b43f6'
OUTPUT='cash-accrual-wrapped-corpus-v2-20261023';DIAG='cash-accrual-net-profit-layout-diagnosis-v1-20261023'
DESIGN='docs/research/cash-accrual-wrapped-label-design-2026-10-23.md';PLAN='docs/superpowers/plans/2026-10-23-cash-accrual-wrapped-label.md';REVIEW='experiments/qlib/cash-accrual-wrapped-review.json'
FIXTURE='tests/fixtures/annual-cash-accrual-wrapped-real-rows.json'
METHODS=tuple(dict.fromkeys((*v1.METHODS,'src/stock_rsi/annual_cash_accruals_v2.py','scripts/inspect_cash_accrual_wrapped_corpus.py','tests/test_annual_cash_accruals_v2.py','tests/test_cash_accrual_wrapped_corpus.py')))
PROFILE={'status':'FROZEN_CASH_ACCRUAL_WRAPPED_CAPTION_CONTINUATION','output_subdir':OUTPUT,'document_count':1236,'cohort_count':394,'workers':4,'maximum_outstanding_documents':4,'maximum_row_lines':12,'expected_V1_supported_reports':227,'source_contracts':[v1.cash.CONTRACT,cash.CONTRACT],'maximum_publication_day':'2025-12-31','network_or_new_PDF_extraction_permitted':False,'ratios_rankings_or_returns_permitted':False,'2026_values_permitted':False}

def case_paths(base,document):return (*v1.case_paths(base,document),base/v1.OUTPUT/'cases'/(document['capture_key']+'.json'))
def inspect_one(base,document,normative_basis,known):
    cash.metadata(document);base=Path(base);*_,prior=case_paths(base,document);frozen=read_bound(prior,known[str(prior.resolve())]);original=v1.inspect_one(base,document,normative_basis,known)
    need(original==frozen,'exact frozen V1 source case reproduction required')
    result={**original,'v1_source_case_sha256':known[str(prior.resolve())],'v1_source_status':original['status'],'v1_original_error':original.get('error')}
    if original['status']==SUPPORTED:return {**result,'source_parser_variant':'V1_PRESERVED'}
    if original['status']=='COVER_IDENTITY_UNVERIFIED':return {**result,'source_parser_variant':'V1_COVER_FAILURE_RETAINED'}
    need(original['status']==UNSUPPORTED and original['report'] is None,'only prior unsupported source may extend')
    *_,cache,_=case_paths(base,document);pages=read_bound(cache,known[str(cache.resolve())])['pages']
    try:parsed=cash.parse_report(pages,document['effective_fiscal_year'],normative_basis=normative_basis);report=cash.make_report(document,parsed)
    except (ValueError,KeyError,ArithmeticError) as exc:return {**result,'status':UNSUPPORTED,'source_parser_variant':'V2_STILL_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc)}
    need(report['contract']==cash.CONTRACT,'unsupported V1 cannot silently become a V1 report')
    for name in ('error','error_type'):result.pop(name,None)
    return {**result,'status':SUPPORTED,'report':report,'source_parser_variant':'V2_RECOVERED_LABEL'}

def validate_case(case,document,base,known,normative_basis=None):
    cash.metadata(document);raw,old,cache,previous=case_paths(base,document);frozen=read_bound(previous,known[str(previous.resolve())])
    need(case['v1_source_case_sha256']==known[str(previous.resolve())] and case['v1_source_status']==frozen['status'] and case['v1_original_error']==frozen.get('error'),'frozen V1 source lineage required')
    need(case['parent_case_sha256']==known[str(old.resolve())] and case['source_page_cache_sha256']==known[str(cache.resolve())] and case['protected_asset_cells_compared']==frozen['protected_asset_cells_compared'],'same original source buffers and protected assets')
    need(all(case[k]==document[d] for k,d in [('capture_key','capture_key'),('instrument','instrument'),('fiscal_year','effective_fiscal_year'),('publication_day','day'),('source_sha256','source_sha256')]),'worker original source identity')
    if frozen['status']==SUPPORTED:
        need(case['status']==SUPPORTED and case['source_parser_variant']=='V1_PRESERVED' and case['report']==frozen['report'],'all original V1 supported reports preserved identically');v1.validate_case(case,document,base,known,normative_basis);return
    if frozen['status']=='COVER_IDENTITY_UNVERIFIED':need(case['status']==frozen['status'] and case['source_parser_variant']=='V1_COVER_FAILURE_RETAINED' and case['report'] is None,'unverified cover cannot supply a monetary report');return
    need(frozen['status']==UNSUPPORTED and case['status'] in (SUPPORTED,UNSUPPORTED),'only registered old unsupported source may recover')
    if case['status']==UNSUPPORTED:need(case['source_parser_variant']=='V2_STILL_UNSUPPORTED' and case['report'] is None,'unsupported source cannot supply monetary values');return
    need(case['source_parser_variant']=='V2_RECOVERED_LABEL' and case['report']['contract']==cash.CONTRACT and cash.make_report(document,case['report']['parsed'])==case['report'],'registered new wrapped source report required')
    source=read_bound(cache,known[str(cache.resolve())]);cash.verify_source_tables(case['report']['parsed'],source['pages'],document['effective_fiscal_year'],normative_basis=normative_basis)

def bindings(base,root,membership):
    need(sha(root/PROOF)==PROOF_SHA and sha(root/PREVIOUS_REQUEST)==PREVIOUS_SHA,'frozen complete V1 source proof/request');p=read_bound(root/PROOF,PROOF_SHA);known={}
    def bind(path,h):
        path=Path(path);need(not path.is_symlink() and sha(path)==h,'unchanged source input '+str(path));key=str(path.resolve());need(key not in known or known[key]==h,'resolved source identity');known[key]=h
    for path,h in p['all_input_sha256'].items():bind(path,h)
    bind(root/PROOF,PROOF_SHA)
    for folder,key in ((v1.OUTPUT,'all_capture_sha256'),('cash-accrual-original-source-root-audit-v1-20261023','root_audit_artifact_sha256'),('cash-accrual-source-visual-witness-v1-20261023','selected_PDF_render_artifact_sha256')):
        need(tree(base/folder)==p[key],'complete retained V1 evidence tree')
        for n,h in p[key].items():bind(base/folder/n,h)
    for n,h in p['public_copy_sha256'].items():bind(root/n,h)
    for n,h in tree(base/DIAG).items():bind(base/DIAG/n,h)
    need(sha(root/'experiments/qlib/cash-accrual-wrapped-layout-diagnosis.json')==sha(base/DIAG/'summary.json'),'exact original diagnostic copy')
    for n in (*METHODS,DESIGN,PLAN,REVIEW,FIXTURE,'experiments/qlib/cash-accrual-wrapped-layout-diagnosis.json'):bind(root/n,sha(root/n))
    return known

def verify(base,root,membership,request,expected):
    req=read_bound(request,expected);need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed caption-only source profile');known=bindings(base,root,membership)
    need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS) and all(sha(root/n)==h for n,h in req['method_sha256'].items()),'complete caption method/source closure')
    old,_=v1.verify(base,root,membership,root/PREVIOUS_REQUEST,PREVIOUS_SHA)
    need(all(req[k]==old[k] for k in ('documents','cohort','normative_basis')),'same full original document/cohort/currency scope')
    terminal=read_bound(base/v1.OUTPUT/'terminal.json',known[str((base/v1.OUTPUT/'terminal.json').resolve())]);need(terminal['complete'] is True and terminal['summary']['status_counts'][SUPPORTED]==227,'all227old successful reports protected')
    known[str(request.resolve())]=expected;req['request_sha256']=expected;return req,known

def execute(req,known,out,base,*,worker=inspect_one,executor_factory=ProcessPoolExecutor):
    out=Path(out);base=Path(base);need(not out.exists() and not out.is_symlink() and not changed(known),'fresh output and all source inputs unchanged');out.mkdir();outputs={};results={};submitted=[];failed=[];primary=None;stage='SETUP';row_index=None
    def stamp(p):
        info=Path(p).stat();return (info.st_ino,info.st_size,info.st_mtime_ns)
    stamps={}
    terminal={'status':'CASH_ACCRUAL_WRAPPED_SOURCE_INCOMPLETE','complete':False,'request_sha256':req['request_sha256'],'investment_factor_admitted':False,'ratios_rankings_or_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False,'failed_stage':None,'failed_row_index':None}
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
                        case=future.result();validate_case(case,doc,base,known,req['normative_basis']);save('cases/'+doc['capture_key']+'.json',case);results[doc['capture_key']]={'status':case['status'],'sha256':outputs['cases/'+doc['capture_key']+'.json'],'instrument':case['instrument'],'fiscal_year':case['fiscal_year'],'protected_asset_cells_compared':case['protected_asset_cells_compared'],'error':case.get('error'),'source_parser_variant':case['source_parser_variant'],'v1_source_status':case['v1_source_status']}
                    except BaseException as exc:
                        failed.append({'capture_key':doc['capture_key'],'type':type(exc).__name__,'error':str(exc)})
                        if batch_error is None:batch_error=exc;first_error_index=i
                if batch_error is not None:row_index=first_error_index;raise batch_error
                boundary()
                if len(results)%100==0 or len(results)==len(req['documents']):print('cash-accrual source',len(results),'/',len(req['documents']),flush=True)
        stage='FINAL_SOURCE_CHECK';need(not changed(known),'all source bytes unchanged after processing');need(set(results)=={d['capture_key'] for d in req['documents']},'all original cases required')
        preserved=sum(c['source_parser_variant']=='V1_PRESERVED' for c in results.values());need(preserved==req['expected_V1_supported_reports'],'all original V1 successes must be preserved');supported=[c for c in results.values() if c['status']==SUPPORTED];terminal.update(status='CASH_ACCRUAL_WRAPPED_CELLS_COMPLETE_NOT_FACTOR_ADMITTED',complete=True,summary={'V1_supported_reports_preserved_identically':preserved,'V2_wrapped_reports_recovered':sum(c['source_parser_variant']=='V2_RECOVERED_LABEL' for c in results.values()),'source_parser_variant_counts':dict(Counter(c['source_parser_variant'] for c in results.values())),'document_count':len(results),'cohort_count':len(req['cohort']),'status_counts':dict(Counter(c['status'] for c in results.values())),'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if c['error'])),'supported_source_issuer_count':len({c['instrument'] for c in supported}),'raw_monetary_cells':len(supported)*6,'protected_asset_cells_compared':sum(c['protected_asset_cells_compared'] for c in results.values()),'original_PDF_text_decodings_performed':0,'manual_visual_QA_complete':False,'financial_version_history_complete':False,'financial_cross_issuer_comparability_verified':False})
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
