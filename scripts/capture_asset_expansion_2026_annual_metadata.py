"""Initial394 cohort,2026 annual-category metadata only; no numeric/ROI reads."""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re
import time

from scripts.immutable_http_capture import ImmutableHttpCapture,file_sha,need,write_once

START,END='2026-01-01','2026-10-21'
OUTPUT='asset-expansion-2026-annual-metadata-20261022'
STATUS='FROZEN_ASSET_EXPANSION_2026_EXACT394_ANNUAL_METADATA'
PROTOCOL='docs/research/asset-expansion-2026-source-extension-plan-2026-10-22.md'
METHODS=('scripts/capture_asset_expansion_2026_annual_metadata.py','scripts/immutable_http_capture.py',
    'tests/test_asset_expansion_2026_metadata.py')
PUBLIC=('experiments/qlib/asset-expansion-pre2026-request.json',
    'experiments/qlib/asset-expansion-raw-development-request.json',
    'experiments/qlib/asset-expansion-raw-development-results.json',
    'experiments/qlib/asset-expansion-raw-account-audit.json',PROTOCOL)
ORG_PLAN='cninfo-csi500-reports-20261017/plan.json'


def read(p):return json.loads(Path(p).read_text())


def metadata_resource(code,org):
    need(re.fullmatch(r'(?:SH60|SZ00)\d{4}',code) and isinstance(org,str) and org,'fixed mainboard source identity')
    return {'method':'POST','url':'https://www.cninfo.com.cn/new/hisAnnouncement/query',
        'payload':{'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'',
            'stock':code[2:]+','+org,'searchkey':'','secid':'','category':'category_ndbg_szsh','trade':'',
            'seDate':START+'~'+END,'sortName':'','sortType':'','isHLtitle':'true'}}


def classify(title):
    clean=re.sub(r'[\s_《》]+','',re.sub(r'<[^>]+>','',title))
    if '摘要' in clean or re.search('abstract|summary',clean,re.I):return clean,'SUMMARY_METADATA_ONLY',None,None
    if '英文' in clean or re.search('annualreport',clean,re.I):return clean,'ENGLISH_METADATA_ONLY',None,None
    if '可视' in clean:return clean,'VISUAL_METADATA_ONLY',None,None
    edition=(r'全文|修订版?|修订稿|更正稿|更正后|更正版|修正后|更新后|更新版|更新前|中文版|图文版|20\d{2}年(?:[1-9]|1[0-2])月修订版')
    m=re.search(r'(?P<year>(?:19|20)\d{2})年?(?:年度报告|年报报告|年报)(?:全文)?(?:[（(](?P<edition>'+edition+r')[）)])?$',clean)
    if m is None:
        if re.search(r'(?:年度报告|年报)全文$',clean):return clean,'UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE',None,'UNSPECIFIED'
        return clean,'OTHER_ANNUAL_CATEGORY_TITLE_RETAINED',None,None
    year=int(m['year']);label=m['edition'] or 'INITIAL_OR_UNSPECIFIED'
    if year>2025:return clean,'OUTSIDE_FROZEN_FISCAL_SCOPE',year,label
    kind=('PRIOR_VERSION_FULL_REPORT_CANDIDATE' if label=='更新前' else
        'ILLUSTRATED_FULL_REPORT_CANDIDATE' if label=='图文版' else
        'REVISED_FULL_REPORT_CANDIDATE' if re.search('修订|更正|修正|更新',label) else 'FULL_ANNUAL_REPORT_CANDIDATE')
    return clean,kind,year,label


