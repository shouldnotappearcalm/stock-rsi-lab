"""Immutable V3 cash grammar on400 archived2026 annual editions; no ranking/ROI."""
import argparse,hashlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from datetime import date,datetime,time,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts import inspect_cash_accrual_cfo_corpus as previous
from stock_rsi import annual_cash_accruals_v3 as cash

sha,tree,changed,persist,read,read_bound,need,digest=previous.sha,previous.tree,previous.changed,previous.persist,previous.read,previous.read_bound,previous.need,previous.digest
legacy=previous.legacy
SUPPORTED,UNSUPPORTED=previous.SUPPORTED,previous.UNSUPPORTED
OLD='asset-expansion-2026-assets-20261023';OUTPUT='cash-accrual-2026-source-v1-20261028'
ASSET_REQUEST='experiments/qlib/asset-expansion-2026-assets-request.json';ASSET_QA='experiments/qlib/asset-expansion-2026-assets-source-audit.json';BYTE_QA='experiments/qlib/asset-expansion-2026-annual-pdf-byte-audit.json'
LEDGER_QA='experiments/qlib/cash-accrual-integer-root-check.json'
DESIGN='docs/research/cash-accrual-2026-source-design-2026-10-28.md'
METHODS=tuple(dict.fromkeys((*previous.METHODS,'scripts/inspect_cash_accrual_2026_sources.py','scripts/audit_cash_accrual_2026_sources.py','tests/test_cash_accrual_2026_sources.py')))
PROFILE={'status':'FROZEN400_EXPOSED2026_CASH_FIELDS_UNCHANGED_V3_NO_RETURN','output_subdir':OUTPUT,'document_count':400,'cohort_count':394,'workers':4,
 'maximum_outstanding_documents':4,'cutoff_day':'2026-10-21','parser_contract':cash.CONTRACT,'new_alpha_candidates':0,'investment_rule_changed':False,
 'network_or_new_PDF_extraction_permitted':False,'ratios_rankings_or_returns_permitted':False,'2026_financial_fields_permitted':True,'sealed_evidence':False}

def case_paths(base,doc):return (base/doc['source_path'],base/OLD/(doc['capture_key']+'.json'),base/OLD/(doc['capture_key']+'.pages.json'))
def metadata(doc):
    public=date.fromisoformat(doc['day']);observed=cash.aware(doc['captured_at_utc']);need('2026-01-01'<=public.isoformat()<=PROFILE['cutoff_day'],'bounded2026publication')
    end=datetime.combine(public,time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc);need(observed>=end,'source observation after publication')
    if doc['effective_fiscal_year'] is not None:cash.metadata(doc)
    else:
        import re
        need(re.fullmatch('(SH|SZ)[0-9]{6}',doc['instrument']) and re.fullmatch('[a-f0-9]{64}',doc['source_sha256']) and re.fullmatch('[0-9]+',doc['announcement_id']),'unresolved source metadata identity')

def inspect_one(base,doc,normative_basis,known):
    base=Path(base);metadata(doc);raw,old_path,cache_path=case_paths(base,doc)
    need(sha(raw)==known[str(raw.resolve())]==doc['source_sha256'],'original2026PDFbytes')
    old=read_bound(old_path,known[str(old_path.resolve())]);cache=read_bound(cache_path,known[str(cache_path.resolve())]);pages=cache['pages'];year=doc['effective_fiscal_year']
    need(old['capture_key']==doc['capture_key'] and old['instrument']==doc['instrument'] and old['fiscal_year']==year
         and old['publication_day']==doc['day'] and old['observed_at']==doc['captured_at_utc'] and old['source_sha256']==doc['source_sha256'],'original archived case metadata')
    need(old['source_page_cache_sha256']==known[str(cache_path.resolve())],'original cached-page provenance')
    need(cache['source_sha256']==doc['source_sha256'] and cache['extractor']=='pypdf6.10.0' and len(pages)==old['page_count']
         and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}==old['all_extracted_page_text_sha256'],'authenticated original page text buffers')
    result={'capture_key':doc['capture_key'],'instrument':doc['instrument'],'fiscal_year':year,'publication_day':doc['day'],'source_sha256':doc['source_sha256'],
        'source_parser_variant':'UNCHANGED_V3_EXPOSED2026_SOURCE','old_asset_case_sha256':known[str(old_path.resolve())],
        'source_page_cache_sha256':known[str(cache_path.resolve())],'protected_asset_cells_compared':0,'report':None,
        'historical_arrival_verified':False,'investment_factor_admitted':False}
    if not(old['cover_code_consistent'] and old['cover_annual_year_consistent']):
        need(old['asset_report'] is None,'cover failure cannot have a protected asset report');return {**result,'status':'COVER_IDENTITY_UNVERIFIED'}
    need(type(year) is int,'verified cover requires literal fiscal year')
    protected=old['asset_report'];controls=0
    if protected is not None:
        need(protected['record_id']==digest({k:v for k,v in protected.items() if k!='record_id'}),'protected whole asset record identity')
        try:assets=cash.v1.parse_asset_cells(pages,year,normative_basis=normative_basis)
        except ValueError:assets=None
        if assets is not None:
            for period,before in protected['payload']['balances'].items():
                need(period in assets and all(before[k]==assets[period][k] for k in ('value_CNY','literal','fiscal_end','column_index')),'protected original asset disagreement')
                controls+=1
    result['protected_asset_cells_compared']=controls
    try:parsed=cash.parse_report(pages,year,normative_basis=normative_basis);report=cash.make_report(doc,parsed)
    except (ValueError,KeyError,ArithmeticError) as exc:return {**result,'status':UNSUPPORTED,'error_type':type(exc).__name__,'error':str(exc)}
    return {**result,'status':SUPPORTED,'report':report}

