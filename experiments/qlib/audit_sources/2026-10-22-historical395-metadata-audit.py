"""Separate395-source metadata/journal reconstruction; not blinded or numeric QA."""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import re


def need(v,why):
    if not v: raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def classify(code,year,data):
    need(type(data) is dict and type(data.get('totalAnnouncement')) is int,'integer source count')
    count,rows=data['totalAnnouncement'],data.get('announcements') or []
    need(0<=count<=30 and type(rows) is list and len(rows)==count and data.get('hasMore') in (None,False),'complete source page')
    allrows,selected,seen=[],[],set()
    for r in rows:
        need(type(r) is dict and r['secCode']==code[2:] and type(r['announcementTime']) is int,'source issuer and timestamp')
        day=datetime.fromtimestamp(r['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
        need(f'{year+1}-01-01'<=day<=f'{year+1}-12-31','source publication window')
        identity,title,path=str(r['announcementId']),r['announcementTitle'],r.get('adjunctUrl')
        need(identity.isdigit() and identity not in seen and type(title) is str,'source identity uniqueness');seen.add(identity)
        clean=re.sub(r'\s+','',re.sub(r'<[^>]+>','',title));kind='OTHER_ANNUAL_CATEGORY_NOTICE'
        if '摘要' in clean:kind='SUMMARY'
        elif '英文' in clean:kind='ENGLISH_EDITION'
        elif '可视' in clean:kind='VISUAL_EDITION'
        elif re.search(str(year)+r'年?年度报告(?:全文|[（(](?:全文|修订版?|修订稿|更正稿|更正后|更新后|更新版|中文版)[）)])?$',clean):
            kind='FULL_ANNUAL_REPORT_CANDIDATE'
            need(type(path) is str and re.fullmatch(r'finalpage/\d{4}-\d{2}-\d{2}/'+re.escape(identity)+r'\.[pP][dD][fF]',path),'safe candidate PDF path')
        row={'instrument':code,'requested_fiscal_year':year,'fiscal_year':year if kind=='FULL_ANNUAL_REPORT_CANDIDATE' else None,
             'title':title,'normalized_title':clean,'day':day,'timestamp_ms':r['announcementTime'],'announcement_id':identity,
             'pdf_path':path,'classification':kind}
        if kind=='FULL_ANNUAL_REPORT_CANDIDATE':
            row['edition_role']='EXPLICIT_REVISED_EDITION' if re.search(r'修订|更正|更新',clean) else 'INITIAL_OR_UNSPECIFIED_EDITION'
            selected.append(row)
        allrows.append(row)
    return allrows,selected


def main():
    parser=argparse.ArgumentParser()
    for n in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+n,required=True)
    a=parser.parse_args();root,base,membership,request,run,out=map(lambda p:Path(p).resolve(),
        (a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external report')
    need(sha(request)==a.expected_request_sha256,'frozen request identity');req=read(request)
    need(req['status']=='FROZEN_BEFORE_HISTORICAL394_EXACT395_ANNUAL_METADATA_READS'
         and req['max_logical_attempts']==395 and req['per_resource_attempts']==req['page_cap']==1
         and req['PDF_download_permitted'] is False and req['financial_numeric_parsing_permitted'] is False
         and req['ranking_or_portfolio_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'fixed395 source-only scope')
    old=base/'cninfo-csi500-reports-20261017';local=base/'gross-profitability-historical394-source-inventory-v2-20261022'
    docs=read(base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json')
    pdfs={d['capture_key']:d for d in docs}
    special={'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
        'PDF_document_records':base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json',
        'inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    paths={'frozen_source_request':request};expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    for key in req['input_sha256']:
        prefix,name=key.split('/',1);need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe bound input')
        if prefix=='repo':p=root/name
        elif prefix=='source':p=base/name
        else:
            need(prefix=='catalog','known source root')
            if name in special:p=special[name]
            elif name.startswith('metadata/'):
                code=name.split('/',1)[1];need(re.fullmatch(r'(?:SH60|SZ00)\d{4}',code),'source instrument path');p=old/'codes'/(code+'.json')
            else:
                need(name.startswith('PDF/') and name[4:] in pdfs,'known cached source')
                rel=pdfs[name[4:]]['source_path'];need(not Path(rel).is_absolute() and '..' not in Path(rel).parts,'safe cached original');p=base/rel
        paths[key]=p
    need(len(paths)==445,'complete445 frozen inputs')
    for key,p in paths.items():need(sha(p)==expected[key],'unchanged input before audit: '+key)
    cohort=sorted({c for c,s,e in (line.split() for line in membership.read_text().splitlines()) if s<='2024-01-02'<=e and c.startswith(('SH60','SZ00'))})
    need(len(cohort)==394,'dated mainboard cohort');catalog=read(local/'case_results.json')
    specs=[{'resource_key':c+'-2022','instrument':c,'fiscal_year':2022,'reason':'MISSING_INITIAL2022_METADATA'}
        for c in cohort if catalog[c]['2022']['status']=='INITIAL2022_METADATA_NOT_CAPTURED']
    need(len(specs)==382,'all382 missing initial filings')
    specs += [{'resource_key':c+'-'+str(y),'instrument':c,'fiscal_year':y,'reason':catalog[c][str(y)]['status']}
        for y in (2023,2024) for c in cohort if catalog[c][str(y)]['status']!='ONE_FULL_REPORT_METADATA_CANDIDATE']
    need(req['specifications']==specs and len(specs)==len({s['resource_key'] for s in specs})==395,'all395 original specs reconstructed')
    outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    cases,summary,terminal=map(lambda n:read(run/n),('case_results.json','summary.json','terminal.json'))
    need(set(cases)=={s['resource_key'] for s in specs},'all registered source packets')
    orgs=read(old/'plan.json')['org_by_code'];allowed={'case_results.json','summary.json','terminal.json','input-before.json','input-postcheck.json'}
    ids_by_key,repair_deltas={},{};body_bytes=0;counts=Counter()
    for spec in specs:
        key,code,year=spec['resource_key'],spec['instrument'],spec['fiscal_year']
        resource={'method':'POST','url':'https://www.cninfo.com.cn/new/hisAnnouncement/query','payload':{
            'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'','stock':code[2:]+','+orgs[code],
            'searchkey':'','secid':'','category':'category_ndbg_szsh','trade':'','seDate':f'{year+1}-01-01~{year+1}-12-31',
            'sortName':'','sortType':'','isHLtitle':'true'}}
        need(req['resources'][key]==resource,'exact original official resource');h=digest({'resource':key,'identity':resource})
        folder=run/'http'/h;names={p.name for p in folder.iterdir()};need(names in ({'request.json','reservation.json','response.json'},{'request.json','reservation.json','response.json','body.bin'}),'only registered HTTP files')
        allowed|={'http/'+h+'/'+name for name in names};allowed.add(key+'.json')
        need(read(folder/'request.json')=={'resource':key,**resource},'literal original HTTP request')
        reservation=read(folder/'reservation.json');response=read(folder/'response.json')
        need(reservation['resource']==key and reservation['identity_sha256']==digest(resource)
             and reservation['attempt']==reservation['maximum_logical_attempts']==1,'single reserved attempt')
        need(response['resource']==key and response['identity_sha256']==digest(resource)
             and response['request_sha256']==sha(folder/'request.json') and response['reservation_sha256']==sha(folder/'reservation.json'),'response request/reservation chain')
        if 'body.bin' in names:
            need(response['body_sha256']==sha(folder/'body.bin') and response['body_bytes']==(folder/'body.bin').stat().st_size,'exact captured body bytes');body_bytes+=response['body_bytes']
        captured=response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED'
        receipt={'folder':'http/'+h,'record':response,'response_sha256':sha(folder/'response.json')} if captured else None
        invalid=None;rows,candidates=[],[]
        try:
            need(captured and response['http_status']==200 and response['body_complete'] is True,'HTTP/body not admitted for parsing')
            rows,candidates=classify(code,year,read(folder/'body.bin'))
        except (ValueError,KeyError,TypeError,OSError,OverflowError) as exc:invalid=exc
        case=cases[key];need(case==read(run/(key+'.json')) and all(case[k]==v for k,v in spec.items()) and case['receipt']==receipt,'case/spec/raw receipt conservation')
        if invalid is not None:
            need(case['status']=='METADATA_SOURCE_REJECTED' and case['error_type'] and case['error'],'raw rejection retained')
        else:
            status='METADATA_CAPTURED_WITH_FULL_REPORT_CANDIDATES' if candidates else 'METADATA_CAPTURED_NO_LITERAL_FULL_REPORT_CANDIDATE'
            need(case['status']==status and case['all_normalized_rows']==rows and case['full_report_candidates']==candidates
                 and case['edition_selected_for_financial_values'] is False,'source rows and every edition independently reconstructed')
        counts[case['status']]+=1;ids_by_key[key]=[r['announcement_id'] for r in candidates]
        if year!=2022:
            oldrows=[r for r in read(old/'codes'/(code+'.json'))['reports']['annual'] if f'{year+1}-01-01'<=r['day']<=f'{year+1}-12-31']
            before={r['announcement_id'] for r in oldrows};after={r['announcement_id'] for r in rows}
            repair_deltas[key]={'original_catalog_status':spec['reason'],'prior_full_candidate_ids':[r['announcement_id'] for r in catalog[code][str(year)]['full_report_candidates']],
                'new_full_candidate_ids':ids_by_key[key],'prior_publication_year_metadata_IDs':sorted(before),'new_publication_year_metadata_IDs':sorted(after),
                'added_raw_ids':sorted(after-before),'absent_raw_ids':sorted(before-after),'edition_selected':False}
    need(set(outputs)==allowed,'no unregistered source/output artifact')
    multiple=[s['resource_key'] for s in specs if len(ids_by_key[s['resource_key']])>1]
    missing=[s['resource_key'] for s in specs if cases[s['resource_key']]['status']=='METADATA_CAPTURED_NO_LITERAL_FULL_REPORT_CANDIDATE']
    need(summary['status']=='ALL395_METADATA_RESOURCES_PROCESSED_NOT_DATA_ADMITTED' and summary['request_sha256']==a.expected_request_sha256
         and summary['resource_count']==summary['logical_attempts']==395 and summary['status_counts']==dict(counts)
         and summary['full_report_candidates']==sum(map(len,ids_by_key.values())) and summary['multiple_candidate_resources']==multiple
         and summary['no_literal_candidate_resources']==missing and summary['input_count']==445 and summary['all_inputs_unchanged'] is True,'complete raw metadata summary')
    post={'all_inputs_unchanged':True,'count':445,'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json')==expected and read(run/'input-postcheck.json')==post and terminal['postcheck']==post
         and terminal['logical_attempts']==terminal['completed_resources']==395 and terminal['pending']==[]
         and terminal['original_error'] is None and terminal['persistence_errors']==[],'successful completion journals, not factor admission')
    for key,p in paths.items():need(sha(p)==expected[key],'unchanged input after audit: '+key)
    need(outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'all output bytes unchanged during audit')
    report={'status':'PASS_SEPARATE395_METADATA_AND_SINGLE_ATTEMPT_AUDIT_NOT_FINANCIAL_DATA_ADMISSION',
        'audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,'all445_input_sha256':expected,
        'all_output_sha256':outputs,'output_files':len(outputs),'logical_POST_attempts':395,'status_counts':dict(counts),
        'raw_HTTP_body_bytes':body_bytes,'full_report_candidates':sum(map(len,ids_by_key.values())),
        'full_candidate_IDs_by_resource':ids_by_key,'13_repair_source_deltas':repair_deltas,
        'production_modules_imported':False,'authored_after_capture_started_same_researcher_not_blinded':True,
        'PDFs_downloaded':0,'financial_numeric_values_decoded':False,'financial_version_history_complete':False,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'portfolio_returns_computed':False,
        '2026_financial_or_market_values_decoded':False,'objective_achieved':False}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(report['status'],sha(out),len(outputs),dict(counts))


if __name__=='__main__':main()
