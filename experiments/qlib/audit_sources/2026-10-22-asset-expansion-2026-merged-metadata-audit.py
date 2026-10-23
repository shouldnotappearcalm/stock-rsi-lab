"""Separate HTTP/curl/origin audit of all394 metadata cases; no production imports."""
import argparse
from collections import Counter
import hashlib,importlib.util,json
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(x,m):
    if not x:raise ValueError(m)
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}


def audit(base,repo,request,expected,run):
    need(sha(request)==expected,'frozen curl continuation');req=read(request);before=inventory(run)
    helper=Path(__file__).with_name('2026-10-22-asset-expansion-2026-metadata-audit.py')
    prior=read(repo/'experiments/qlib/asset-expansion-2026-metadata-prefix-audit.json')
    need(sha(helper)==prior['audit_code_sha256'],'same pinned separate metadata normalizer')
    spec=importlib.util.spec_from_file_location('separate_2026_metadata_rows',helper);normalizer=importlib.util.module_from_spec(spec);spec.loader.exec_module(normalizer)
    old_request=repo/'experiments/qlib/asset-expansion-2026-metadata-request.json';original=read(old_request)
    parent=base/'asset-expansion-2026-annual-metadata-20261022'
    checked=normalizer.audit(base,repo,old_request,sha(old_request),parent)
    need(checked['all_output_sha256']==prior['all_output_sha256'] and checked['resources_checked']==17
        and len(checked['source_rejections'])==3,'original seventeen cases/three failures independently rechecked')
    bound={request:expected}
    for group,p in (('method_sha256',repo),('public_sha256',repo),('source_sha256',base)):
        for name,h in req[group].items():bound[p/name]=h
    for p,h in bound.items():need(sha(p)==h,'input before '+str(p))
    cases=read(run/'case_results.json');origins=read(run/'case_origins.json');terminal=read(run/'terminal.json')
    need(list(cases)==original['cohort'] and set(cases)==set(origins) and len(cases)==394
        and terminal['completed_resources']==394 and not terminal['pending'] and terminal['original_error'] is None
        and not terminal['changed_original_inputs'] and not terminal['persistence_errors'],'complete merged394 source cases')
    need(read(run/'input-before.json')=={str(p):h for p,h in bound.items()},'frozen continuation input map')
    counts=Counter();kinds=Counter();fiscal=Counter();rows_checked=0;candidate_records=[];rejected=[];reused=0;curl_checked=0
    for code,case in cases.items():
        origin=origins[code];need(origin in (parent.name,run.name),'explicit immutable case-origin root')
        directory=base/origin;need(read(run/(code+'.json'))==case,'per-case root identity')
        if origin==parent.name:
            need((run/(code+'.json')).read_bytes()==(parent/(code+'.json')).read_bytes()
                and case['status']!='METADATA_SOURCE_REJECTED','only successful original case reused byte-identically');reused+=1
        else:need(code in req['codes_to_fetch'],'registered new source identity')
        resource=original['resources'][code];folder=directory/'http'/digest({'resource':code,'identity':resource})
        q,res,response=(read(folder/n) for n in ('request.json','reservation.json','response.json'))
        need(q=={'resource':code,**resource} and res['resource']==code and res['identity_sha256']==digest(resource)
            and res['attempt']==1 and res['maximum_logical_attempts']==1,'exact original method/URL/form and one logical attempt')
        need(response['resource']==code and response['identity_sha256']==digest(resource)
            and response['request_sha256']==sha(folder/'request.json')
            and response['reservation_sha256']==sha(folder/'reservation.json'),'HTTP source checksum chain')
        counts[case['status']]+=1
        if case['status']=='METADATA_SOURCE_REJECTED':
            rejected.append({'instrument':code,'error_type':case['error_type'],'error':case['error'],'origin':origin});continue
        need(response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and response['http_status']==200
            and response['body_complete'] is True and response['final_url']==resource['url'],'complete original HTTP200 metadata')
        body=folder/'body.bin';need(sha(body)==response['body_sha256'] and body.stat().st_size==response['body_bytes']<=1048576,'exact raw body bytes')
        need(case['receipt']=={'folder':str(folder.relative_to(directory)),'record':response,'response_sha256':sha(folder/'response.json')},'full persisted case receipt')
        if origin==run.name:
            tfolder=run/'curl-transport'/digest({'resource':code,'identity':resource});tr=read(tfolder/'transport.json')
            need(read(tfolder/'request.json')==q and tr['resource']==code and tr['returncode']==0
                and tr['original_error'] is None and tr['automatic_retries']==0 and tr['redirects_permitted'] is False,'successful exact curl identity/no implicit retry or redirect')
            need(set(tr['artifact_sha256'])=={'request.json','headers.bin','body.bin','stdout.bin','stderr.bin'}
                and all(sha(tfolder/n)==h for n,h in tr['artifact_sha256'].items()),'all original curl artifacts authenticated')
            need((tfolder/'body.bin').read_bytes()==body.read_bytes()
                and (tfolder/'stdout.bin').read_text().strip().splitlines()==['200',resource['url']],'curl body/status/final URL match immutable HTTP body')
            curl_checked+=1
        normalized,selected=normalizer.normalize(code,json.loads(body.read_bytes()))
        need(normalized==case['all_normalized_rows'] and selected==case['full_report_candidates']
            and case['edition_selected_for_financial_values'] is False,'separate exact title/year/edition/identity classification')
        need(case['status']==('METADATA_CAPTURED_WITH_CANDIDATES' if selected else 'METADATA_CAPTURED_NO_FULL_CANDIDATE'),'source case status')
        rows_checked+=len(normalized);kinds.update(r['classification'] for r in normalized);fiscal.update(str(r['fiscal_year']) for r in selected);candidate_records.extend(selected)
    need(reused==14 and len(list((run/'http').rglob('reservation.json')))==380
        and len(list((parent/'http').rglob('reservation.json')))==17
        and len(list((run/'curl-transport').rglob('transport.json')))==380
        and terminal['new_logical_attempts']==380 and terminal['global_logical_attempts_including_parent']==397,'complete global attempt accounting and fourteen exact reuses')
    summary=read(run/'summary.json');need(summary['resource_count']==394 and summary['status_counts']==dict(counts)
        and summary['full_report_candidates']==len(candidate_records) and summary['candidate_fiscal_year_counts']==dict(fiscal)
        and summary['all_original_inputs_unchanged'] is True and summary['PDFs_downloaded']==0
        and summary['financial_numeric_values_decoded'] is False and summary['2026_portfolio_returns_computed'] is False,'exact summary and metadata-only claim')
    for p,h in bound.items():need(sha(p)==h,'input after '+str(p))
    need(inventory(run)==before,'all merged HTTP/curl/case output bytes unchanged')
    return {'status':'SEPARATE_ALL394_MERGED_2026_METADATA_AND_CURL_BYTES_AUDITED_NOT_FINANCIAL_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'shared_separate_metadata_normalizer_sha256':sha(helper),
        'request_sha256':expected,'summary_sha256':sha(run/'summary.json'),'source_issuers_checked':394,
        'byte_identical_original_successes_reused':reused,'successful_curl_bodies_checked':curl_checked,
        'new_logical_attempts':380,'original_logical_attempts':17,'total_logical_attempts':397,
        'original_three_TLS_failures_retained':True,'source_rejections':rejected,'all_394_sources_accepted':not rejected,
        'status_counts':dict(counts),'original_rows_checked':rows_checked,'classification_counts':dict(kinds),
        'full_report_candidates':len(candidate_records),'candidate_fiscal_year_counts':dict(fiscal),
        'all_output_sha256':before,'all_original_inputs_unchanged':True,'no_production_imports':True,
        'same_researcher_separate_QA':True,'PDF_bytes_or_financial_values_read':False,
        'historical_arrival_verified':False,'financial_version_history_complete':False,
        '2026_portfolio_returns_computed':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.output);need(not out.exists(),'fresh external merged metadata QA')
    r=audit(Path(a.source_root),Path(a.repo_root),Path(a.request).resolve(),a.expected_request_sha256,Path(a.run_dir))
    with out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(r['status'],'issuers394','candidates',r['full_report_candidates'],'rejections',len(r['source_rejections']))

if __name__=='__main__':main()
