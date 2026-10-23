"""Separate coded-title interpretation and one registered final metadata retry."""
import argparse
from collections import Counter
import copy
from datetime import date,datetime
import json
from pathlib import Path
import re

from scripts import capture_asset_expansion_2026_annual_metadata as original
from scripts.frozen_curl_http import FrozenCurlOpener
from scripts.immutable_http_capture import ImmutableHttpCapture,digest,file_sha,need,write_once

PARENT='asset-expansion-2026-annual-metadata-curl-20261022'
OUTPUT='asset-expansion-2026-metadata-completed-20261023'
CODE='SH600118'
METHODS=('scripts/complete_asset_expansion_2026_metadata.py','scripts/frozen_curl_http.py',
    'scripts/immutable_http_capture.py','scripts/capture_asset_expansion_2026_annual_metadata.py',
    'tests/test_asset_expansion_2026_metadata_completion.py')


def read(p):return json.loads(Path(p).read_text())


def coded_title(row):
    title=re.sub(r'\s+','',re.sub(r'<[^>]+>','',row['title']))
    m=re.fullmatch(r'(?P<code>\d{6})_(?P<name>[^_]+)_(?P<year>(?:19|20)\d{2})年_年度报告(?P<date>\d{8})',title)
    if m is None:return None
    year=int(m['year']);stamp=datetime.strptime(m['date'],'%Y%m%d').date();published=date.fromisoformat(row['day'])
    need(m['code']==row['instrument'][2:] and year<=2025 and date(year,12,31)<stamp<=published,
        'coded title issuer/fiscal-year/filename-date contradiction')
    # The filename-style date is checked only. It never replaces the source publication clock.
    return {**row,'classification':'CODED_TITLE_FULL_REPORT_CANDIDATE','fiscal_year':year,
        'edition':'INITIAL_OR_UNSPECIFIED','original_row_sha256':digest(row),
        'title_date_not_publication_clock':stamp.isoformat()}


