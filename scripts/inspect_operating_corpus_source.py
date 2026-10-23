"""Fixed original-cache operating sources and dated coverage; no financial ratios."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import os
from pathlib import Path
import sys

from scripts import build_profitability_availability as parent
from scripts.immutable_http_capture import file_sha as sha, need, write_once
from stock_rsi import annual_operating as op
from stock_rsi import operating_availability as availability
from stock_rsi.data import digest

OUTPUT='operating-corpus-source-v1-20261023'
PARENT_OUTPUT=parent.V7_OUTPUT
INDUSTRY_OUTPUT=parent.INDUSTRY_OUTPUT
INITIAL_CACHE='gross-profitability-historical394-initial2022-schema-20261022'
LATER_CACHE='gross-profitability-all1236-source-v6-20261022'
PARENT_REQUEST='experiments/qlib/profitability-monthly-availability-request.json'
PARENT_SHA='a753412c63a3b33d73ab1292bf423ea2b1ea3f3a749535e17a9a7e981e73ba7c'
STATUS='FROZEN_BEFORE_COMPLETE_OPERATING_CORPUS_SOURCE_AND_COVERAGE'
SUPPORTED=availability.SUPPORTED
WORKERS=4
PILOT='operating-profitability-source-fixture-20261023'
PILOT_FILES=('input-before.json','reports.json','snapshots.json','page-text-sha256.json','input-postcheck.json','terminal.json','summary.json')
METHODS=tuple(dict.fromkeys((*parent.METHODS,'src/stock_rsi/annual_operating.py','src/stock_rsi/operating_availability.py',
    *(f'src/stock_rsi/annual_profitability_v{i}.py' for i in range(2,8)),
    'src/stock_rsi/models.py','src/stock_rsi/time.py','scripts/inspect_operating_corpus_source.py','scripts/audit_operating_corpus_source.py')))
PUBLIC=(PARENT_REQUEST,'experiments/qlib/operating-profitability-source-request.json',
    'experiments/qlib/operating-corpus-source-review.json',
    'experiments/qlib/operating-profitability-source-review.json','experiments/qlib/operating-profitability-source-results.json',
    'experiments/qlib/operating-profitability-source-independent-check.json',
    'tests/fixtures/annual-operating-real-row-vintages.json','tests/test_operating_availability.py',
    'tests/test_operating_corpus_runner.py','tests/test_operating_corpus_audit.py',
    'docs/research/operating-corpus-source-design-2026-10-23.md','docs/superpowers/plans/2026-10-23-operating-corpus-source.md')


def read(path):return parent.read(path)


def required_paths(base,root,membership):
    old=read(root/PARENT_REQUEST)
    paths={k:parent.resolve(k,root,base,membership) for k in old['input_sha256']}
    for name in (*METHODS,*PUBLIC):paths['repo/'+name]=root/name
    paths['membership']=membership
    for name in PILOT_FILES:paths['source/'+PILOT+'/'+name]=base/PILOT/name
    for name in ('operating-profitability-source-independent-check-20261023.json','operating-profitability-cohort-metadata-inventory-20261023.json'):
        paths['source/'+name]=base/name
    for doc in old['documents']:
        need(doc['source_phase'] in ('INITIAL_AUTHENTICATED_PAGE_CACHE','LATER_ORIGINAL_PDF'),'fixed cache phase')
        folder=INITIAL_CACHE if doc['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER_CACHE
        name=folder+'/'+doc['capture_key']+'.pages.json';paths['source/'+name]=base/name
    return paths


def verify(base,root,membership,request_file,expected_sha):
    need(sha(request_file)==expected_sha,'frozen operating corpus request')
    req=read(request_file)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['document_count']==1236
         and req['cohort_count']==394 and req['workers']==req['maximum_outstanding_documents']==4
         and req['runtime_python']==sys.version.split()[0]=='3.11.15'
         and req['parser_contract']==op.CONTRACT and req['normative_basis']==op.CAS19_REFERENCE
         and req['modes']==[op.OBSERVED,op.RECONSTRUCTED] and req['maximum_publication_day']=='2025-12-31'
         and req['new_PDF_text_decodings_permitted'] is False and req['network_permitted'] is False
         and req['ratios_rankings_or_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False
         and req['newer_source_failures_block_older_values'] is True and req['older_reissues_retained']==6
         and set(req['method_sha256'])==set(METHODS),'complete fixed operating-corpus scope')
    paths=required_paths(base,root,membership)
    need(set(paths)==set(req['input_sha256']),'complete exact source/method input closure')
    for key,path in paths.items():need(sha(path)==req['input_sha256'][key],'bound operating source input '+key)
    for name,value in req['method_sha256'].items():need(value==req['input_sha256']['repo/'+name],'method/input identity')
    need(sha(root/PARENT_REQUEST)==PARENT_SHA,'unchanged original complete source parent')
    old,_=parent.verify(base,root,membership,root/PARENT_REQUEST,PARENT_SHA)
    need(req['documents']==old['documents'] and req['cohort']==old['cohort'] and req['formations']==old['formations'],
         'same complete original documents/cohort/calendar; no success subset')
    for key,h in old['input_sha256'].items():need(req['input_sha256'][key]==h,'original source closure changed')
    need(len({d['capture_key'] for d in req['documents']})==len({d['announcement_id'] for d in req['documents']})==1236
         and all(d['day']<='2025-12-31' for d in req['documents'])
         and sum(d['effective_fiscal_year']<2022 for d in req['documents'])==6,'all original editions and older reissues retained')
    pilot=read(base/PILOT/'summary.json');proof=read(root/'experiments/qlib/operating-profitability-source-independent-check.json')
    need(pilot['contract']==op.CONTRACT and pilot['all_inputs_unchanged'] is True and pilot['filing_records']==2
         and proof['status']=='PASS_SEPARATE_TWO_REPORT_RAW_ARITHMETIC_AND_SOURCE_IDENTITIES'
         and proof['request_sha256']==pilot['request_sha256'],'completed original two-report source proof required')
    for name,h in proof['all_output_sha256'].items():need(sha(base/PILOT/name)==h,'pilot evidence unchanged')
    return req,paths


def inspect_one(base,document,normative_basis):
    base=Path(base);key=document['capture_key'];old_file=base/PARENT_OUTPUT/(key+'.json');old=read(old_file)
    need(sha(base/document['source_path'])==document['source_sha256']==old['source_sha256']
         and old['capture_key']==key and old['instrument']==document['instrument']
         and old['fiscal_year']==document['effective_fiscal_year'],'original source/case identity')
    phase=document['source_phase'];need(phase in ('INITIAL_AUTHENTICATED_PAGE_CACHE','LATER_ORIGINAL_PDF'),'known original cache phase')
    folder=INITIAL_CACHE if phase=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER_CACHE
    cache_file=base/folder/(key+'.pages.json');cache=read(cache_file);pages=cache['pages']
    need(cache['source_sha256']==document['source_sha256'] and cache['extractor']=='pypdf6.10.0'
         and len(pages)==old['page_count'] and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}
         ==old['all_extracted_page_text_sha256'],'authenticated cached pages required before source classification')
    result={'capture_key':key,'instrument':document['instrument'],'fiscal_year':document['effective_fiscal_year'],
        'publication_day':document['day'],'source_sha256':document['source_sha256'],'parent_case_sha256':sha(old_file),
        'source_page_cache_sha256':sha(cache_file),'page_count':len(pages),'GP_source_status':old['status'],
        'operating_report':None,'GP_control_cells_compared':0,'historical_arrival_verified':False,'investment_factor_admitted':False}
    if not(old['cover_code_consistent'] and old['cover_annual_year_consistent']):
        return {**result,'status':'COVER_IDENTITY_UNVERIFIED'}
    try:
        parsed=op.parse_report(pages,document['effective_fiscal_year'],normative_basis=normative_basis)
        report=op.make_report(document['instrument'],document['effective_fiscal_year'],document['day'],document['captured_at_utc'],
            document['source_sha256'],document['announcement_id'],parsed)
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':'OPERATING_SOURCE_SCHEMA_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc)}
    # Compatibility disagreement is a fatal source error, not a normal new-field
    # schema failure. Old GP success is not required for this independent measure.
    controls=0
    for observation in old['source_observations']:
        need(observation['record_id']==digest({k:v for k,v in observation.items() if k!='record_id'}),'old GP observation integrity')
        period=observation['fiscal_end'];legacy=observation['payload']['cells']
        for field in ('revenue','cost_of_sales','total_assets'):
            cell=parsed['balances'][period] if field=='total_assets' else parsed['income'][period][field]
            need(all(cell[name]==legacy[field][name] for name in ('value_CNY','literal','fiscal_end','column_index')),
                 'new source disagrees with protected old GP raw cell')
            controls+=1
    return {**result,'status':SUPPORTED,'operating_report':report,'GP_control_cells_compared':controls}


def run(base,root,membership,request_file,expected_sha,*,executor_factory=ProcessPoolExecutor,worker=inspect_one):
    out=base/OUTPUT;need(not out.exists(),'fresh operating output only; no overwrite/resume')
    req,paths=verify(base,root,membership,request_file,expected_sha)
    paths={**paths,'frozen_request':Path(request_file)};expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,path in paths.items():need(sha(path)==expected[key],'input before '+key)
    out.mkdir(parents=True);results={};submitted=[];failed=[];queries=[];primary=None;mismatches=[];persistence=[];summary=None
    try:
        write_once(out/'input-before.json',expected)
        with executor_factory(max_workers=WORKERS) as pool:
            for start in range(0,len(req['documents']),WORKERS):
                batch=req['documents'][start:start+WORKERS];futures=[];batch_error=None
                for doc in batch:
                    try:future=pool.submit(worker,str(base),doc,req['normative_basis'])
                    except BaseException as exc:
                        batch_error=exc;break
                    submitted.append(doc['capture_key']);futures.append((doc,future))
                # Drain every submitted peer even on failure. No later batch is
                # submitted; aggregate order remains the original request order.
                for doc,future in futures:
                    key=doc['capture_key']
                    try:
                        case=future.result()
                        need(case['capture_key']==key and case['source_sha256']==doc['source_sha256'],'source worker identity')
                        write_once(out/(key+'.json'),case);results[key]=case
                    except BaseException as exc:
                        failed.append({'capture_key':key,'type':type(exc).__name__,'message':str(exc)})
                        if batch_error is None:batch_error=exc
                if batch_error is not None:raise batch_error
                if len(results)%100==0 or len(results)==len(req['documents']):
                    print('operating source',len(results),'/',len(req['documents']),flush=True)
        need(set(results)=={d['capture_key'] for d in req['documents']},'complete original source cases required')
        write_once(out/'case_results.json',results)
        industry=read(base/INDUSTRY_OUTPUT/'catalog.json')
        for formation in req['formations']:
            for mode in req['modes']:
                view=availability.snapshot_availability(req['documents'],results.__getitem__,industry,req['cohort'],formation['as_of'],mode=mode)
                name=formation['execution_session']+'-'+mode+'.json';write_once(out/name,view)
                counts=dict(Counter(r['annual_status'] for r in view['classifications']))
                queries.append({**formation,'mode':mode,'artifact':name,'annual_status_counts':counts,
                    'industry_annual_status_counts':dict(Counter(r['industry_status']+'/'+r['annual_status'] for r in view['classifications']))})
        observed=sum(sum(v for k,v in q['annual_status_counts'].items() if k!='NO_VISIBLE_ANNUAL_REPORT') for q in queries if q['mode']==op.OBSERVED)
        need(observed==0,'actual2026 captures cannot enter observed historical views')
        reports=[c for c in results.values() if c['operating_report'] is not None]
        summary={'status':'COMPLETE_OPERATING_SOURCE_CORPUS_AND_COVERAGE_NOT_FACTOR_ADMITTED','request_sha256':expected_sha,
            'document_count':len(results),'cohort_count':len(req['cohort']),'status_counts':dict(Counter(c['status'] for c in results.values())),
            'status_counts_by_fiscal_year':{str(y):dict(Counter(c['status'] for c in results.values() if c['fiscal_year']==y)) for y in sorted({c['fiscal_year'] for c in results.values()})},
            'unsupported_error_counts':dict(Counter(c['error'] for c in results.values() if 'error' in c)),
            'source_report_count':len(reports),'supported_source_issuer_count':len({c['instrument'] for c in reports}),
            'raw_monetary_cells':len(reports)*12,'GP_control_cells_compared':sum(c['GP_control_cells_compared'] for c in results.values()),
            'older_reissues_retained':sum(c['fiscal_year']<2022 for c in results.values()),'queries':queries,
            'observed_visible_annual_rows':observed,'input_count':len(paths),'all_inputs_unchanged':True,
            'original_PDF_text_decodings_performed':0,'historical_arrival_verified':False,'current_business_identity_verified':False,
            'manual_visual_QA_complete':False,'financial_reporting_compatibility_verified':False,'investment_factor_admitted':False,
            'ratios_rankings_or_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
        write_once(out/'.summary-pending.json',summary)
    except BaseException as exc:primary=exc
    finally:
        if not (out/'case_results.json').exists():
            try:write_once(out/'case_results.json',results)
            except BaseException as exc:
                persistence.append('case_results.json:'+type(exc).__name__)
                if primary is None:primary=exc
        for key,path in paths.items():
            try:
                if sha(path)!=expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'count':len(paths),'all_inputs_unchanged':not mismatches,'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        try:write_once(out/'input-postcheck.json',post)
        except BaseException as exc:
            persistence.append('input-postcheck.json:'+type(exc).__name__)
            if primary is None:primary=exc
        if summary is not None and primary is None and not mismatches and not persistence:
            try:os.replace(out/'.summary-pending.json',out/'summary.json')
            except BaseException as exc:primary=exc
        terminal={'completed':summary is not None and primary is None and not mismatches and not persistence,
            'completed_documents':len(results),'submitted_keys':submitted,
            'failed_documents':failed,'unsubmitted_keys':[d['capture_key'] for d in req['documents'] if d['capture_key'] not in submitted],
            'pending':[d['capture_key'] for d in req['documents'] if d['capture_key'] not in results],
            'completed_queries':queries,'pending_query_count':len(req['formations'])*len(req['modes'])-len(queries),
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence,'ratios_rankings_or_returns_computed':False}
        try:
            write_once(out/'.terminal-pending.json',terminal);os.replace(out/'.terminal-pending.json',out/'terminal.json')
        except BaseException as exc:
            persistence.append('terminal.json:'+type(exc).__name__)
            if primary is None:primary=exc
            if (out/'summary.json').exists():
                try:os.replace(out/'summary.json',out/'uncommitted-summary.json')
                except BaseException as cleanup:persistence.append('summary-demotion:'+type(cleanup).__name__)
            terminal.update(completed=False,original_error={'type':type(primary).__name__,'message':str(primary)})
            try:
                write_once(out/'.terminal-failure.json',terminal);os.replace(out/'.terminal-failure.json',out/'terminal.json')
            except BaseException as failure:persistence.append('terminal-failure:'+type(failure).__name__)
    if primary is not None:
        if persistence:primary.add_note('source terminal persistence errors: '+str(persistence))
        raise primary
    need(not mismatches and not persistence and terminal['completed'],'complete unchanged source run and persistence required')
    return summary


def main():
    parser=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();summary=run(Path(args.source_root).resolve(),Path(__file__).resolve().parents[1],
        Path(args.membership_file).resolve(),Path(args.request).resolve(),args.expected_request_sha256)
    print(summary['status'],summary['status_counts'],flush=True)


if __name__=='__main__':main()
