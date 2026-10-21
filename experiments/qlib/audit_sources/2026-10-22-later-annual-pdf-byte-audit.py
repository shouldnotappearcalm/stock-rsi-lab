"""Separate reconstruction of later annual candidates and exact byte journals.
No production imports or PDF text decoding. Same researcher, after run started.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def need(value,why):
    if not value:raise AssertionError(why)
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def classify(title):
    text=re.sub(r'[\s_《》]+','',re.sub(r'<[^>]+>','',title))
    if '摘要' in text or re.search('abstract|summary',text,re.I):return {'kind':'SUMMARY_METADATA_ONLY','fiscal_year':None}
    if '英文' in text or re.search('annualreport',text,re.I):return {'kind':'ENGLISH_METADATA_ONLY','fiscal_year':None}
    if '可视' in text:return {'kind':'VISUAL_METADATA_ONLY','fiscal_year':None}
    if text=='年报全文':return {'kind':'UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE','fiscal_year':None,'edition':'UNSPECIFIED'}
    suffix=r'全文|修订版?|修订稿|更正稿|更正后|更正版|修正后|更新后|更新版|更新前|中文版|图文版|20\d{2}年(?:[1-9]|1[0-2])月修订版'
    match=re.search(r'((?:19|20)\d{2})年?(?:年度报告|年报报告|年报)(?:全文)?(?:[（(]('+suffix+r')[）)])?$',text)
    if match is None:return {'kind':'OTHER_ANNUAL_CATEGORY_TITLE_RETAINED','fiscal_year':None}
    year=int(match.group(1))
    if year>2024:return {'kind':'OUTSIDE_PRE2026_FISCAL_SCOPE','fiscal_year':year}
    edition=match.group(2) or 'INITIAL_OR_UNSPECIFIED'
    kind='FULL_ANNUAL_REPORT_CANDIDATE'
    if edition=='更新前':kind='PRIOR_VERSION_FULL_REPORT_CANDIDATE'
    elif edition=='图文版':kind='ILLUSTRATED_FULL_REPORT_CANDIDATE'
    elif re.search('修订|更正|修正|更新',edition):kind='REVISED_FULL_REPORT_CANDIDATE'
    return {'kind':kind,'fiscal_year':year,'edition':edition}


def main():
    parser=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();root,base,membership,request,run,out=map(lambda p:Path(p).resolve(),
        (a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external audit output')
    need(sha(request)==a.expected_request_sha256,'frozen later candidate request')
    req=read(request)
    need(req['status']=='FROZEN_BEFORE_HISTORICAL394_ALL_LATER_ANNUAL_CANDIDATE_PDF_BYTES'
         and req['document_count']==828 and req['max_logical_attempts']==804 and req['cache_reuse_count']==24
         and req['per_resource_attempts']==1 and req['max_body_bytes']==67108864 and req['timeout_seconds']==20
         and req['minimum_request_interval_seconds']==0.2 and req['PDF_text_or_financial_numeric_parsing_permitted'] is False
         and req['ranking_or_portfolio_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,
         'exact828 candidate bytes-only source scope')
    old=base/'cninfo-csi500-reports-20261017';fixed=base/'gross-profitability-fixed12-annual-pdfs-20261022'
    cached=read(fixed/'documents.json');cached_by_id={d['announcement_id']:d for d in cached};cached_by_key={d['capture_key']:d for d in cached}
    special={'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
        'PDF_document_records':fixed/'documents.json','inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    paths={'frozen_source_request':request};expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    for key in req['input_sha256']:
        prefix,name=key.split('/',1);need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe bound input path')
        if prefix=='repo':path=root/name
        elif prefix=='source':path=base/name
        else:
            need(prefix=='catalog','known source catalog')
            if name in special:path=special[name]
            elif name.startswith('metadata/'):path=old/'codes'/(name.split('/',1)[1]+'.json')
            else:
                need(name.startswith('PDF/') and name[4:] in cached_by_key,'known cached source alias')
                path=base/cached_by_key[name[4:]]['source_path']
        paths[key]=path
    need(len(paths)==2711,'complete2711 source bindings')
    for key,path in paths.items():need(sha(path)==expected[key],'unchanged input before: '+key)
    cohort=read(root/'experiments/qlib/profitability-historical394-source-inventory.json')['dated_cohort']
    actual_cohort=sorted({c for c,s,e in (line.split() for line in membership.read_text().splitlines()) if s<='2024-01-02'<=e and c.startswith(('SH60','SZ00'))})
    need(actual_cohort==cohort and len(cohort)==394,'dated source range, not current lookup membership')
    rows=[]
    for code in cohort:
        path=old/'codes'/(code+'.json');packet=read(path)
        need(packet['code']==code and packet['query_window']==['2024-01-01','2025-12-31'],'original later metadata publication window')
        for row in packet['reports']['annual']:
            need(row['code']==code[2:],'original issuer code')
            rows.append((code,row,{'path':str(path.relative_to(base)),'sha256':sha(path)}))
    folder=base/'gross-profitability-historical394-annual-metadata-20261022'
    for key,case in read(folder/'case_results.json').items():
        if case['fiscal_year'] in (2023,2024):
            path=folder/(key+'.json')
            for row in case['all_normalized_rows']:rows.append((case['instrument'],row,{'path':str(path.relative_to(base)),'sha256':sha(path)}))
    grouped,seen,unselected={}, {}, {}
    for code,row,reference in rows:
        identity=row['announcement_id'];core={k:row[k] for k in ('title','day','timestamp_ms','announcement_id','pdf_path')};signature={'instrument':code,**core}
        need(identity not in seen or seen[identity]==signature,'no metadata conflict hidden by duplicate ID')
        seen[identity]=signature;label=classify(core['title'])
        if 'CANDIDATE' not in label['kind']:unselected[identity]={**signature,**label};continue
        year=label['fiscal_year'];day=datetime.fromtimestamp(core['timestamp_ms']/1000,timezone(timedelta(hours=8))).date().isoformat()
        need(day==core['day'] and '2024-01-01'<=day<='2025-12-31' and (year is None or year<int(day[:4]))
             and re.fullmatch(r'finalpage/'+re.escape(day)+'/'+re.escape(identity)+r'\.[pP][dD][fF]',core['pdf_path']),'original path/day/year identity')
        if identity not in grouped:
            d={**core,'instrument':code,'fiscal_year':year,
               'fiscal_year_basis':'EXPLICIT_TITLE_PENDING_COVER_CONFIRMATION' if year is not None else 'UNSPECIFIED_TITLE_COVER_REVIEW_REQUIRED',
               'edition_role':label['kind'],'edition_label':label['edition'],
               'capture_key':code+'-'+(str(year) if year is not None else 'UNKNOWN')+'-'+identity,
               'url':'https://static.cninfo.com.cn/'+core['pdf_path'],'metadata_source_refs':[]}
            cache=cached_by_id.get(identity)
            if cache:
                need(cache['instrument']==code and cache['fiscal_year']==year and all(cache[k]==core[k] for k in core),'reused original metadata identity')
                d.update(source_kind='REUSE_AUTHENTICATED_ORIGINAL_PDF',source_path=cache['source_path'],source_sha256=cache['source_sha256'],captured_at_utc=cache['captured_at_utc'])
            else:d['source_kind']='FRESH_FROZEN_PDF_GET'
            grouped[identity]=d
        if reference not in grouped[identity]['metadata_source_refs']:grouped[identity]['metadata_source_refs'].append(reference)
    documents=sorted(grouped.values(),key=lambda d:(d['instrument'],d['fiscal_year'] or 9999,d['day'],d['announcement_id']))
    need(documents==req['documents'] and len(documents)==828 and len({d['instrument'] for d in documents})==394,'all828 source candidate definitions reconstructed')
    gaps={str(y):[c for c in cohort if not any(d['instrument']==c and d['fiscal_year']==y for d in documents)] for y in (2023,2024)}
    inventory={'source_row_occurrences':len(rows),'unique_source_announcements':len(seen),
        'selected_candidate_documents':len(documents),'selected_candidate_issuers':len({d['instrument'] for d in documents}),
        'candidate_counts_by_literal_fiscal_year':dict(Counter(str(d['fiscal_year']) for d in documents)),
        'candidate_counts_by_edition_role':dict(Counter(d['edition_role'] for d in documents)),
        'missing_explicit_fiscal_year_candidates_by_issuer':gaps,
        'yearless_source_candidates':[d['capture_key'] for d in documents if d['fiscal_year'] is None],
        'unselected_unique_title_counts':dict(Counter(d['kind'] for d in unselected.values())),
        'other_annual_category_titles_retained':[d for d in unselected.values() if d['kind']=='OTHER_ANNUAL_CATEGORY_TITLE_RETAINED'],
        'source_candidate_count_is_not_financial_content_coverage':True}
    need(inventory==req['source_inventory'] and gaps=={'2023':[],'2024':['SH601106','SH603737','SZ002505']}
         and inventory['yearless_source_candidates']==['SH601106-UNKNOWN-1223415420'],'source range gaps and yearless status, no fiscal inference')
    resources={d['capture_key']:{'method':'GET','url':d['url'],'payload':None} for d in documents if d['source_kind']=='FRESH_FROZEN_PDF_GET'}
    need(resources==req['resources'] and len(resources)==804,'exact804 registered GETs')
    outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    cases,summary,terminal=(read(run/name) for name in ('case_results.json','summary.json','terminal.json'))
    need(set(cases)=={d['capture_key'] for d in documents},'complete828 candidate records')
    allowed={'input-before.json','input-postcheck.json','case_results.json','terminal.json','summary.json','documents.json'}
    records,reused,good,fresh_bytes,rejected=[],0,0,0,0
    for d in documents:
        key=d['capture_key'];case=cases[key];allowed.add(key+'.json')
        if d['source_kind']=='REUSE_AUTHENTICATED_ORIGINAL_PDF':
            need(sha(base/d['source_path'])==d['source_sha256'],'original cached body unchanged')
            record={**d,'status':'ORIGINAL_PDF_BYTES_REUSED_CONTENT_REVIEW_SEPARATE'};reused+=1
        else:
            identity=resources[key];h=digest({'resource':key,'identity':identity});folder=run/'http'/h;names={p.name for p in folder.iterdir()}
            need(names in ({'request.json','reservation.json','response.json','body.bin'},{'request.json','reservation.json','response.json'}),'only registered raw source files')
            allowed|={'http/'+h+'/'+n for n in names}
            need(read(folder/'request.json')=={'resource':key,**identity},'exact official GET request')
            reserve,response=read(folder/'reservation.json'),read(folder/'response.json')
            need(reserve['resource']==key and reserve['attempt']==reserve['maximum_logical_attempts']==1 and reserve['identity_sha256']==digest(identity),'one logical attempt only')
            need(response['resource']==key and response['identity_sha256']==digest(identity)
                 and response['request_sha256']==sha(folder/'request.json') and response['reservation_sha256']==sha(folder/'reservation.json'),'immutable raw response chain')
            valid=False
            if 'body.bin' in names:
                body=folder/'body.bin';need(response['body_sha256']==sha(body) and response['body_bytes']==body.stat().st_size,'complete captured body identity')
                with body.open('rb') as stream:magic=stream.read(5)
                target=urlsplit(response.get('final_url',''))
                valid=(response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and response['http_status']==200
                    and response['body_complete'] is True and 1000<=response['body_bytes']<=67108864 and magic==b'%PDF-'
                    and target.scheme=='https' and target.hostname=='static.cninfo.com.cn')
                if valid and response['content_length_header'] is not None:need(int(response['content_length_header'])==response['body_bytes'],'declared body length')
            if valid:
                receipt={'folder':'http/'+h,'record':response,'response_sha256':sha(folder/'response.json')}
                record={**d,'status':'PDF_MAGIC_CAPTURED_CONTENT_REVIEW_PENDING','receipt':receipt,
                    'source_path':str((folder/'body.bin').relative_to(base)),'source_sha256':sha(folder/'body.bin'),'captured_at_utc':response['captured_at_utc']}
                good+=1;fresh_bytes+=response['body_bytes']
            else:
                need(case['status']=='PDF_SOURCE_REJECTED' and all(case[k]==v for k,v in d.items()) and case['error_type'] and case['error'],'original source rejection retained')
                record=case;rejected+=1
        need(record==case==read(run/(key+'.json'))==summary['results_by_document'][key],'source/case/summary conservation')
        records.append(record)
    need(set(outputs)==allowed and read(run/'documents.json')==records and reused==24 and good+rejected==804,'exact source outputs/cache/GET conservation')
    need(summary['documents_recorded']==828 and summary['source_issuers']==394 and summary['logical_GET_attempts']==804
         and summary['cached_originals_reused']==24 and summary['rejected_documents']==rejected and summary['source_inventory']==inventory,
         'actual source capture summary')
    need(summary['status']==('LATER_ANNUAL_CANDIDATE_PDF_BYTES_CAPTURED_CONTENT_REVIEW_PENDING' if not rejected else 'LATER_ANNUAL_PDF_CAPTURE_WITH_SOURCE_REJECTIONS'),'byte completeness is not financial admission')
    for flag in ('PDF_text_or_financial_values_decoded','issuer_fiscal_and_accounting_content_verified','financial_version_history_complete',
                 'historical_arrival_verified','investment_factor_admitted','security_ranking_or_portfolio_returns_computed','2026_financial_or_market_values_read','objective_achieved'):
        need(summary[flag] is False,'no unearned source or economic claim')
    post={'all_inputs_unchanged':True,'count':2711,'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json')==expected and read(run/'input-postcheck.json')==post and terminal['postcheck']==post
         and terminal['logical_attempts']==804 and terminal['completed_documents']==828 and terminal['pending']==[]
         and terminal['original_error'] is None and terminal['persistence_errors']==[],'complete source terminal/input journals')
    for key,path in paths.items():need(sha(path)==expected[key],'unchanged input after: '+key)
    need(outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'source output bytes unchanged')
    report={'status':'PASS_SEPARATE_LATER828_CANDIDATE_AND_SINGLE_GET_BYTE_AUDIT_NOT_FINANCIAL_ADMISSION',
        'audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,'all_input_sha256':expected,'all_output_sha256':outputs,
        'source_document_records':records,'source_inventory':inventory,'logical_GET_attempts':804,'new_PDF_magic_bodies':good,
        'cached_originals_reused':reused,'rejected_sources':rejected,'fresh_PDF_bytes':fresh_bytes,'output_files':len(outputs),
        'production_modules_imported':False,'authored_after_capture_started_same_researcher_not_blinded':True,
        'PDF_text_or_financial_values_decoded':False,'issuer_fiscal_and_accounting_content_verified':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    with out.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(report['status'],sha(out),good,reused,rejected,fresh_bytes,flush=True)


if __name__=='__main__':main()
