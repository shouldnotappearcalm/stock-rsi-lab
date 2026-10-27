"""CFO-caption-only continuation from immutable, fully audited V2 source cases."""
import argparse,json,os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path
from scripts import inspect_cash_accrual_wrapped_corpus as previous
from stock_rsi import annual_cash_accruals_v3 as cash
sha,tree,changed,persist,read,read_bound,need,digest=previous.sha,previous.tree,previous.changed,previous.persist,previous.read,previous.read_bound,previous.need,previous.digest
legacy=previous.legacy
SUPPORTED,UNSUPPORTED=previous.SUPPORTED,previous.UNSUPPORTED
PREVIOUS_REQUEST='experiments/qlib/cash-accrual-wrapped-request.json'
PREVIOUS_SHA='2f79d0dd60feb4e590183d5796fef0c80f0221e42c2dfa775b20c493adc60a40'
PROOF='experiments/qlib/cash-accrual-wrapped-root-check.json'
PROOF_SHA='b8072105bb136974da4110424e62532d94121b224bc24d04d9f8d9f730953147'
OUTPUT='cash-accrual-cfo-corpus-v3-20261027'
DESIGN='docs/research/cash-accrual-cfo-source-design-2026-10-27.md'
METHODS=tuple(dict.fromkeys((*previous.METHODS,'src/stock_rsi/annual_cash_accruals_v3.py','scripts/inspect_cash_accrual_cfo_corpus.py','scripts/audit_cash_accrual_cfo_corpus.py','tests/test_annual_cash_accruals_v3.py','tests/test_cash_accrual_cfo_corpus.py')))
PROFILE={'status':'FROZEN_CFO_CAPTION_ONLY_SOURCE_CONTINUATION','output_subdir':OUTPUT,'document_count':1236,'cohort_count':394,'workers':4,'maximum_outstanding_documents':4,'maximum_row_lines':12,'expected_V2_supported_reports':257,'maximum_publication_day':'2025-12-31','network_or_new_PDF_extraction_permitted':False,'ratios_rankings_or_returns_permitted':False,'2026_values_permitted':False}

def case_paths(base,document):
    return (*previous.case_paths(base,document),base/previous.OUTPUT/'cases'/(document['capture_key']+'.json'))

def inspect_one(base,document,normative_basis,known):
    cash.metadata(document);base=Path(base);paths=case_paths(base,document)
    need(sha(paths[0])==known[str(paths[0].resolve())]==document['source_sha256'],'original PDF bytes')
    values=[read_bound(p,known[str(p.resolve())]) for p in paths[1:]]
    original=values[-1];previous.validate_case(original,document,base,known,normative_basis)
    result={**original,'v2_case_sha256':known[str(paths[-1].resolve())],'v2_original_status':original['status'],
            'v2_original_error':original.get('error'),'v2_source_parser_variant':original['source_parser_variant']}
    if original['status']==SUPPORTED:return {**result,'source_parser_variant':'V2_PRESERVED'}
    if original['status']=='COVER_IDENTITY_UNVERIFIED':return {**result,'source_parser_variant':'V2_COVER_FAILURE_RETAINED'}
    need(original['status']==UNSUPPORTED and original['report'] is None,'only audited unsupported source may extend')
    pages=values[1]['pages']
    try:parsed=cash.parse_report(pages,document['effective_fiscal_year'],normative_basis=normative_basis);report=cash.make_report(document,parsed)
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':UNSUPPORTED,'source_parser_variant':'V3_STILL_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc)}
    need(report['contract']==cash.CONTRACT,'new recovery requires new CFO source contract')
    for n in ('error','error_type'):result.pop(n,None)
    return {**result,'status':SUPPORTED,'report':report,'source_parser_variant':'V3_RECOVERED_CFO_LABEL'}

def validate_case(case,document,base,known,normative_basis=None):
    cash.metadata(document);paths=case_paths(base,document);old=read_bound(paths[-1],known[str(paths[-1].resolve())])
    need(case['v2_case_sha256']==known[str(paths[-1].resolve())] and case['v2_original_status']==old['status']
         and case['v2_original_error']==old.get('error') and case['v2_source_parser_variant']==old['source_parser_variant'],'exact audited V2 case lineage')
    for key in ('capture_key','instrument','fiscal_year','publication_day','source_sha256','parent_case_sha256',
                'source_page_cache_sha256','protected_asset_cells_compared','investment_factor_admitted','historical_arrival_verified',
                'v1_source_case_sha256','v1_source_status','v1_original_error'):
        need(case[key]==old[key],'unchanged protected source metadata: '+key)
    need(case['investment_factor_admitted'] is False and case['historical_arrival_verified'] is False,'no source assurance escalation')
    if old['status']==SUPPORTED:
        need(case['status']==SUPPORTED and case['report']==old['report'] and case['source_parser_variant']=='V2_PRESERVED','all257prior reports preserved identically')
        previous.validate_case({**case,'source_parser_variant':old['source_parser_variant']},document,base,known,normative_basis);return
    if old['status']=='COVER_IDENTITY_UNVERIFIED':
        need(case['status']==old['status'] and case['report'] is None and case['source_parser_variant']=='V2_COVER_FAILURE_RETAINED','cover failure retained');return
    need(old['status']==UNSUPPORTED,'known prior status')
    if case['status']==UNSUPPORTED:
        need(case['report'] is None and case['source_parser_variant']=='V3_STILL_UNSUPPORTED','failed source has no values');return
    need(case['status']==SUPPORTED and case['source_parser_variant']=='V3_RECOVERED_CFO_LABEL'
         and case['report']['contract']==cash.CONTRACT and cash.make_report(document,case['report']['parsed'])==case['report'],'registered coherent CFO report')
    pages=read_bound(paths[2],known[str(paths[2].resolve())])['pages']
    cash.verify_source_tables(case['report']['parsed'],pages,document['effective_fiscal_year'],normative_basis=normative_basis)

