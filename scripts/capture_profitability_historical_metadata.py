"""Exactly395 registered annual metadata reads, no PDF/financial values or ROI."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time

from scripts.immutable_http_capture import ImmutableHttpCapture, need, file_sha, write_once

CATALOG = 'experiments/qlib/profitability-historical394-source-inventory.json'
CATALOG_CODE = 'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'
OLD = 'cninfo-csi500-reports-20261017'
LOCAL_CATALOG = 'gross-profitability-historical394-source-inventory-v2-20261022'
DOCS = 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json'
OUTPUT = 'gross-profitability-historical394-annual-metadata-20261022'
STATUS = 'FROZEN_BEFORE_HISTORICAL394_EXACT395_ANNUAL_METADATA_READS'
METHODS = ('scripts/immutable_http_capture.py', 'scripts/capture_profitability_historical_metadata.py')
PUBLIC = (CATALOG, CATALOG_CODE, 'experiments/qlib/profitability-historical394-inventory-semantics-note.json',
          'docs/research/profitability-historical394-metadata-plan-2026-10-22.md',
          'tests/test_profitability_historical_metadata_capture.py')


def read(p): return json.loads(Path(p).read_text())


def metadata_resource(code, org, fiscal_year):
    year = fiscal_year + 1
    need(fiscal_year in (2022, 2023, 2024), 'pre2026 report years only')
    return {'method': 'POST', 'url': 'https://www.cninfo.com.cn/new/hisAnnouncement/query',
        'payload': {'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'',
        'stock':code[2:]+','+org,'searchkey':'','secid':'','category':'category_ndbg_szsh',
        'trade':'','seDate':f'{year}-01-01~{year}-12-31','sortName':'','sortType':'','isHLtitle':'true'}}


def select_rows(code, fiscal_year, data):
    need(type(data) is dict and type(data.get('totalAnnouncement')) is int, 'original metadata count required')
    total, rows = data['totalAnnouncement'], data.get('announcements') or []
    need(0 <= total <= 30 and type(rows) is list and len(rows) == total
         and data.get('hasMore') in (None,False), 'one complete30-row metadata page required')
    year = fiscal_year + 1
    need(fiscal_year in (2022,2023,2024), 'pre2026 fiscal scope')
    normalized, selected, seen = [], [], set()
    for row in rows:
        need(type(row) is dict and row['secCode'] == code[2:] and type(row['announcementTime']) is int,
             'original issuer/timestamp required')
        day = datetime.fromtimestamp(row['announcementTime']/1000, timezone(timedelta(hours=8))).date().isoformat()
        need(f'{year}-01-01' <= day <= f'{year}-12-31', 'outside frozen publication-year window')
        identity, title, path = str(row['announcementId']), row['announcementTitle'], row.get('adjunctUrl')
        need(identity.isdigit() and identity not in seen and type(title) is str, 'unique original announcement identity')
        seen.add(identity)
        clean = re.sub(r'\s+','',re.sub(r'<[^>]+>','',title))
        kind = 'OTHER_ANNUAL_CATEGORY_NOTICE'
        if '摘要' in clean: kind = 'SUMMARY'
        elif '英文' in clean: kind = 'ENGLISH_EDITION'
        elif '可视' in clean: kind = 'VISUAL_EDITION'
        elif re.search(str(fiscal_year)+r'年?年度报告(?:全文|[（(](?:全文|修订版?|修订稿|更正稿|更正后|更新后|更新版|中文版)[）)])?$',clean):
            kind = 'FULL_ANNUAL_REPORT_CANDIDATE'
            need(type(path) is str and re.fullmatch(r'finalpage/\d{4}-\d{2}-\d{2}/'+re.escape(identity)+r'\.[pP][dD][fF]',path),
                 'safe original full-report PDF path required')
        record = {'instrument':code,'requested_fiscal_year':fiscal_year,'fiscal_year':fiscal_year if kind=='FULL_ANNUAL_REPORT_CANDIDATE' else None,
            'title':title,'normalized_title':clean,'day':day,'timestamp_ms':row['announcementTime'],
            'announcement_id':identity,'pdf_path':path,'classification':kind}
        if kind == 'FULL_ANNUAL_REPORT_CANDIDATE':
            record['edition_role'] = 'EXPLICIT_REVISED_EDITION' if re.search(r'修订|更正|更新',clean) else 'INITIAL_OR_UNSPECIFIED_EDITION'
            selected.append(record)
        normalized.append(record)
    return normalized, selected


def catalog_input_paths(base, root, membership):
    paths = {'membership_intervals':membership,'metadata_manifest':base/OLD/'manifest.json',
        'metadata_plan':base/OLD/'plan.json','PDF_document_records':base/DOCS,'inventory_code':root/CATALOG_CODE}
    for d in read(base/DOCS):
        need(not Path(d['source_path']).is_absolute() and '..' not in Path(d['source_path']).parts, 'safe cached source path')
        paths['PDF/'+d['capture_key']] = base/d['source_path']
    for code in read(root/CATALOG)['dated_cohort']:
        need(re.fullmatch(r'(?:SH60|SZ00)\d{4}',code), 'mainboard instrument identity')
        paths['metadata/'+code] = base/OLD/'codes'/(code+'.json')
    return paths


def required_paths(base, root, membership):
    paths = {'catalog/'+k:p for k,p in catalog_input_paths(base,root,membership).items()}
    for name in (*METHODS,*PUBLIC): paths['repo/'+name] = root/name
    for name in ('summary.json','case_results.json'): paths['source/'+LOCAL_CATALOG+'/'+name] = base/LOCAL_CATALOG/name
    return paths


def check(paths, expected):
    need(set(paths)==set(expected),'complete source/method bindings required')
    for key,path in paths.items(): need(file_sha(path)==expected[key],'bound input changed: '+key)


def specifications(base, root, membership):
    catalog = read(root/CATALOG)
    need(catalog['status']=='HISTORICAL394_PREFIX_AWARE_SOURCE_CATALOG_NOT_INVESTMENT_UNIVERSE_ADMISSION'
         and catalog['as_of']=='2024-01-02' and catalog['mainboard_cohort_count']==394
         and catalog['initial2022_metadata_still_needed']==382,'original dated source catalog required')
    check(catalog_input_paths(base,root,membership),catalog['all_input_sha256'])
    need(file_sha(base/LOCAL_CATALOG/'summary.json')==file_sha(root/CATALOG)
         and file_sha(base/LOCAL_CATALOG/'case_results.json')==catalog['case_results_sha256'],'actual source catalog identity')
    cohort = sorted({c for c,s,e in (line.split() for line in membership.read_text().splitlines())
                     if s<='2024-01-02'<=e and c.startswith(('SH60','SZ00'))})
    need(cohort==catalog['dated_cohort'],'historical membership, not lookup addresses, determines source scope')
    cases = read(base/LOCAL_CATALOG/'case_results.json')
    need(set(cases)==set(cohort),'complete394 issuer catalog')
    specs = [{'resource_key':c+'-2022','instrument':c,'fiscal_year':2022,'reason':'MISSING_INITIAL2022_METADATA'}
             for c in cohort if cases[c]['2022']['status']=='INITIAL2022_METADATA_NOT_CAPTURED']
    need(len(specs)==382,'exact missing382 initial filings')
    repairs = [{'resource_key':c+'-'+str(y),'instrument':c,'fiscal_year':y,'reason':cases[c][str(y)]['status']}
               for y in (2023,2024) for c in cohort if cases[c][str(y)]['status']!='ONE_FULL_REPORT_METADATA_CANDIDATE']
    need(len(repairs)==13 and sum(s['reason']=='MULTIPLE_FULL_REPORT_METADATA_CANDIDATES' for s in repairs)==7,
         'all seven ambiguous and six no-literal-match cells retained')
    return specs+repairs


def verify(base, root, membership, request_file, expected_sha):
    need(file_sha(request_file)==expected_sha,'frozen historical metadata request changed')
    req=read(request_file);specs=specifications(base,root,membership);orgs=read(base/OLD/'plan.json')['org_by_code']
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['specifications']==specs
         and req['max_logical_attempts']==395 and req['per_resource_attempts']==1 and req['page_cap']==1
         and req['max_body_bytes']==1048576 and req['timeout_seconds']==20
         and req['minimum_request_interval_seconds']==0.2 and req['PDF_download_permitted'] is False
         and req['financial_numeric_parsing_permitted'] is False and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'fixed395 metadata-only resources required')
    need(req['resources']=={s['resource_key']:metadata_resource(s['instrument'],orgs[s['instrument']],s['fiscal_year']) for s in specs}
         and set(req['method_sha256'])==set(METHODS),'exact official resource addressing and methods')
    paths=required_paths(base,root,membership);check(paths,req['input_sha256'])
    for name,h in req['method_sha256'].items(): need(h==req['input_sha256']['repo/'+name],'method/input identities agree')
    return req,paths


def capture(base, root, membership, request_file, expected_sha, out, *, opener=None, pause=time.sleep):
    need(out.resolve()==(base/OUTPUT).resolve() and not out.exists(),'fixed fresh output only; no retry/resume')
    req,paths=verify(base,root,membership,request_file,expected_sha)
    paths={**paths,'frozen_source_request':Path(request_file)};expected={**req['input_sha256'],'frozen_source_request':expected_sha}
    check(paths,expected);out.mkdir(parents=True)
    results,primary,mismatches,persistence_errors,journal={},None,[],[],None
    keys=[s['resource_key'] for s in req['specifications']]
    try:
        write_once(out/'input-before.json',expected)
        journal=ImmutableHttpCapture(out/'http',req['resources'],max_attempts=len(keys),max_body_bytes=1048576,
                                     **({} if opener is None else {'opener':opener}))
        consecutive=0
        for spec in req['specifications']:
            key=spec['resource_key'];receipt=None
            try:
                receipt,body=journal.fetch(key)
                need(receipt['record']['http_status']==200,'official metadata HTTP status not200')
                rows,candidates=select_rows(spec['instrument'],spec['fiscal_year'],json.loads(body.read_bytes()))
                results[key]={**spec,'status':'METADATA_CAPTURED_WITH_FULL_REPORT_CANDIDATES' if candidates else 'METADATA_CAPTURED_NO_LITERAL_FULL_REPORT_CANDIDATE',
                    'receipt':receipt,'all_normalized_rows':rows,'full_report_candidates':candidates,
                    'edition_selected_for_financial_values':False}
                consecutive=0
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                if getattr(exc,'capture_evidence_persistence_error',False): raise
                results[key]={**spec,'status':'METADATA_SOURCE_REJECTED','receipt':receipt,
                              'error_type':type(exc).__name__,'error':str(exc)}
                consecutive+=1
            write_once(out/(key+'.json'),results[key])
            print('historical annual metadata',key,results[key]['status'],flush=True)
            if consecutive==3: raise ValueError('three consecutive source rejections; remaining resources not attempted')
            pause(0.2)
    except BaseException as exc: primary=exc
    finally:
        for key,path in paths.items():
            try:
                if file_sha(path)!=expected[key]: mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc: mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        terminal={'status':'HISTORICAL_ANNUAL_METADATA_CAPTURE_TERMINAL','logical_attempts':journal.attempts if journal else 0,
            'completed_resources':len(results),'pending':[k for k in keys if k not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence_errors,'PDFs_downloaded':0,'portfolio_returns_computed':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try: write_once(out/name,value)
            except BaseException as exc: persistence_errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence_errors: primary.add_note('Metadata terminal persistence errors: '+str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors,'metadata input changed or terminal evidence persistence failed')
    need(len(results)==len(keys),'all registered source resources processed')
    from collections import Counter
    counts=dict(Counter(r['status'] for r in results.values()))
    summary={'status':'ALL395_METADATA_RESOURCES_PROCESSED_NOT_DATA_ADMITTED','request_sha256':expected_sha,
        'resource_count':len(results),'logical_attempts':journal.attempts,'status_counts':counts,
        'full_report_candidates':sum(len(r.get('full_report_candidates',[])) for r in results.values()),
        'multiple_candidate_resources':[k for k,r in results.items() if len(r.get('full_report_candidates',[]))>1],
        'no_literal_candidate_resources':[k for k,r in results.items() if r['status']=='METADATA_CAPTURED_NO_LITERAL_FULL_REPORT_CANDIDATE'],
        'input_count':len(paths),'all_inputs_unchanged':True,'PDFs_downloaded':0,'financial_numeric_values_decoded':False,
        'current_org_mapping_is_historical_master':False,'financial_version_history_complete':False,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'portfolio_returns_computed':False,
        '2026_financial_or_market_values_decoded':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);base,root=Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result=capture(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['status_counts'],flush=True)
    return 2 if result['status_counts'].get('METADATA_SOURCE_REJECTED',0) else 0


if __name__=='__main__': raise SystemExit(main())
