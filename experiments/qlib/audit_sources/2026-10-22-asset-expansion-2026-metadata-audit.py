"""Separate stdlib raw-byte/count/edition QA; no production imports or PDF reads."""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib,json,re
from pathlib import Path

START,END='2026-01-01','2026-10-21'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(x,m):
    if not x:raise ValueError(m)
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}


def normalize(code,data):
    need(type(data) is dict and type(data.get('totalAnnouncement')) is int,'typed original count')
    count=data['totalAnnouncement'];rows=data.get('announcements')
    if rows is None and count==0:rows=[]
    need(0<=count<=30 and type(rows) is list and len(rows)==count
        and (data.get('hasMore') is None or data.get('hasMore') is False),'complete single-page metadata')
    result=[];seen=set()
    for r in rows:
        need(r['secCode']==code[2:] and type(r['announcementTime']) is int and type(r['announcementTitle']) is str,'raw issuer/timestamp/title')
        day=datetime.fromtimestamp(r['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
        need(START<=day<=END,'original publication cutoff')
        aid=str(r['announcementId']);need(aid.isdigit() and aid not in seen,'unique original announcement');seen.add(aid)
        title=r['announcementTitle'];plain=re.sub(r'[\s_《》]+','',re.sub(r'<[^>]+>','',title));year=None;edition=None
        if '摘要' in plain or re.search('abstract|summary',plain,re.I):kind='SUMMARY_METADATA_ONLY'
        elif '英文' in plain or re.search('annualreport',plain,re.I):kind='ENGLISH_METADATA_ONLY'
        elif '可视' in plain:kind='VISUAL_METADATA_ONLY'
        else:
            match=re.search(r'((?:19|20)\d{2})年?(?:年度报告|年报报告|年报)(?:全文)?(?:[（(](全文|修订版?|修订稿|更正稿|更正后|更正版|修正后|更新后|更新版|更新前|中文版|图文版|20\d{2}年(?:[1-9]|1[0-2])月修订版)[）)])?$',plain)
            if match:
                year=int(match[1]);edition=match[2] or 'INITIAL_OR_UNSPECIFIED'
                if year>2025:kind='OUTSIDE_FROZEN_FISCAL_SCOPE'
                elif edition=='更新前':kind='PRIOR_VERSION_FULL_REPORT_CANDIDATE'
                elif edition=='图文版':kind='ILLUSTRATED_FULL_REPORT_CANDIDATE'
                elif re.search('修订|更正|修正|更新',edition):kind='REVISED_FULL_REPORT_CANDIDATE'
                else:kind='FULL_ANNUAL_REPORT_CANDIDATE'
            elif re.search(r'(?:年度报告|年报)全文$',plain):kind='UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE';edition='UNSPECIFIED'
            else:kind='OTHER_ANNUAL_CATEGORY_TITLE_RETAINED'
        path=r.get('adjunctUrl')
        if 'CANDIDATE' in kind:need(type(path) is str and re.fullmatch('finalpage/'+re.escape(day)+'/'+re.escape(aid)+r'\.[pP][dD][fF]',path),'exact candidate original path/date/ID')
        result.append({'instrument':code,'title':title,'normalized_title':plain,'classification':kind,
            'fiscal_year':year,'edition':edition,'day':day,'timestamp_ms':r['announcementTime'],'announcement_id':aid,'pdf_path':path})
    return result,[r for r in result if 'CANDIDATE' in r['classification']]


def audit(base,repo,request,expected,run):
    need(sha(request)==expected,'frozen2026metadata request');req=read(request);before=inventory(run)
    cohort=read(repo/'experiments/qlib/asset-expansion-pre2026-request.json')['cohort']
    need(req['cohort']==cohort and len(cohort)==394 and cohort==sorted(set(cohort)),'same complete initial394cohort')
    orgs=read(base/'cninfo-csi500-reports-20261017/plan.json')['org_by_code'];inputs={request:expected}
    for group,parent in (('method_sha256',repo),('public_sha256',repo),('source_sha256',base)):
        for n,h in req[group].items():inputs[parent/n]=h
    for p,h in inputs.items():need(sha(p)==h,'input before '+str(p))
    terminal=read(run/'terminal.json');cases=read(run/'case_results.json');pending=[c for c in cohort if c not in cases]
    need(list(cases)==cohort[:len(cases)] and terminal['pending']==pending and terminal['completed_resources']==len(cases)
        and terminal['postcheck']['all_inputs_unchanged'] and not terminal['persistence_errors'],'immutable completed prefix and terminal identity')
    need(read(run/'input-before.json')=={str(p):h for p,h in inputs.items()},'exact source input bindings')
    statuses=Counter();classifications=Counter();fiscal=Counter();rows_checked=0;candidates=[];failures=[];source_artifacts={}
    for code in cases:
        resource={'method':'POST','url':'https://www.cninfo.com.cn/new/hisAnnouncement/query',
            'payload':{'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'',
                'stock':code[2:]+','+orgs[code],'searchkey':'','secid':'','category':'category_ndbg_szsh','trade':'',
                'seDate':START+'~'+END,'sortName':'','sortType':'','isHLtitle':'true'}}
        need(req['resources'][code]==resource,'independent resource identity/window')
        folder=run/'http'/digest({'resource':code,'identity':resource});q,res,record=(read(folder/n) for n in ('request.json','reservation.json','response.json'))
        need(q=={'resource':code,**resource} and res['resource']==code and res['identity_sha256']==digest(resource)
            and res['attempt']==1 and res['maximum_logical_attempts']==1,'one exact original query/reservation')
        need(record['resource']==code and record['identity_sha256']==digest(resource)
            and record['request_sha256']==sha(folder/'request.json') and record['reservation_sha256']==sha(folder/'reservation.json'),'response hash chain')
        case=cases[code];need(read(run/(code+'.json'))==case,'per-issuer case matches terminal collection');statuses[case['status']]+=1
        if case['status']=='METADATA_SOURCE_REJECTED':
            failures.append({'instrument':code,'error_type':case['error_type'],'error':case['error'],
                'HTTP_record_status':record['status'],'response_sha256':sha(folder/'response.json')});continue
        need(record['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and record['http_status']==200
            and record['body_complete'] is True and record['final_url']==resource['url'],'complete original same-endpoint HTTP200')
        body=folder/'body.bin';need(sha(body)==record['body_sha256'] and body.stat().st_size==record['body_bytes']<=1048576,'original metadata raw bytes')
        receipt=case['receipt'];need(receipt['folder']==str(folder.relative_to(run)) and receipt['record']==record
            and receipt['response_sha256']==sha(folder/'response.json'),'case source receipt binds complete original response')
        normalized,selected=normalize(code,json.loads(body.read_bytes()))
        need(normalized==case['all_normalized_rows'] and selected==case['full_report_candidates']
            and case['edition_selected_for_financial_values'] is False,'independent all-row title/edition/year/path classification')
        need(case['status']==('METADATA_CAPTURED_WITH_CANDIDATES' if selected else 'METADATA_CAPTURED_NO_FULL_CANDIDATE'),'source/no-candidate status')
        rows_checked+=len(normalized);classifications.update(r['classification'] for r in normalized);fiscal.update(str(r['fiscal_year']) for r in selected)
        candidates.extend(selected)
    reservations=list((run/'http').rglob('reservation.json'))
    need(len(reservations)==terminal['logical_attempts'] and len(reservations) in (len(cases),len(cases)+1),'actual prefix attempt accounting')
    if not pending:
        s=read(run/'summary.json');need(s['resource_count']==394 and s['status_counts']==dict(statuses)
            and s['full_report_candidates']==len(candidates) and s['candidate_fiscal_year_counts']==dict(fiscal)
            and s['all_inputs_unchanged'] and s['financial_numeric_values_decoded'] is False
            and s['2026_portfolio_returns_computed'] is False,'complete frozen source summary identity and limits')
    for p,h in inputs.items():need(sha(p)==h,'input after '+str(p))
    need(inventory(run)==before,'all raw HTTP/case bytes unchanged through QA')
    return {'status':'SEPARATE_2026_ANNUAL_METADATA_PREFIX_AND_SOURCE_BYTES_AUDITED_NOT_FINANCIAL_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':expected,'complete394_resources':len(cases)==394,
        'all_394_sources_accepted':len(cases)==394 and not failures,'original_terminal_error':terminal['original_error'],
        'resources_checked':len(cases),'HTTP_attempts':len(reservations),'pending':pending,'source_rejections':failures,
        'status_counts':dict(statuses),'original_rows_checked':rows_checked,'classification_counts':dict(classifications),
        'full_report_candidates':len(candidates),'candidate_fiscal_year_counts':dict(fiscal),
        'all_output_sha256':before,'all_original_inputs_unchanged':True,'no_production_imports':True,
        'same_researcher_separate_QA':True,'PDF_bytes_or_financial_values_read':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,
        '2026_portfolio_returns_computed':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.output);need(not out.exists(),'fresh external source QA output')
    result=audit(Path(a.source_root),Path(a.repo_root),Path(a.request).resolve(),a.expected_request_sha256,Path(a.run_dir))
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],'resources',result['resources_checked'],'candidates',result['full_report_candidates'],'rejections',len(result['source_rejections']))

if __name__=='__main__':main()