def validate_case(case,doc,base,known,normative_basis=None):
    metadata(doc);_,old,cache=case_paths(base,doc)
    need(case['old_asset_case_sha256']==known[str(old.resolve())] and case['source_page_cache_sha256']==known[str(cache.resolve())],'original case/page lineage')
    need(all(case[k]==doc[d] for k,d in [('capture_key','capture_key'),('instrument','instrument'),('fiscal_year','effective_fiscal_year'),('publication_day','day'),('source_sha256','source_sha256')]),'worker source identity')
    need(case['investment_factor_admitted'] is False and case['historical_arrival_verified'] is False,'no investment/arrival assurance')
    need(case['status'] in (SUPPORTED,UNSUPPORTED,'COVER_IDENTITY_UNVERIFIED'),'registered source status')
    if case['status']==SUPPORTED:
        need(cash.make_report(doc,case['report']['parsed'])==case['report'],'coherent original cash report')
        pages=read_bound(cache,known[str(cache.resolve())])['pages'];cash.verify_source_tables(case['report']['parsed'],pages,doc['effective_fiscal_year'],normative_basis=normative_basis)
    else:need(case['report'] is None,'failed source cannot supply money')

def bindings(base,root):
    qa=read(root/ASSET_QA);old=read(root/ASSET_REQUEST);byte=read(root/BYTE_QA);gate=read(root/LEDGER_QA)
    need(qa['document_count']==400 and qa['all_original_inputs_unchanged'] and qa['unsupported_schema_failures_not_reclassified'],'original400source audit')
    need(qa['request_sha256']==sha(root/ASSET_REQUEST) and byte['all400_originals_captured'] is True and not byte['source_rejections'],'authenticated original source authorities')
    need(gate['status']=='PASS_SEPARATE_INTEGER_LEDGER_SNAPSHOTS_AND_RATIONAL_ALLOCATOR' and gate['all_inputs_outputs_unchanged'],'raw-share2024/2025must pass before future cash fields')
    p=gate['cases']['40'];need(min(p['2024_return_pct'],p['2025_return_pct'])>0 and p['average_exposure_pct']>=90,'frozen high-cost development gate')
    known={}
    def bind(path,h=None):
        path=Path(path);h=h or sha(path);key=str(path.resolve());need(not path.is_symlink() and (key not in known or known[key]==h) and sha(path)==h,'unchanged original source '+str(path));known[key]=h
    for name in (ASSET_QA,ASSET_REQUEST,BYTE_QA,LEDGER_QA,DESIGN,*METHODS):bind(root/name)
    need(tree(base/OLD)==qa['all_original_extraction_output_sha256'],'entire retained original source case/cache tree')
    for n,h in qa['all_original_extraction_output_sha256'].items():bind(base/OLD/n,h)
    for n,h in byte['all_output_sha256'].items():bind(base/'asset-expansion-2026-annual-pdfs-20261023'/n,h)
    for path,h in gate['all_output_sha256'].items():bind(base/'cash-accrual-integer-pre2026-v1-20261028'/path,h)
    for path,h in old['currency_source_sha256'].items():bind(base/path,h)
    return known

