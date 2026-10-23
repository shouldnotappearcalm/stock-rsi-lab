"""Independent completion/clock/HTTP audit layered on the pinned metadata QA."""
import argparse
from collections import Counter
from datetime import date,datetime
import hashlib,importlib.util,json,re
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(x,m):
    if not x:raise ValueError(m)
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}
def load(p,name):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base,repo,request,run,out=map(Path,(a.source_root,a.repo_root,a.request,a.run_dir,a.output))
    need(not out.exists() and sha(request)==a.expected_request_sha256,'fresh external QA/frozen completion request')
    r=read(request);before=inventory(run);parent=base/'asset-expansion-2026-annual-metadata-curl-20261022'
    parentqa=read(repo/'experiments/qlib/asset-expansion-2026-merged-metadata-audit.json')
    helper=Path(__file__).with_name('2026-10-22-asset-expansion-2026-merged-metadata-audit.py')
    need(sha(helper)==parentqa['audit_code_sha256'],'pinned prior separate full-source checker')
    previous=load(helper,'previous_separate_merged_metadata')
    previous_req=repo/'experiments/qlib/asset-expansion-2026-metadata-curl-request.json'
    checked=previous.audit(base,repo,previous_req,sha(previous_req),parent)
    need(checked['all_output_sha256']==parentqa['all_output_sha256'] and len(checked['source_rejections'])==1,'all original397 attempts and one remaining rejection retained')
    bound={request:a.expected_request_sha256}
    for group in ('method_sha256','public_sha256'):
        for n,h in r[group].items():bound[repo/n]=h
    for n,h in parentqa['all_output_sha256'].items():bound[parent/n]=h
    for p,h in bound.items():need(sha(p)==h,'completion input before '+str(p))
    terminal=read(run/'terminal.json');summary=read(run/'summary.json')
    need(terminal['new_attempts']==1 and terminal['global_attempts']==398 and terminal['original_error'] is None
        and not terminal['changed_original_inputs'],'one completed third TLS attempt/global398')
    expected=read(parent/'case_results.json');completions=read(run/'title_completions.json')
    need(len(completions)==1 and completions[0]['instrument']=='SH600704','one coded-title source interpretation')
    c=completions[0];source=next(v for v in expected['SH600704']['all_normalized_rows'] if v['announcement_id']=='1225202697')
    need(source==c['original_row'] and source['classification']=='OTHER_ANNUAL_CATEGORY_TITLE_RETAINED','exact original title row retained')
    m=re.fullmatch(r'(\d{6})_([^_]+)_((?:19|20)\d{2})年_年度报告(\d{8})',source['title'])
    need(m is not None and m[1]==source['instrument'][2:] and int(m[3])<=2025,'literal coded issuer/fiscal year')
    stamp=datetime.strptime(m[4],'%Y%m%d').date();need(date(int(m[3]),12,31)<stamp<=date.fromisoformat(source['day']),'filename date is not a future source date')
    need(re.fullmatch('finalpage/'+re.escape(source['day'])+'/'+source['announcement_id']+r'\.[pP][dD][fF]',source['pdf_path']),'original exact PDF identity/path')
    completed={**source,'classification':'CODED_TITLE_FULL_REPORT_CANDIDATE','fiscal_year':int(m[3]),'edition':'INITIAL_OR_UNSPECIFIED',
        'original_row_sha256':digest(source),'title_date_not_publication_clock':stamp.isoformat()}
    need(completed==c['completed_row'] and completed['day']=='2026-04-28' and completed['title_date_not_publication_clock']=='2026-04-27','source grammar completion never backdates publication')
    case=expected['SH600704'];case['all_normalized_rows']=[completed if v['announcement_id']==source['announcement_id'] else v for v in case['all_normalized_rows']]
    case['full_report_candidates']=[v for v in case['all_normalized_rows'] if 'CANDIDATE' in v['classification']];case['status']='METADATA_CAPTURED_WITH_CANDIDATES'
    resource=r['resources']['SH600118'];folder=run/'http'/digest({'resource':'SH600118','identity':resource})
    q,res,response=(read(folder/n) for n in ('request.json','reservation.json','response.json'))
    need(q=={'resource':'SH600118',**resource} and res['attempt']==1 and res['identity_sha256']==digest(resource)
        and response['identity_sha256']==digest(resource) and response['request_sha256']==sha(folder/'request.json')
        and response['reservation_sha256']==sha(folder/'reservation.json'),'one exact new source request/hash chain')
    need(response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and response['http_status']==200
        and response['body_complete'] is True and response['final_url']==resource['url'],'complete source metadata HTTP200')
    body=folder/'body.bin';need(sha(body)==response['body_sha256'] and body.stat().st_size==response['body_bytes']<=1048576,'complete source bytes')
    tfolder=run/'curl-transport'/folder.name;transport=read(tfolder/'transport.json')
    need(transport['returncode']==0 and transport['automatic_retries']==0 and transport['redirects_permitted'] is False
        and read(tfolder/'request.json')==q and all(sha(tfolder/n)==h for n,h in transport['artifact_sha256'].items())
        and (tfolder/'body.bin').read_bytes()==body.read_bytes()
        and (tfolder/'stdout.bin').read_text().strip().splitlines()==['200',resource['url']],'exact curl body/status/artifact lineage')
    normalizer=load(Path(__file__).with_name('2026-10-22-asset-expansion-2026-metadata-audit.py'),'separate_metadata_rows_for_completion')
    rows,candidates=normalizer.normalize('SH600118',json.loads(body.read_bytes()))
    fresh={'instrument':'SH600118','status':'METADATA_CAPTURED_WITH_CANDIDATES' if candidates else 'METADATA_CAPTURED_NO_FULL_CANDIDATE',
        'receipt':{'folder':str(folder.relative_to(run)),'record':response,'response_sha256':sha(folder/'response.json')},
        'all_normalized_rows':rows,'full_report_candidates':candidates,'edition_selected_for_financial_values':False}
    need(read(run/'source-result.json')==fresh,'new source row interpretation independently reproduced');expected['SH600118']=fresh
    cases=read(run/'case_results.json');need(cases==expected and len(cases)==394,'all inherited cases unchanged except two explicit completions')
    for code,case in cases.items():need(read(run/(code+'.json'))==case,'complete per-issuer case file')
    origins=read(parent/'case_origins.json');origins['SH600118']=run.name;need(read(run/'case_origins.json')==origins,'exact inherited HTTP origin directories')
    counts=Counter(v['status'] for v in cases.values());reports=[v for case in cases.values() for v in case['full_report_candidates']]
    fiscal=Counter(str(v['fiscal_year']) for v in reports)
    need(summary['status_counts']==dict(counts) and summary['full_report_candidates']==len(reports)
        and summary['candidate_fiscal_year_counts']==dict(fiscal) and summary['global_logical_attempts']==398
        and summary['financial_numeric_values_decoded'] is False and summary['2026_portfolio_returns_computed'] is False,'complete metadata-only summary')
    for p,h in bound.items():need(sha(p)==h,'completion input after '+str(p))
    need(inventory(run)==before,'all completion output bytes unchanged')
    result={'status':'SEPARATE_ALL394_COMPLETED_METADATA_CLOCK_AND_HTTP_AUDIT_PASSED_NOT_FINANCIAL_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':sha(request),'summary_sha256':sha(run/'summary.json'),
        'shared_prior_separate_checker_sha256':sha(helper),'source_issuers_checked':394,'full_report_candidates':len(reports),
        'candidate_fiscal_year_counts':dict(fiscal),'status_counts':dict(counts),'all_394_sources_accepted':'METADATA_SOURCE_REJECTED' not in counts,
        'global_logical_attempts':398,'original_source_failures_retained':True,'title_schema_completions_checked':1,
        'publication_clock_preserved':True,'all_output_sha256':before,'all_original_inputs_unchanged':True,
        'no_production_imports':True,'same_researcher_separate_QA':True,'PDF_bytes_or_financial_values_read':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'2026_portfolio_returns_computed':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],'394issuers',len(reports),'candidate originals')

if __name__=='__main__':main()