def bindings(base,root,membership):
    need(sha(root/PROOF)==PROOF_SHA,'pinned whole V2 source audit');proof=read_bound(root/PROOF,PROOF_SHA)
    need(proof['status']=='PASS_ALL_WRAPPED_SOURCE_CASE_REPLAY_AND_SEPARATE_LITERAL_CHECKS_NOT_FACTOR_ADMISSION'
         and proof['request_sha256']==PREVIOUS_SHA and proof['all_inputs_outputs_unchanged'] is True
         and proof['all_original_227_reports_preserved_identically'] is True,'completed prior source audit')
    known={}
    def bind(path,h):
        path=Path(path);key=str(path.resolve());need(not path.is_symlink() and (key not in known or known[key]==h),'unique source identity')
        if key not in known:need(sha(path)==h,'authenticated input '+str(path));known[key]=h
    for path,h in proof['all_input_sha256'].items():bind(path,h)
    need(tree(base/previous.OUTPUT)==proof['all_output_sha256'],'whole audited V2 output tree')
    for n,h in proof['all_output_sha256'].items():bind(base/previous.OUTPUT/n,h)
    bind(root/PROOF,PROOF_SHA);bind(root/PREVIOUS_REQUEST,PREVIOUS_SHA)
    for n in (*METHODS,DESIGN,'tests/fixtures/annual-cash-accrual-cfo-real-row.json'):bind(root/n,sha(root/n))
    return known

def verify(base,root,membership,request,expected):
    req=read_bound(request,expected);need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed source-only CFO continuation')
    known=bindings(base,root,membership);need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS)
        and all(sha(root/n)==h for n,h in req['method_sha256'].items()),'whole CFO source/method closure')
    old=read_bound(root/PREVIOUS_REQUEST,PREVIOUS_SHA)
    need(all(req[k]==old[k] for k in ('documents','cohort','normative_basis')),'same1236original editions/394issuers/no2026sources')
    known[str(request.resolve())]=expected;req['request_sha256']=expected;return req,known

def execute(req,known,out,base,*,worker=inspect_one,executor_factory=ProcessPoolExecutor):
    out=Path(out);base=Path(base);need(not out.exists() and not out.is_symlink() and not changed(known),'fresh output and all source inputs unchanged');out.mkdir();outputs={};results={};submitted=[];failed=[];primary=None;stage='SETUP';row_index=None
    def stamp(p):
        info=Path(p).stat();return (info.st_ino,info.st_size,info.st_mtime_ns)
    stamps={}
    terminal={'status':'CASH_ACCRUAL_CFO_SOURCE_INCOMPLETE','complete':False,'request_sha256':req['request_sha256'],'investment_factor_admitted':False,'ratios_rankings_or_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False,'failed_stage':None,'failed_row_index':None}
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
        preserved=sum(c['source_parser_variant']=='V2_PRESERVED' for c in results.values());need(preserved==req['expected_V2_supported_reports'],'all original V2 successes must be preserved');supported=[c for c in results.values() if c['status']==SUPPORTED];terminal.update(status='CASH_ACCRUAL_WRAPPED_CELLS_COMPLETE_NOT_FACTOR_ADMITTED',complete=True,summary={'V2_supported_reports_preserved_identically':preserved,'V3_CFO_reports_recovered':sum(c['source_parser_variant']=='V3_RECOVERED_CFO_LABEL' for c in results.values()),'source_parser_variant_counts':dict(Counter(c['source_parser_variant'] for c in results.values())),'document_count':len(results),'cohort_count':len(req['cohort']),'status_counts':dict(Counter(c['status'] for c in results.values())),'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if c['error'])),'supported_source_issuer_count':len({c['instrument'] for c in supported}),'raw_monetary_cells':len(supported)*6,'protected_asset_cells_compared':sum(c['protected_asset_cells_compared'] for c in results.values()),'original_PDF_text_decodings_performed':0,'manual_visual_QA_complete':False,'financial_version_history_complete':False,'financial_cross_issuer_comparability_verified':False})
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
    if a.preflight_only:print('CFO source preflight PASS');return
    print(execute(req,known,base/OUTPUT,base)['status'])

if __name__=='__main__':main()