def select_rows(code,data):
    need(type(data) is dict and type(data.get('totalAnnouncement')) is int,'typed original metadata count')
    total=data['totalAnnouncement'];rows=data.get('announcements')
    if rows is None and total==0:rows=[]
    need(0<=total<=30 and type(rows) is list and len(rows)==total
        and (data.get('hasMore') is None or data.get('hasMore') is False),'one complete original30row page')
    normalized=[];candidates=[];seen=set()
    for row in rows:
        need(type(row) is dict and row['secCode']==code[2:] and type(row['announcementTime']) is int,'original issuer/timestamp')
        day=datetime.fromtimestamp(row['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
        need(START<=day<=END,'metadata beyond frozen2026 source window')
        identity=str(row['announcementId']);title=row['announcementTitle'];path=row.get('adjunctUrl')
        need(identity.isdigit() and identity not in seen and type(title) is str,'unique original announcement identity/title')
        seen.add(identity);clean,kind,year,edition=classify(title)
        if 'CANDIDATE' in kind:
            need(type(path) is str and re.fullmatch('finalpage/'+re.escape(day)+'/'+re.escape(identity)+r'\.[pP][dD][fF]',path),
                'candidate PDF must bind exact original date and identity')
        record={'instrument':code,'title':title,'normalized_title':clean,'classification':kind,
            'fiscal_year':year,'edition':edition,'day':day,'timestamp_ms':row['announcementTime'],
            'announcement_id':identity,'pdf_path':path}
        normalized.append(record)
        if 'CANDIDATE' in kind:candidates.append(record)
    return normalized,candidates


def verify(base,root,request,expected_sha):
    need(file_sha(request)==expected_sha,'frozen2026 metadata request')
    r=read(request);cohort=read(root/PUBLIC[0])['cohort'];orgs=read(base/ORG_PLAN)['org_by_code']
    need(r['status']==STATUS and r['cohort']==cohort and len(cohort)==394
        and cohort==sorted(set(cohort)) and r['output_subdir']==OUTPUT and r['window']==[START,END]
        and r['max_logical_attempts']==394 and r['per_resource_attempts']==1
        and r['max_body_bytes']==1048576 and r['timeout_seconds']==20
        and r['minimum_request_interval_seconds']==.2
        and r['PDF_download_permitted'] is False and r['financial_numeric_parsing_permitted'] is False
        and r['rank_or_portfolio_returns_permitted'] is False,'fixed394 metadata-only2026 protocol')
    need(r['resources']=={c:metadata_resource(c,orgs[c]) for c in cohort},'all exact issuer/window resources')
    need(set(r['method_sha256'])==set(METHODS) and set(r['public_sha256'])==set(PUBLIC)
        and set(r['source_sha256'])=={ORG_PLAN},'complete method/source binding groups')
    paths={request:expected_sha}
    for group,directory in (('method_sha256',root),('public_sha256',root),('source_sha256',base)):
        for name,h in r[group].items():paths[directory/name]=h
    for p,h in paths.items():need(file_sha(p)==h,'frozen input '+str(p))
    actual=read(root/PUBLIC[2]);qa=read(root/PUBLIC[3])
    need(actual['raw_daily_proxy_development_gate_passes'] is True
        and qa['raw_daily_proxy_development_gate_passes_independently'] is True
        and qa['summary_sha256']==file_sha(root/PUBLIC[2]) and all(qa['arithmetic_negative_controls_rejected'].values())
        and qa['2026_return_computed'] is False,'separate audited pre2026 lead before2026 resources')
    return r,paths


def capture(base,root,request,expected_sha,out,*,opener=None,pause=time.sleep):
    need(not out.exists() and out.resolve()==(base/OUTPUT).resolve(),'fixed fresh output,no retry/resume')
    r,bound=verify(base,root,request,expected_sha);out.mkdir(parents=True);results={};journal=None;primary=None;persistence=[]
    try:
        write_once(out/'input-before.json',{str(p):h for p,h in bound.items()})
        journal=ImmutableHttpCapture(out/'http',r['resources'],max_attempts=len(r['resources']),max_body_bytes=1048576,
            **({} if opener is None else {'opener':opener}))
        consecutive=0
        for code in r['cohort']:
            receipt=None
            try:
                receipt,body=journal.fetch(code);need(receipt['record']['http_status']==200,'annual metadata HTTP status not200')
                rows,candidates=select_rows(code,json.loads(body.read_bytes()))
                results[code]={'instrument':code,'status':'METADATA_CAPTURED_WITH_CANDIDATES' if candidates else 'METADATA_CAPTURED_NO_FULL_CANDIDATE',
                    'receipt':receipt,'all_normalized_rows':rows,'full_report_candidates':candidates,
                    'edition_selected_for_financial_values':False};consecutive=0
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                if getattr(exc,'capture_evidence_persistence_error',False):raise
                results[code]={'instrument':code,'status':'METADATA_SOURCE_REJECTED','receipt':receipt,
                    'error_type':type(exc).__name__,'error':str(exc)};consecutive+=1
            write_once(out/(code+'.json'),results[code]);print('2026annualmetadata',len(results),'/',len(r['cohort']),code,results[code]['status'],flush=True)
            if consecutive==3:raise ValueError('three consecutive rejections; remaining resources not attempted')
            pause(.2)
    except BaseException as exc:primary=exc
    finally:
        mismatches=[]
        for p,h in bound.items():
            try:
                if file_sha(p)!=h:mismatches.append({'input':str(p),'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':str(p),'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'input_count':len(bound),'mismatches':mismatches}
        terminal={'status':'ASSET_2026_METADATA_CAPTURE_TERMINAL','logical_attempts':journal.attempts if journal else 0,
            'completed_resources':len(results),'pending':[c for c in r['cohort'] if c not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence,'PDFs_downloaded':0,'portfolio_returns_computed':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence:primary.add_note('Terminal persistence errors: '+str(persistence))
        raise primary
    need(not mismatches and not persistence and len(results)==len(r['cohort']),'complete immutable metadata capture')
    summary={'status':'ALL394_2026_ANNUAL_METADATA_RESOURCES_PROCESSED_NOT_DATA_ADMITTED',
        'request_sha256':expected_sha,'window':[START,END],'resource_count':len(results),'logical_attempts':journal.attempts,
        'status_counts':dict(Counter(v['status'] for v in results.values())),
        'full_report_candidates':sum(len(v.get('full_report_candidates',[])) for v in results.values()),
        'candidate_fiscal_year_counts':dict(Counter(str(row['fiscal_year']) for v in results.values() for row in v.get('full_report_candidates',[]))),
        'multiple_candidate_issuers':[c for c,v in results.items() if len(v.get('full_report_candidates',[]))>1],
        'no_candidate_issuers':[c for c,v in results.items() if v['status']=='METADATA_CAPTURED_NO_FULL_CANDIDATE'],
        'input_count':len(bound),'all_inputs_unchanged':True,'PDFs_downloaded':0,'financial_numeric_values_decoded':False,
        'current_org_mapping_is_historical_master':False,'historical_arrival_verified':False,
        'financial_version_history_complete':False,'investment_factor_admitted':False,
        '2026_portfolio_returns_computed':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);root=Path(__file__).resolve().parents[1]
    result=capture(base,root,Path(a.request).resolve(),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['status_counts'],flush=True)
    return 2 if result['status_counts'].get('METADATA_SOURCE_REJECTED',0) else 0


if __name__=='__main__':raise SystemExit(main())
