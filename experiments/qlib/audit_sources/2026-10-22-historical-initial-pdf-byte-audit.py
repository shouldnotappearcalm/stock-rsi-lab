"""Reconstruct408 source definitions/byte journals; no PDF content or finance QA."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def need(v,why):
    if not v: raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def title_match(title):
    normalized=re.sub(r'[\s_《》]+','',re.sub(r'<[^>]+>','',title))
    return (not any(t in normalized for t in ('摘要','英文','可视')) and re.search(
        r'2022年?(?:年度报告|年报)(?:全文|[（(](?:全文|修订版?|修订稿|更正稿|更正后|更正版|更新后|更新版|中文版)[）)])?$',normalized) is not None)


def main():
    parser=argparse.ArgumentParser()
    for n in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+n,required=True)
    a=parser.parse_args();root,base,membership,request,run,out=map(lambda p:Path(p).resolve(),
        (a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external report')
    need(sha(request)==a.expected_request_sha256,'frozen PDF source request');req=read(request)
    need(req['status']=='FROZEN_BEFORE_HISTORICAL394_INITIAL2022_PDF_CAPTURE' and req['document_count']==408
         and req['max_logical_attempts']==396 and req['per_resource_attempts']==1 and req['cache_reuse_count']==12
         and req['max_body_bytes']==67108864 and req['financial_numeric_parsing_permitted'] is False
         and req['ranking_or_portfolio_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'exact408 source-only byte scope')
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
    need(len(paths)==2433,'complete2433 frozen inputs')
    for key,p in paths.items():need(sha(p)==expected[key],'unchanged input before audit: '+key)
    source_meta=base/'gross-profitability-historical394-annual-metadata-20261022'
    metadata=read(source_meta/'case_results.json')
    olddocs=read(base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json')
    source_rows=[(d['instrument'],d,'AUTHENTICATED_FIXED12_INITIAL_RECORD',base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json',d)
                 for d in olddocs if d['fiscal_year']==2022]
    for key,case in metadata.items():
        if case['fiscal_year']==2022:
            for row in case['all_normalized_rows']:
                if title_match(row['title']):source_rows.append((case['instrument'],row,'SOURCE_BACKED_EXPLICIT_YEAR_TITLE_ALIASES',source_meta/(key+'.json'),None))
    rebuilt,identities=[],set()
    for code,row,origin,packet,cache in source_rows:
        identity=row['announcement_id'];need(identity not in identities and title_match(row['title'])
            and '2023-01-01'<=row['day']<='2023-12-31' and re.fullmatch(
            r'finalpage/\d{4}-\d{2}-\d{2}/'+re.escape(identity)+r'\.[pP][dD][fF]',row['pdf_path']),'unique explicit2022 original title/path/publication')
        identities.add(identity)
        d={k:row[k] for k in ('title','day','timestamp_ms','announcement_id','pdf_path')}
        d.update(instrument=code,fiscal_year=2022,url='https://static.cninfo.com.cn/'+row['pdf_path'],capture_key=code+'-2022-'+identity,
            metadata_origin=origin,metadata_source_artifact_sha256=sha(packet),
            original_candidate_classification=row.get('classification','PRIOR_AUTHENTICATED_SOURCE_RECORD'))
        if cache:
            d.update(source_kind='REUSE_AUTHENTICATED_ORIGINAL_PDF',source_path=cache['source_path'],
                source_sha256=cache['source_sha256'],captured_at_utc=cache['captured_at_utc'])
        else:d['source_kind']='FRESH_FROZEN_PDF_GET'
        rebuilt.append(d)
    need(rebuilt==req['documents'] and len(rebuilt)==408 and len({d['instrument'] for d in rebuilt})==391,
         'all408 source candidates and391 issuers reconstructed without edition choice')
    cohort=read(root/'experiments/qlib/profitability-historical394-source-inventory.json')['dated_cohort']
    gaps=[c for c in cohort if c not in {d['instrument'] for d in rebuilt}]
    need(gaps==req['remaining_gap_issuers']==['SH600925','SH601061','SZ001286'],'all residual initial source gaps retained')
    expected_resources={d['capture_key']:{'method':'GET','url':d['url'],'payload':None} for d in rebuilt if d['source_kind']=='FRESH_FROZEN_PDF_GET'}
    need(req['resources']==expected_resources and len(expected_resources)==396,'exact396 original GETs')
    outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    cases,summary,terminal=map(lambda n:read(run/n),('case_results.json','summary.json','terminal.json'))
    need(set(cases)=={d['capture_key'] for d in rebuilt},'all408 source packets')
    allowed={'input-before.json','input-postcheck.json','case_results.json','terminal.json','summary.json','documents.json'}
    records,valid,fresh_bytes,reused,rejected=[],0,0,0,0
    for d in rebuilt:
        key=d['capture_key'];allowed.add(key+'.json');case=cases[key]
        if d['source_kind']=='REUSE_AUTHENTICATED_ORIGINAL_PDF':
            need(sha(base/d['source_path'])==d['source_sha256'],'unchanged cached PDF bytes')
            record={**d,'status':'ORIGINAL_PDF_BYTES_REUSED_IDENTITY_REVIEW_SEPARATE'};reused+=1
        else:
            resource=expected_resources[key];h=digest({'resource':key,'identity':resource});folder=run/'http'/h
            names={p.name for p in folder.iterdir()};need(names in ({'request.json','reservation.json','response.json'},
                {'request.json','reservation.json','response.json','body.bin'}),'only registered source HTTP files')
            allowed|={'http/'+h+'/'+n for n in names}
            need(read(folder/'request.json')=={'resource':key,**resource},'exact original PDF GET')
            reservation=read(folder/'reservation.json');response=read(folder/'response.json')
            need(reservation['resource']==key and reservation['attempt']==reservation['maximum_logical_attempts']==1
                 and reservation['identity_sha256']==digest(resource),'one reserved logical attempt')
            need(response['resource']==key and response['identity_sha256']==digest(resource)
                 and response['request_sha256']==sha(folder/'request.json') and response['reservation_sha256']==sha(folder/'reservation.json'),
                 'raw source reservation/response chain')
            good=False
            if 'body.bin' in names:
                need(response['body_sha256']==sha(folder/'body.bin') and response['body_bytes']==(folder/'body.bin').stat().st_size,'exact original body bytes')
                with (folder/'body.bin').open('rb') as stream:magic=stream.read(5)
                good=(response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and response['http_status']==200
                      and response['body_complete'] is True and 1000<=response['body_bytes']<=67108864 and magic==b'%PDF-')
            if good:
                receipt={'folder':'http/'+h,'record':response,'response_sha256':sha(folder/'response.json')}
                record={**d,'status':'PDF_MAGIC_CAPTURED_NUMERIC_IDENTITY_REVIEW_PENDING','receipt':receipt,
                    'source_path':str((folder/'body.bin').relative_to(base)),'source_sha256':sha(folder/'body.bin'),
                    'captured_at_utc':response['captured_at_utc']}
                fresh_bytes+=response['body_bytes'];valid+=1
            else:
                need(case['status']=='PDF_SOURCE_REJECTED' and all(case[k]==v for k,v in d.items())
                     and case['error_type'] and case['error'],'source rejection retained without substituted PDF')
                record=case;rejected+=1
        need(record==case==read(run/(key+'.json'))==summary['results_by_document'][key],'source records/packets reconstructed')
        records.append(record)
    need(set(outputs)==allowed and read(run/'documents.json')==records,'exact registered output set and source order')
    need(reused==12 and valid+rejected==396 and summary['documents_recorded']==408 and summary['logical_attempts']==396
         and summary['cached_reused']==12 and summary['rejected_documents']==rejected and summary['input_count']==2433
         and summary['all_inputs_unchanged'] is True and summary['financial_numeric_values_decoded'] is False
         and summary['investment_factor_admitted'] is False and summary['objective_achieved'] is False,'complete source byte summary')
    need(summary['status']==('HISTORICAL_INITIAL2022_PDF_BYTES_CAPTURED_REVIEW_PENDING' if not rejected else 'HISTORICAL_INITIAL2022_PDF_CAPTURE_INCOMPLETE'),
         'byte success/rejection status remains distinct from admission')
    post={'all_inputs_unchanged':True,'count':2433,'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json')==expected and read(run/'input-postcheck.json')==post
         and terminal['logical_attempts']==396 and terminal['completed_documents']==408 and terminal['pending']==[]
         and terminal['original_error'] is None and terminal['postcheck']==post and terminal['persistence_errors']==[],'complete terminal/input journals')
    for key,p in paths.items():need(sha(p)==expected[key],'unchanged input after byte audit: '+key)
    need(outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'all captured output bytes unchanged')
    report={'status':'PASS_408_ORIGINAL_PDF_BYTE_RECORD_RECONSTRUCTION_CONTENT_NOT_ADMITTED','audit_code_sha256':sha(__file__),
        'request_sha256':a.expected_request_sha256,'all2433_input_sha256':expected,'all_output_sha256':outputs,
        'source_document_records':records,'source_candidates':408,'source_issuers':391,'remaining_gap_issuers':gaps,
        'logical_GET_attempts':396,'new_PDF_magic_bodies':valid,'rejected_PDF_resources':rejected,'cached_originals_reused':12,
        'fresh_PDF_bytes':fresh_bytes,'output_files':len(outputs),'production_modules_imported':False,
        'authored_after_capture_started_same_researcher_not_blinded':True,'PDF_text_or_financial_values_decoded':False,
        'issuer_fiscal_and_accounting_content_verified':False,'financial_version_history_complete':False,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'portfolio_returns_computed':False,
        '2026_financial_or_market_values_decoded':False,'objective_achieved':False}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(report['status'],sha(out),valid,rejected,fresh_bytes)


if __name__=='__main__':main()