def verify(base,root,membership,request,expected):
    req=read_bound(request,expected);need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed400source-only2026protocol')
    known=bindings(base,root);need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS) and all(sha(root/n)==h for n,h in req['method_sha256'].items()),'entire source/method closure')
    old=read(root/ASSET_REQUEST);docs=[]
    for d in old['documents']:
        c=read_bound(base/OLD/(d['key']+'.json'),known[str((base/OLD/(d['key']+'.json')).resolve())]);docs.append({**d,'capture_key':d['key'],'effective_fiscal_year':c['fiscal_year']})
    need(req['documents']==docs and req['normative_basis']==old['normative_basis'] and len(docs)==400 and len({d['capture_key'] for d in docs})==400,'all original400editions unchanged')
    known[str(request.resolve())]=expected;req['request_sha256']=expected;return req,known

def execute(req,known,out,base,*,worker=inspect_one,executor_factory=ProcessPoolExecutor):
    out=Path(out);base=Path(base);need(not out.exists() and not changed(known),'fresh unchanged source output');out.mkdir();outputs={};results={};submitted=[];failed=[];error=None;index=None;stage='SETUP'
    state={'status':'CASH2026_SOURCE_INCOMPLETE','complete':False,'request_sha256':req['request_sha256'],'investment_factor_admitted':False,
           'ratios_rankings_or_returns_computed':False,'2026_financial_fields_read':True,'objective_achieved':False,'sealed_evidence':False}
    def save(n,v):persist(out,n,v,outputs)
    def stamp(p):s=Path(p).stat();return(s.st_ino,s.st_size,s.st_mtime_ns)
    try:
        stamps={p:stamp(p) for p in known}
        with executor_factory(max_workers=4) as pool:
            for start in range(0,len(req['documents']),4):
                need(all(stamp(p)==v for p,v in stamps.items()) and tree(out)==outputs,'context between batches');stage='BATCH';peers=[];batch_error=None;first=None
                for i,d in enumerate(req['documents'][start:start+4]):
                    index=start+i
                    try:subset={str(p.resolve()):known[str(p.resolve())] for p in case_paths(base,d)};future=pool.submit(worker,base,deepcopy(d),req['normative_basis'],subset)
                    except BaseException as exc:batch_error=exc;first=index;break
                    submitted.append(d['capture_key']);peers.append((index,d,future))
                for i,d,future in peers:
                    index=i
                    try:
                        c=future.result();validate_case(c,d,base,known,req['normative_basis']);save('cases/'+d['capture_key']+'.json',c)
                        results[d['capture_key']]={'status':c['status'],'sha256':outputs['cases/'+d['capture_key']+'.json'],'instrument':c['instrument'],'fiscal_year':c['fiscal_year'],'protected_asset_cells_compared':c['protected_asset_cells_compared'],'error':c.get('error'),'source_parser_variant':c['source_parser_variant']}
                    except BaseException as exc:
                        failed.append({'capture_key':d['capture_key'],'type':type(exc).__name__,'error':str(exc)})
                        if batch_error is None:batch_error=exc;first=i
                if batch_error is not None:index=first;raise batch_error
                if len(results)%100==0 or len(results)==len(req['documents']):print('cash2026source',len(results),'/',len(req['documents']),flush=True)
        stage='FINAL';need(not changed(known) and len(results)==len(req['documents']),'all sources complete and unchanged')
        supported=[c for c in results.values() if c['status']==SUPPORTED]
        state.update(status='ALL400_FROZEN_V3_CASH2026_SOURCES_COMPLETE_NOT_FACTOR_ADMITTED',complete=True,summary={'document_count':len(results),'cohort_count':len(req['cohort']),
            'status_counts':dict(Counter(c['status'] for c in results.values())),'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if c['error'])),
            'supported_source_issuer_count':len({c['instrument'] for c in supported}),'raw_monetary_cells':len(supported)*6,'protected_asset_cells_compared':sum(c['protected_asset_cells_compared'] for c in results.values())})
    except BaseException as exc:error=exc;state.update(complete=False,error_type=type(exc).__name__,error=str(exc),failed_stage=stage,failed_row_index=index)
    state.update(completed_documents=len(results),submitted_keys=submitted,failed_documents=failed,pending=[d['capture_key'] for d in req['documents'] if d['capture_key'] not in results])
    try:save('case_index.json',results)
    except BaseException as exc:
        state['complete']=False
        if error is None:error=exc;state.update(error_type=type(exc).__name__,error=str(exc),failed_stage='CASE_INDEX')
    try:value=legacy.finish_source(out,state,known,outputs)
    except BaseException as exc:
        if error is None:error=exc
        else:error.add_note('finalization:'+type(exc).__name__)
    if error is not None:raise error
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1]
    req,known=verify(base,root,None,Path(a.request).resolve(),a.expected_request_sha256);print(execute(req,known,base/OUTPUT,base)['status'])
if __name__=='__main__':main()
