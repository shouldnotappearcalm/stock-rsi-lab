"""Frozen pre2026 annual/correction candidate bytes over the dated394 range.
Keeps prior, revised, illustrated and unspecified-year editions distinct. No
PDF text, financial values, investment selection or publication-year inference.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import time
from scripts import capture_profitability_historical_initial_pdfs as metadata
from scripts import capture_profitability_annual_pdfs as fixed
from scripts.immutable_http_capture import ImmutableHttpCapture, need, file_sha, write_once

read = metadata.read
OUTPUT = 'gross-profitability-historical394-later-annual-pdfs-20261022'
STATUS = 'FROZEN_BEFORE_HISTORICAL394_ALL_LATER_ANNUAL_CANDIDATE_PDF_BYTES'
FIXED_REQUEST = 'experiments/qlib/profitability-fixed12-annual-pdf-request.json'
FIXED_SHA = '578b2a18c63944b3c833037608dd1beb493d2fb8a90b89570142b1f4b15ba18f'
FIXED_AUDIT = 'experiments/qlib/profitability-fixed12-annual-pdf-byte-audit.json'
FIXED_CODE = 'experiments/qlib/audit_sources/2026-10-22-profitability-annual-pdf-byte-audit.py'
METHODS = tuple(dict.fromkeys((*metadata.METHODS,*fixed.METHODS,'scripts/capture_profitability_later_annual_pdfs.py')))
PUBLIC = (FIXED_REQUEST,FIXED_AUDIT,FIXED_CODE,metadata.META_REQUEST,metadata.META_AUDIT,metadata.META_CODE,
    'docs/research/profitability-historical394-later-pdf-plan-2026-10-22.md',
    'tests/test_profitability_later_annual_pdfs.py')


def classify_title(title):
    clean = re.sub(r'[\s_《》]+','',re.sub(r'<[^>]+>','',title))
    if '摘要' in clean or re.search(r'abstract|summary',clean,re.I): return {'kind':'SUMMARY_METADATA_ONLY','fiscal_year':None}
    if '英文' in clean or re.search(r'annualreport',clean,re.I): return {'kind':'ENGLISH_METADATA_ONLY','fiscal_year':None}
    if '可视' in clean: return {'kind':'VISUAL_METADATA_ONLY','fiscal_year':None}
    if clean == '年报全文': return {'kind':'UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE','fiscal_year':None,'edition':'UNSPECIFIED'}
    edition = (r'全文|修订版?|修订稿|更正稿|更正后|更正版|修正后|更新后|更新版|更新前|中文版|图文版|'
               r'20\d{2}年(?:[1-9]|1[0-2])月修订版')
    match = re.search(r'(?P<year>(?:19|20)\d{2})年?(?:年度报告|年报报告|年报)(?:全文)?'
                      r'(?:[（(](?P<edition>'+edition+r')[）)])?$',clean)
    if match is None: return {'kind':'OTHER_ANNUAL_CATEGORY_TITLE_RETAINED','fiscal_year':None}
    year = int(match.group('year'))
    if year > 2024: return {'kind':'OUTSIDE_PRE2026_FISCAL_SCOPE','fiscal_year':year}
    label = match.group('edition') or 'INITIAL_OR_UNSPECIFIED'
    kind = ('PRIOR_VERSION_FULL_REPORT_CANDIDATE' if label == '更新前' else
            'ILLUSTRATED_FULL_REPORT_CANDIDATE' if label == '图文版' else
            'REVISED_FULL_REPORT_CANDIDATE' if re.search('修订|更正|修正|更新',label) else 'FULL_ANNUAL_REPORT_CANDIDATE')
    return {'kind':kind,'fiscal_year':year,'edition':label}


def select_documents(cohort, source_rows, cached):
    grouped,unselected,seen_rows = {},{},{}
    cache = {d['announcement_id']:d for d in cached}
    need(len(cache) == len(cached),'unique authenticated cache announcement IDs')
    for code,row,source_ref in source_rows:
        need(code in cohort,'source issuer outside dated cohort')
        identity = row['announcement_id'];core = {k:row[k] for k in ('title','day','timestamp_ms','announcement_id','pdf_path')}
        need(type(identity) is str and identity.isdigit(),'literal announcement ID')
        signature = {'instrument':code,**core}
        if identity in seen_rows: need(seen_rows[identity] == signature,'conflicting original metadata for announcement '+identity)
        seen_rows[identity] = signature
        classification = classify_title(core['title'])
        if 'CANDIDATE' not in classification['kind']:
            unselected[identity] = {**signature,**classification};continue
        year = classification['fiscal_year']
        day = datetime.fromtimestamp(core['timestamp_ms']/1000,timezone(timedelta(hours=8))).date().isoformat()
        need(day == core['day'] and '2024-01-01' <= day <= '2025-12-31'
             and (year is None or year < int(day[:4])),'pre2026 publication and explicit fiscal chronology')
        path = core['pdf_path']
        need(type(path) is str and re.fullmatch(r'finalpage/'+re.escape(day)+'/'+re.escape(identity)+r'\.[pP][dD][fF]',path),
             'literal official PDF path/date/ID identity')
        if identity not in grouped:
            d = {**core,'instrument':code,'fiscal_year':year,
                 'fiscal_year_basis':'EXPLICIT_TITLE_PENDING_COVER_CONFIRMATION' if year is not None else 'UNSPECIFIED_TITLE_COVER_REVIEW_REQUIRED',
                 'edition_role':classification['kind'],'edition_label':classification['edition'],
                 'capture_key':code+'-'+(str(year) if year is not None else 'UNKNOWN')+'-'+identity,
                 'url':'https://static.cninfo.com.cn/'+path,'metadata_source_refs':[]}
            old = cache.get(identity)
            if old:
                need(old['instrument'] == code and old['fiscal_year'] == year and all(old[k] == core[k] for k in core),'cached original metadata identity')
                d.update(source_kind='REUSE_AUTHENTICATED_ORIGINAL_PDF',source_path=old['source_path'],
                         source_sha256=old['source_sha256'],captured_at_utc=old['captured_at_utc'])
            else: d['source_kind'] = 'FRESH_FROZEN_PDF_GET'
            grouped[identity] = d
        if source_ref not in grouped[identity]['metadata_source_refs']:
            grouped[identity]['metadata_source_refs'].append(source_ref)
    documents = sorted(grouped.values(),key=lambda d:(d['instrument'],d['fiscal_year'] or 9999,d['day'],d['announcement_id']))
    gaps = {str(y):[c for c in cohort if not any(d['instrument'] == c and d['fiscal_year'] == y for d in documents)] for y in (2023,2024)}
    inventory = {'source_row_occurrences':len(source_rows),'unique_source_announcements':len(seen_rows),
        'selected_candidate_documents':len(documents),'selected_candidate_issuers':len({d['instrument'] for d in documents}),
        'candidate_counts_by_literal_fiscal_year':dict(Counter(str(d['fiscal_year']) for d in documents)),
        'candidate_counts_by_edition_role':dict(Counter(d['edition_role'] for d in documents)),
        'missing_explicit_fiscal_year_candidates_by_issuer':gaps,
        'yearless_source_candidates':[d['capture_key'] for d in documents if d['fiscal_year'] is None],
        'unselected_unique_title_counts':dict(Counter(d['kind'] for d in unselected.values())),
        'other_annual_category_titles_retained':[d for d in unselected.values() if d['kind'] == 'OTHER_ANNUAL_CATEGORY_TITLE_RETAINED'],
        'source_candidate_count_is_not_financial_content_coverage':True}
    return documents,inventory


def derive_documents(base, root, membership):
    cases = metadata.metadata_artifacts(base,root,membership)
    fixed.verify(base,root,root/FIXED_REQUEST,FIXED_SHA)
    audit = read(root/FIXED_AUDIT)
    need(audit['status'] == 'PASS_SEPARATE_FIXED12_ANNUAL_PDF_BYTE_AUDIT' and audit['request_sha256'] == FIXED_SHA
         and audit['audit_code_sha256'] == file_sha(root/FIXED_CODE),'authenticated original36 byte audit')
    directory = base/fixed.OUTPUT
    need({str(p.relative_to(directory)):file_sha(p) for p in sorted(directory.rglob('*')) if p.is_file()} == audit['all178_output_sha256'],
         'complete original36 capture outputs unchanged')
    cached = read(base/metadata.initial.DOCS)
    need(cached == audit['source_document_records'],'authenticated original36 source records')
    cohort = read(root/metadata.initial.CATALOG)['dated_cohort'];source_rows = []
    for code in cohort:
        path = base/metadata.initial.OLD/'codes'/(code+'.json');packet = read(path)
        need(packet['code'] == code and packet['query_window'] == ['2024-01-01','2025-12-31'],'original later publication window')
        ref = {'path':str(path.relative_to(base)),'sha256':file_sha(path)}
        for row in packet['reports']['annual']:
            need(row['code'] == code[2:],'original later issuer identity')
            source_rows.append((code,row,ref))
    for key,case in cases.items():
        if case['fiscal_year'] not in (2023,2024): continue
        path = base/metadata.initial.OUTPUT/(key+'.json');ref = {'path':str(path.relative_to(base)),'sha256':file_sha(path)}
        for row in case['all_normalized_rows']:source_rows.append((case['instrument'],row,ref))
    documents,inventory = select_documents(cohort,source_rows,cached)
    for d in documents:
        if d['source_kind'].startswith('REUSE'):
            need(not Path(d['source_path']).is_absolute() and '..' not in Path(d['source_path']).parts
                 and file_sha(base/d['source_path']) == d['source_sha256'],'unchanged original cached PDF')
    return documents,inventory


def resources(documents):
    return {d['capture_key']:{'method':'GET','url':d['url'],'payload':None} for d in documents if d['source_kind'] == 'FRESH_FROZEN_PDF_GET'}


def required_paths(base, root, membership):
    paths = {**metadata.required_paths(base,root,membership),**fixed.required_paths(base,root)}
    for name in (*METHODS,*PUBLIC):paths['repo/'+name] = root/name
    for name in read(root/FIXED_AUDIT)['all178_output_sha256']:
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe cached output path')
        paths['source/'+fixed.OUTPUT+'/'+name] = base/fixed.OUTPUT/name
    return paths


def verify(base, root, membership, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha,'frozen later annual PDF request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['per_resource_attempts'] == 1
         and req['max_body_bytes'] == 67108864 and req['timeout_seconds'] == 20 and req['minimum_request_interval_seconds'] == 0.2
         and req['PDF_text_or_financial_numeric_parsing_permitted'] is False and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'pre2026 later original bytes only')
    paths = required_paths(base,root,membership);metadata.initial.check(paths,req['input_sha256'])
    need(set(req['method_sha256']) == set(METHODS),'complete later-capture method closure')
    for name,h in req['method_sha256'].items():need(h == req['input_sha256']['repo/'+name],'method/input identity')
    documents,inventory = derive_documents(base,root,membership)
    need(req['documents'] == documents and req['source_inventory'] == inventory and req['resources'] == resources(documents)
         and req['document_count'] == len(documents) and req['source_issuer_count'] == 394
         and req['max_logical_attempts'] == len(req['resources']) and req['cache_reuse_count'] == len(documents)-len(req['resources']) == 24,
         'all original later candidates, editions,24 reuses and raw source gaps required')
    return req,paths


def capture(base, root, membership, request_file, expected_sha, out, *, opener=None, pause=time.sleep):
    need(out.resolve() == (base/OUTPUT).resolve() and not out.exists(),'fresh later PDF output only; no retry/resume')
    req,paths = verify(base,root,membership,request_file,expected_sha)
    paths = {**paths,'frozen_source_request':Path(request_file)};expected = {**req['input_sha256'],'frozen_source_request':expected_sha}
    metadata.initial.check(paths,expected);out.mkdir(parents=True)
    results,primary,mismatches,persistence_errors,journal = {},None,[],[],None
    try:
        write_once(out/'input-before.json',expected)
        journal = ImmutableHttpCapture(out/'http',req['resources'],max_attempts=len(req['resources']),max_body_bytes=67108864,
                                       **({} if opener is None else {'opener':opener}))
        consecutive = 0
        for document in req['documents']:
            key = document['capture_key']
            try:
                if document['source_kind'] == 'REUSE_AUTHENTICATED_ORIGINAL_PDF':
                    need(file_sha(base/document['source_path']) == document['source_sha256'],'old original PDF mutated')
                    result = {**document,'status':'ORIGINAL_PDF_BYTES_REUSED_CONTENT_REVIEW_SEPARATE'}
                else:
                    receipt,body = journal.fetch(key)
                    need(receipt['record']['http_status'] == 200 and receipt['record']['body_complete'] is True,'complete original HTTP200 PDF required')
                    with body.open('rb') as stream: magic = stream.read(5)
                    need(magic == b'%PDF-' and body.stat().st_size >= 1000,'original response is not a nontrivial PDF; bytes retained')
                    result = {**document,'status':'PDF_MAGIC_CAPTURED_CONTENT_REVIEW_PENDING','receipt':receipt,
                              'source_path':str(body.relative_to(base)),'source_sha256':file_sha(body),'captured_at_utc':receipt['record']['captured_at_utc']}
                consecutive = 0
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if getattr(exc,'capture_evidence_persistence_error',False):raise
                result = {**document,'status':'PDF_SOURCE_REJECTED','error_type':type(exc).__name__,'error':str(exc)};consecutive += 1
            results[key] = result;write_once(out/(key+'.json'),result)
            print('later annual PDF',len(results),'/',len(req['documents']),key,result['status'],flush=True)
            if consecutive == 3:raise ValueError('three consecutive PDF source rejections; remaining resources not attempted')
            if document['source_kind'] == 'FRESH_FROZEN_PDF_GET':pause(0.2)
    except BaseException as exc:primary = exc
    finally:
        for key,path in paths.items():
            try:
                if file_sha(path) != expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post = {'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        terminal = {'status':'HISTORICAL_LATER_ANNUAL_PDF_TERMINAL','logical_attempts':journal.attempts if journal else 0,
            'completed_documents':len(results),'pending':[d['capture_key'] for d in req['documents'] if d['capture_key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':persistence_errors,'financial_numeric_values_decoded':False}
        for name,value in (('case_results.json',results),('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence_errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if persistence_errors:primary.add_note('Later PDF persistence errors: '+str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors and len(results) == len(req['documents']),'complete unchanged later PDF capture')
    rejected = sum(r['status'] == 'PDF_SOURCE_REJECTED' for r in results.values())
    summary = {'status':'LATER_ANNUAL_CANDIDATE_PDF_BYTES_CAPTURED_CONTENT_REVIEW_PENDING' if not rejected else 'LATER_ANNUAL_PDF_CAPTURE_WITH_SOURCE_REJECTIONS',
        'request_sha256':expected_sha,'documents_recorded':len(results),'source_issuers':len({d['instrument'] for d in req['documents']}),
        'logical_GET_attempts':journal.attempts,'cached_originals_reused':req['cache_reuse_count'],'rejected_documents':rejected,
        'source_inventory':req['source_inventory'],'results_by_document':results,'input_count':len(paths),'all_inputs_unchanged':True,
        'PDF_text_or_financial_values_decoded':False,'issuer_fiscal_and_accounting_content_verified':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'documents.json',list(results.values()));write_once(out/'summary.json',summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args();base,root=Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result=capture(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['rejected_documents'],flush=True)
    return 2 if result['rejected_documents'] else 0


if __name__ == '__main__':raise SystemExit(main())
