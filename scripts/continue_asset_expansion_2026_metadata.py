"""New380-request curl stage; reuse14 successes and retain3 original TLS failures."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from scripts import capture_asset_expansion_2026_annual_metadata as original
from scripts.frozen_curl_http import FrozenCurlOpener
from scripts.immutable_http_capture import ImmutableHttpCapture,file_sha,need,write_once

PARENT=original.OUTPUT
OUTPUT='asset-expansion-2026-annual-metadata-curl-20261022'
METHODS=('scripts/continue_asset_expansion_2026_metadata.py','scripts/frozen_curl_http.py',
    'scripts/capture_asset_expansion_2026_annual_metadata.py','scripts/immutable_http_capture.py',
    'tests/test_asset_expansion_2026_metadata.py','tests/test_frozen_curl_http.py',
    'tests/test_asset_expansion_2026_continuation.py')


def read(p):return json.loads(Path(p).read_text())


def remaining_scope(cohort,cases):
    need(set(cases)<=set(cohort),'parent cases within same cohort')
    valid=('METADATA_CAPTURED_WITH_CANDIDATES','METADATA_CAPTURED_NO_FULL_CANDIDATE')
    need(all(v['status'] in (*valid,'METADATA_SOURCE_REJECTED') for v in cases.values()),'explicit original source statuses')
    reused={c:cases[c] for c in cohort if c in cases and cases[c]['status'] in valid}
    return reused,[c for c in cohort if c not in reused],[c for c in cohort if c in cases and cases[c]['status']=='METADATA_SOURCE_REJECTED']


def capture(base,repo,request,expected,out):
    need(not out.exists() and file_sha(request)==expected,'fresh frozen curl continuation')
    r=read(request);bound={request:expected}
    need(r['status']=='FROZEN_ASSET_EXPANSION_380_CURL_METADATA_CONTINUATION'
        and r['maximum_new_logical_attempts']==380 and r['maximum_global_logical_attempts_including_parent']==397
        and r['maximum_global_attempts_for_original_TLS_cases']==2 and r['per_resource_attempts']==1
        and r['maximum_body_bytes']==1048576 and r['minimum_request_interval_seconds']==.2
        and set(r['method_sha256'])==set(METHODS),'exact curl continuation budget')
    for group,parent in (('method_sha256',repo),('public_sha256',repo),('source_sha256',base)):
        for n,h in r[group].items():
            need(not Path(n).is_absolute() and '..' not in Path(n).parts,'bound root-relative continuation input')
            bound[parent/n]=h
    for p,h in bound.items():need(file_sha(p)==h,'original failure/source/method changed: '+str(p))
    parent=base/PARENT;old=read(parent/'case_results.json');terminal=read(parent/'terminal.json')
    qa=read(repo/'experiments/qlib/asset-expansion-2026-metadata-prefix-audit.json')
    need(qa['resources_checked']==17 and len(qa['source_rejections'])==3 and qa['no_production_imports'] is True
        and all(file_sha(parent/n)==h for n,h in qa['all_output_sha256'].items()),'separately audited immutable original prefix')
    original_req=read(repo/'experiments/qlib/asset-expansion-2026-metadata-request.json')
    cohort=original_req['cohort'];reused,todo,retries=remaining_scope(cohort,old)
    need(len(old)==17 and len(reused)==14 and len(retries)==3 and len(terminal['pending'])==377
        and terminal['original_error']['type']=='ValueError'
        and retries==r['original_TLS_retry_codes'] and todo==r['codes_to_fetch']
        and r['resources']=={c:original_req['resources'][c] for c in todo},'unchanged fourteen successes and exact three retries/377first attempts')
    for c in retries:
        need(old[c]['error_type']=='URLError' and 'SSL' in old[c]['error'],'only retained TLS errors receive a second logical attempt')
    out.mkdir(parents=True);results=dict(reused);origins={c:PARENT for c in reused};journal=None;primary=None;persistence=[]
    try:
        write_once(out/'input-before.json',{str(p):h for p,h in bound.items()})
        for c in reused:(out/(c+'.json')).write_bytes((parent/(c+'.json')).read_bytes())
        transport=FrozenCurlOpener(out/'curl-transport',r['resources'],max_body_bytes=1048576)
        journal=ImmutableHttpCapture(out/'http',r['resources'],max_attempts=380,max_body_bytes=1048576,opener=transport)
        consecutive=0
        for number,code in enumerate(todo,1):
            receipt=None
            try:
                receipt,body=journal.fetch(code);need(receipt['record']['http_status']==200,'annual metadata HTTP status not200')
                rows,candidates=original.select_rows(code,json.loads(body.read_bytes()))
                value={'instrument':code,'status':'METADATA_CAPTURED_WITH_CANDIDATES' if candidates else 'METADATA_CAPTURED_NO_FULL_CANDIDATE',
                    'receipt':receipt,'all_normalized_rows':rows,'full_report_candidates':candidates,
                    'edition_selected_for_financial_values':False};consecutive=0
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                if getattr(exc,'capture_evidence_persistence_error',False):raise
                value={'instrument':code,'status':'METADATA_SOURCE_REJECTED','receipt':receipt,
                    'error_type':type(exc).__name__,'error':str(exc)};consecutive+=1
            results[code]=value;origins[code]=OUTPUT;write_once(out/(code+'.json'),value)
            print('curl2026metadata',number,'/380',code,value['status'],flush=True)
            if consecutive==3:raise ValueError('three consecutive curl source rejections; remaining resources not attempted')
            time.sleep(.2)
    except BaseException as exc:primary=exc
    finally:
        changed=[]
        for p,h in bound.items():
            try:
                if file_sha(p)!=h:changed.append(str(p))
            except BaseException as exc:changed.append(str(p)+':'+type(exc).__name__)
        ordered={c:results[c] for c in cohort if c in results};pending=[c for c in cohort if c not in results]
        terminal={'status':'ASSET_2026_CURL_METADATA_CONTINUATION_TERMINAL','new_logical_attempts':journal.attempts if journal else 0,
            'global_logical_attempts_including_parent':17+(journal.attempts if journal else 0),'reused_successful_cases':14,
            'completed_resources':len(results),'pending':pending,'changed_original_inputs':changed,
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},'persistence_errors':persistence}
        for name,value in (('case_results.json',ordered),('case_origins.json',origins),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if primary is not None:raise primary
    need(not changed and not persistence and not pending,'complete immutable merged metadata cases')
    summary={'status':'ALL394_2026_METADATA_MERGED_AFTER_SEPARATE_CURL_STAGE_NOT_FINANCIAL_ADMISSION',
        'request_sha256':expected,'parent_request_sha256':file_sha(repo/'experiments/qlib/asset-expansion-2026-metadata-request.json'),
        'window':[original.START,original.END],'resource_count':394,'reused_successful_cases':14,'new_logical_attempts':journal.attempts,
        'global_logical_attempts_including_parent':17+journal.attempts,'original_three_TLS_failures_retained':True,
        'status_counts':dict(Counter(v['status'] for v in results.values())),
        'full_report_candidates':sum(len(v.get('full_report_candidates',[])) for v in results.values()),
        'candidate_fiscal_year_counts':dict(Counter(str(row['fiscal_year']) for v in results.values() for row in v.get('full_report_candidates',[]))),
        'multiple_candidate_issuers':[c for c,v in results.items() if len(v.get('full_report_candidates',[]))>1],
        'no_candidate_issuers':[c for c,v in results.items() if v['status']=='METADATA_CAPTURED_NO_FULL_CANDIDATE'],
        'all_original_inputs_unchanged':True,'PDFs_downloaded':0,'financial_numeric_values_decoded':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,
        '2026_portfolio_returns_computed':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[1]
    r=capture(base,repo,Path(a.request).resolve(),a.expected_request_sha256,base/OUTPUT)
    print(r['status'],r['status_counts'],flush=True);return 2 if r['status_counts'].get('METADATA_SOURCE_REJECTED',0) else 0

if __name__=='__main__':raise SystemExit(main())