def run(base,repo,request,expected,out):
    need(not out.exists() and file_sha(request)==expected,'fresh frozen metadata completion')
    r=read(request)
    need(r['status']=='FROZEN_ONE_FINAL_TLS_RETRY_AND_CODED_TITLE_METADATA_COMPLETION'
        and r['maximum_new_logical_attempts']==1 and r['maximum_global_logical_attempts']==398
        and r['global_attempts_for_SH600118']==3 and set(r['method_sha256'])==set(METHODS),'explicit one-request/global398 completion scope')
    bound={request:expected}
    for group,parent in (('method_sha256',repo),('public_sha256',repo)):
        for n,h in r[group].items():
            need(not Path(n).is_absolute() and '..' not in Path(n).parts,'root-relative completion input')
            bound[parent/n]=h
    qa=read(repo/'experiments/qlib/asset-expansion-2026-merged-metadata-audit.json')
    need(qa['source_issuers_checked']==394 and len(qa['source_rejections'])==1
        and qa['source_rejections'][0]['instrument']==CODE and qa['no_production_imports'] is True
        and digest(qa['all_output_sha256'])==r['parent_all_output_sha256_digest'],'separately audited single remaining TLS source')
    parent=base/PARENT
    for n,h in qa['all_output_sha256'].items():bound[parent/n]=h
    for p,h in bound.items():need(file_sha(p)==h,'original input changed: '+str(p))
    cases=copy.deepcopy(read(parent/'case_results.json'));origins=read(parent/'case_origins.json')
    need(cases[CODE]['status']=='METADATA_SOURCE_REJECTED' and cases[CODE]['error_type']=='URLError'
        and 'SSL' in cases[CODE]['error'],'remaining terminal SSL failure must stay retained')
    source_request=read(repo/'experiments/qlib/asset-expansion-2026-metadata-request.json')
    resources={CODE:source_request['resources'][CODE]};need(r['resources']==resources,'exact same official source/cutoff; no probes')
    completions=[]
    for code,case in cases.items():
        if case['status']=='METADATA_SOURCE_REJECTED':continue
        rows=[]
        for row in case['all_normalized_rows']:
            completed=coded_title(row) if row['classification']=='OTHER_ANNUAL_CATEGORY_TITLE_RETAINED' else None
            if completed is not None:
                need(re.fullmatch('finalpage/'+re.escape(row['day'])+'/'+re.escape(row['announcement_id'])+r'\.[pP][dD][fF]',row['pdf_path']),
                    'completed candidate exact source PDF date/ID/path')
                completions.append({'instrument':code,'announcement_id':row['announcement_id'],'original_row':row,'completed_row':completed})
            rows.append(row if completed is None else completed)
        case['all_normalized_rows']=rows;case['full_report_candidates']=[x for x in rows if 'CANDIDATE' in x['classification']]
        case['status']='METADATA_CAPTURED_WITH_CANDIDATES' if case['full_report_candidates'] else 'METADATA_CAPTURED_NO_FULL_CANDIDATE'
    need(len(completions)==1 and completions[0]['instrument']=='SH600704'
        and completions[0]['announcement_id']=='1225202697','only discovered coded-title source completion')
    out.mkdir(parents=True);write_once(out/'input-before.json',{str(p):h for p,h in bound.items()})
    write_once(out/'title_completions.json',completions);journal=None;primary=None;result=None
    try:
        transport=FrozenCurlOpener(out/'curl-transport',resources,max_body_bytes=1048576)
        journal=ImmutableHttpCapture(out/'http',resources,max_attempts=1,max_body_bytes=1048576,opener=transport)
        receipt,body=journal.fetch(CODE);need(receipt['record']['http_status']==200,'final metadata HTTP status not200')
        rows,candidates=original.select_rows(CODE,json.loads(body.read_bytes()))
        result={'instrument':CODE,'status':'METADATA_CAPTURED_WITH_CANDIDATES' if candidates else 'METADATA_CAPTURED_NO_FULL_CANDIDATE',
            'receipt':receipt,'all_normalized_rows':rows,'full_report_candidates':candidates,'edition_selected_for_financial_values':False}
        write_once(out/'source-result.json',result);cases[CODE]=result;origins[CODE]=OUTPUT
    except BaseException as exc:
        primary=exc;write_once(out/'error.json',{'type':type(exc).__name__,'message':str(exc),'previous_failures_retained':True})
    finally:
        changed=[]
        for p,h in bound.items():
            try:
                if file_sha(p)!=h:changed.append(str(p))
            except BaseException as exc:changed.append(str(p)+':'+type(exc).__name__)
        write_once(out/'terminal.json',{'new_attempts':journal.attempts if journal else 0,'global_attempts':397+(journal.attempts if journal else 0),
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},'changed_original_inputs':changed})
    if primary is not None:raise primary
    need(not changed,'completion original source/method changed')
    write_once(out/'case_results.json',cases);write_once(out/'case_origins.json',origins)
    for code,case in cases.items():write_once(out/(code+'.json'),case)
    summary={'status':'ALL394_METADATA_WITH_EXPLICIT_TITLE_COMPLETION_NOT_FINANCIAL_ADMISSION','request_sha256':expected,
        'resource_count':394,'window':[original.START,original.END],'new_logical_attempts':journal.attempts,'global_logical_attempts':398,
        'old_source_failures_retained':True,'title_schema_completions':len(completions),
        'status_counts':dict(Counter(v['status'] for v in cases.values())),
        'full_report_candidates':sum(len(v.get('full_report_candidates',[])) for v in cases.values()),
        'candidate_fiscal_year_counts':dict(Counter(str(x['fiscal_year']) for v in cases.values() for x in v.get('full_report_candidates',[]))),
        'all_original_inputs_unchanged':True,'PDFs_downloaded':0,'financial_numeric_values_decoded':False,
        'historical_arrival_verified':False,'financial_version_history_complete':False,'2026_portfolio_returns_computed':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);print(summary['status'],summary['status_counts'],'candidates',summary['full_report_candidates'],flush=True)
    return summary


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[1]
    run(base,repo,Path(a.request).resolve(),a.expected_request_sha256,base/OUTPUT)

if __name__=='__main__':main()
